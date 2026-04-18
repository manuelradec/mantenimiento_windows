"""
Regression tests for Ola 3 fixes (P2 — pre-checks + network credentials).

1. `get_battery_report()` skips with NOT_APPLICABLE when there is no battery
   (desktops) instead of emitting powercfg's raw error.

2. `inspect_license()` falls back to SoftwareLicensingProduct via WMI when
   ospp.vbs is missing, producing a usable ``status='success'`` result.

3. `services.network_credentials` validates targets, rejects empty
   user/password, and masks password in the command description.

4. `save_to_network_share()` converts OSError winerror=1326 into a
   ``status='skipped', reason='auth_required'`` result with a user-facing
   hint, instead of propagating the raw exception.

5. cmdkey allowlist patterns accept valid forms and reject foreign ones.
"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.command_runner import _validate_command, CommandResult, CommandStatus
from services import power_tools
from services import office_tools
from services import network_credentials
from services import maintenance_report


# ============================================================
# 1. Battery pre-check
# ============================================================

class TestBatteryPreCheck:

    def test_no_battery_returns_not_applicable_without_running_powercfg(self):
        """On a desktop (no battery) powercfg must never be invoked."""
        with patch.object(power_tools, '_has_battery', return_value=False):
            with patch.object(power_tools, 'run_cmd') as mock_run:
                with patch.object(sys, 'platform', 'win32'):
                    result = power_tools.get_battery_report()
        assert result.status == CommandStatus.NOT_APPLICABLE
        assert 'bateria' in (result.output or '').lower()
        mock_run.assert_not_called()

    def test_battery_present_still_runs_powercfg(self):
        fake = CommandResult(status=CommandStatus.SUCCESS, output='ok')
        with patch.object(power_tools, '_has_battery', return_value=True):
            with patch.object(power_tools, 'run_cmd', return_value=fake) as mock_run:
                with patch.object(sys, 'platform', 'win32'):
                    result = power_tools.get_battery_report()
        assert result.is_success
        mock_run.assert_called_once()
        assert '/batteryreport' in mock_run.call_args.args[0]


# ============================================================
# 2. Office WMI fallback
# ============================================================

class TestOfficeSlpFallback:

    def test_inspect_license_uses_slp_when_ospp_missing(self):
        slp_payload = CommandResult(status=CommandStatus.SUCCESS, output='[{}]')
        slp_payload.details['data'] = [{
            'Name': 'Office 21, Office21ProPlus2021VL_KMS_Client_AE edition',
            'Description': 'Office 2021',
            'PartialProductKey': 'ABCDE',
            'LicenseStatus': 1,
        }]
        with patch.object(office_tools, '_find_ospp', return_value=''):
            with patch.object(office_tools, 'run_powershell_json',
                              return_value=slp_payload):
                with patch.object(office_tools.sys, 'platform', 'win32'):
                    result = office_tools.inspect_license()
        assert result['status'] == 'success'
        assert result['parsed']['license_status'] == 'licensed'
        assert result['parsed']['source'] == 'slp_wmi'
        assert result['parsed']['partial_key'] == 'ABCDE'

    def test_inspect_license_slp_no_office_entries(self):
        empty = CommandResult(status=CommandStatus.SUCCESS, output='')
        empty.details['data'] = None
        with patch.object(office_tools, '_find_ospp', return_value=''):
            with patch.object(office_tools, 'run_powershell_json',
                              return_value=empty):
                with patch.object(office_tools.sys, 'platform', 'win32'):
                    result = office_tools.inspect_license()
        assert result['status'] == 'office_not_found'

    def test_inspect_license_slp_error_propagates_as_error(self):
        bad = CommandResult(status=CommandStatus.ERROR,
                            output='', error='some CIM failure')
        with patch.object(office_tools, '_find_ospp', return_value=''):
            with patch.object(office_tools, 'run_powershell_json',
                              return_value=bad):
                with patch.object(office_tools.sys, 'platform', 'win32'):
                    result = office_tools.inspect_license()
        assert result['status'] == 'error'


# ============================================================
# 3. network_credentials validation + password masking
# ============================================================

class TestNetworkCredentials:

    def test_validate_target_accepts_unc(self):
        assert network_credentials._validate_target(
            r'\\192.168.122.215\soporte CLJ'
        ) == r'\\192.168.122.215\soporte CLJ'

    def test_validate_target_strips_outer_quotes(self):
        assert network_credentials._validate_target('"\\\\host\\share"') == r'\\host\share'

    def test_validate_target_rejects_shell_metacharacters(self):
        import pytest
        with pytest.raises(ValueError):
            network_credentials._validate_target(r'\\host\share; rm -rf /')

    def test_save_credential_rejects_empty_password(self):
        with patch.object(network_credentials.sys, 'platform', 'win32'):
            result = network_credentials.save_credential(
                r'\\host\share', 'user', ''
            )
        assert result['status'] == 'invalid_password'

    def test_save_credential_masks_password_in_description(self):
        """run_cmd description must never contain the real password."""
        fake_ok = CommandResult(status=CommandStatus.SUCCESS, output='')
        with patch.object(network_credentials.sys, 'platform', 'win32'):
            with patch.object(network_credentials, 'run_cmd',
                              return_value=fake_ok) as mock_run:
                network_credentials.save_credential(
                    r'\\host\share', 'admin', 'SuperSecret123!'
                )
        called_description = mock_run.call_args.kwargs.get('description', '')
        assert 'SuperSecret123!' not in called_description
        assert 'admin' not in called_description
        # argv still contains the password (that's how cmdkey receives it) —
        # that is fine, cmdkey never echoes it.
        argv = mock_run.call_args.args[0]
        assert '/pass:SuperSecret123!' in argv


# ============================================================
# 4. WinError 1326 → skipped/auth_required
# ============================================================

class TestShareAuthFallback:

    def test_save_to_network_share_1326_returns_auth_required(self):
        err = OSError('logon failure')
        err.winerror = 1326
        with patch.object(maintenance_report.sys, 'platform', 'win32'):
            with patch.object(maintenance_report.os, 'makedirs',
                              side_effect=err):
                result = maintenance_report.save_to_network_share(
                    '<html/>', {'hostname': 'H', 'serial': 'S'}
                )
        assert result['status'] == 'skipped'
        assert result['reason'] == 'auth_required'
        assert result['winerror'] == 1326
        assert 'credenciales' in (result.get('error') or '').lower()

    def test_save_to_network_share_unrelated_error_stays_error(self):
        err = OSError('disk full')
        err.winerror = 112  # ERROR_DISK_FULL
        with patch.object(maintenance_report.sys, 'platform', 'win32'):
            with patch.object(maintenance_report.os, 'makedirs',
                              side_effect=err):
                result = maintenance_report.save_to_network_share(
                    '<html/>', {'hostname': 'H', 'serial': 'S'}
                )
        assert result['status'] == 'error'


# ============================================================
# 5. cmdkey allowlist
# ============================================================

class TestCmdkeyAllowlist:

    def test_cmdkey_list_allowed(self):
        assert _validate_command(['cmdkey', '/list']) is True

    def test_cmdkey_list_with_target_allowed(self):
        assert _validate_command(['cmdkey', r'/list:\\host\share']) is True

    def test_cmdkey_add_full_form_allowed(self):
        assert _validate_command([
            'cmdkey',
            r'/add:\\host\share',
            '/user:admin',
            '/pass:SuperSecret123!',
        ]) is True

    def test_cmdkey_delete_allowed(self):
        assert _validate_command(['cmdkey', r'/delete:\\host\share']) is True

    def test_cmdkey_add_without_credentials_rejected(self):
        """cmdkey /add:<target> alone (no user/pass) must be blocked."""
        assert _validate_command(['cmdkey', r'/add:\\host\share']) is False

    def test_cmdkey_unknown_flag_rejected(self):
        assert _validate_command(['cmdkey', '/wipe']) is False
