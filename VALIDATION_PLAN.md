# CleanCPU v3.0.0 - Windows Validation Plan

## Pre-requisites
- Windows 10 (21H2+) or Windows 11 (22H2+)
- Python 3.10+ installed
- Admin and non-admin terminal sessions available
- Network connectivity for update tests

## Phase 1: Startup & Security (Non-Admin)

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 1.1 | `python run.py` | Server starts on 127.0.0.1:5000, browser opens |  |
| 1.2 | Open http://127.0.0.1:5000 | Dashboard loads, "NO ADMIN" badge visible |  |
| 1.3 | Open http://localhost:5000 | Dashboard loads (localhost in allowed hosts) |  |
| 1.4 | curl with `Host: evil.com` header | 403 Forbidden |  |
| 1.5 | POST without CSRF token | 403 Forbidden |  |
| 1.6 | POST with `Origin: http://evil.com` | 403 Forbidden |  |
| 1.7 | Check response headers | CSP, X-Frame-Options:DENY, nosniff, same-origin present |  |
| 1.8 | Inspect session cookie | HttpOnly=true, SameSite=Strict, name=cleancpu_session |  |
| 1.9 | Open from another machine on LAN | Connection refused (127.0.0.1 only) |  |

## Phase 2: Read-Only Diagnostics (Non-Admin)

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 2.1 | Dashboard system overview | OS, CPU, RAM, disk info displayed |  |
| 2.2 | Diagnostics page | System info loads via psutil |  |
| 2.3 | Drivers page | Driver list via pnputil |  |
| 2.4 | GET /api/system-overview | JSON with os_name, cpu, ram fields |  |
| 2.5 | GET /api/actions | 40+ actions listed with risk classes |  |
| 2.6 | GET /api/policy/status | mode: safe_maintenance |  |
| 2.7 | GET /api/elevation | is_admin: false |  |

## Phase 3: Safe Mutations (Non-Admin where possible)

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 3.1 | Cleanup > User Temp | Files cleaned, before/after snapshot with category=cleanup |  |
| 3.2 | Cleanup > DNS Cache | ipconfig /flushdns executes, success |  |
| 3.3 | Network > Flush DNS | Flush DNS via network route, snapshot category=network |  |
| 3.4 | Network > Test Connectivity | Ping results displayed |  |
| 3.5 | Update > Scan | Windows Update scan initiated, snapshot category=update |  |
| 3.6 | Security > Quick Scan | Defender quick scan starts, snapshot category=security |  |
| 3.7 | Verify audit log | GET /api/jobs shows completed jobs with timestamps |  |
| 3.8 | Verify JSONL log | logs/events.jsonl contains action_executed entries |  |
| 3.9 | Verify rollback_info in response | Each action result contains rollback classification, needs_reboot, restore_point_recommended |  |

## Phase 4: Admin-Required Actions (Run as Admin)

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 4.1 | Restart as admin | "ADMIN" badge visible |  |
| 4.2 | Cleanup > Windows Temp | System temp cleaned (requires admin) |  |
| 4.3 | Cleanup > Software Distribution | WU cache cleaned |  |
| 4.4 | Repair > SFC (change to Advanced mode first) | sfc /scannow runs, Event Viewer data collected |  |
| 4.5 | Repair > DISM Check Health | DISM CheckHealth runs |  |
| 4.6 | Network > Reset Winsock | Winsock reset, reboot warning shown, needs_reboot=true |  |
| 4.7 | Advanced > Create Restore Point | Restore point created |  |
| 4.8 | Update > Install | Updates installed if available |  |

## Phase 5: Policy Engine Enforcement

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 5.1 | Default mode = safe_maintenance | RISKY/DISRUPTIVE/DESTRUCTIVE actions rejected |  |
| 5.2 | Try Repair > SFC in safe mode | Status: rejected, reason: mode_restriction |  |
| 5.3 | Try Power > Set Balanced in safe mode | Status: rejected |  |
| 5.4 | Switch to Advanced mode | POST /api/policy/mode with {"mode":"advanced"} |  |
| 5.5 | Retry SFC in Advanced mode | Action proceeds (or needs_confirmation) |  |
| 5.6 | Confirmation flow | needs_confirmation -> user confirms -> action executes |  |
| 5.7 | Switch to Expert mode | DESTRUCTIVE actions allowed with confirmation |  |
| 5.8 | Switch to Diagnostic mode | Only read-only actions allowed |  |

## Phase 6: Job Runner & Cancellation

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 6.1 | Start long-running action (SFC) | Job status bar appears with spinner |  |
| 6.2 | Cancel running job | Job cancelled, process tree killed |  |
| 6.3 | Verify module locking | Second action on same module rejected while first runs |  |
| 6.4 | Different module concurrent | Two different modules can run simultaneously |  |
| 6.5 | Verify job duration_ms | Completed jobs show non-zero duration |  |

## Phase 7: Reporting

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 7.1 | Reports page loads | Lists available report types |  |
| 7.2 | Generate HTML report | Incident-grade HTML with executive summary |  |
| 7.3 | Generate text report | Structured text report |  |
| 7.4 | Generate JSON export | Full bundle with audit, snapshots, jobs |  |
| 7.5 | Verify snapshots in report | Before/after data with action-specific fields (category, disk, temp sizes) |  |
| 7.6 | Verify Event Viewer data in report | Repair/update actions include relevant Windows events |  |

## Phase 8: Action-Aware Snapshots

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 8.1 | Cleanup action snapshot | category=cleanup, user_temp_mb, windows_temp_mb, prefetch_mb present |  |
| 8.2 | Network action snapshot | category=network, adapter info present |  |
| 8.3 | Power action snapshot | category=power, active_plan present |  |
| 8.4 | Update action snapshot | category=update, wu_services, software_distribution_exists present |  |
| 8.5 | Security action snapshot | category=security, defender info present |  |
| 8.6 | Storage action snapshot (retrim) | category=storage, disks info present |  |
| 8.7 | Repair action snapshot | category=repair, base metrics present |  |
| 8.8 | Explorer restart snapshot | category=explorer, explorer_running flag present |  |
| 8.9 | Before/after comparison | Both snapshots stored, diff visible in report |  |

## Phase 9: Rollback Classification

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 9.1 | Check flush_dns rollback | classification=auto_reversible, needs_reboot=false |  |
| 9.2 | Check reset_winsock rollback | classification=manually_reversible, needs_reboot=true |  |
| 9.3 | Check SFC rollback | restore_point_recommended=true |  |
| 9.4 | Check component_cleanup rollback | classification=not_reversible, restore_point_recommended=true |  |
| 9.5 | Verify all mutating actions have strategies | No registered mutating action without ROLLBACK_STRATEGIES entry |  |

## Phase 10: Command Security (Hardened)

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 10.1 | Verify sfc /scannow allowed | Command executes |  |
| 10.2 | Verify DISM allowed subcommands only | /CheckHealth, /ScanHealth, /RestoreHealth work |  |
| 10.3 | Verify `net user` blocked | net with 'user' as first arg rejected |  |
| 10.4 | Verify `net localgroup` blocked | net with 'localgroup' rejected |  |
| 10.5 | Verify `net stop wuauserv` allowed | net stop with service name works |  |
| 10.6 | Verify `sc delete` blocked | sc with 'delete' rejected |  |
| 10.7 | Verify unknown commands blocked | evil.exe rejected by allowlist |  |
| 10.8 | Verify argument sanitization | Semicolons, pipes, backticks blocked |  |
| 10.9 | Verify mdsched.exe with args blocked | max_args=0 enforcement |  |
| 10.10 | Verify wsreset.exe with args blocked | max_args=0 enforcement |  |
| 10.11 | Verify ren only allows WU paths | allowed_patterns enforcement for ren |  |
| 10.12 | Verify cscript only allows slmgr.vbs | allowed_patterns enforcement for cscript |  |
| 10.13 | Verify pnputil /delete-driver blocked | denied_args enforcement |  |
| 10.14 | Verify netsh firewall args blocked | denied_args enforcement |  |
| 10.15 | Verify defrag /x blocked, /A allowed | denied_args + allowed subcommands |  |
| 10.16 | Verify PowerShell requires proper flags | -NoProfile, -NonInteractive, -Command required |  |

## Phase 11: PowerShell JSON Output

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 11.1 | GET /api/system-overview | Structured JSON, not Format-Table text |  |
| 11.2 | Network adapters | JSON array with Name, Status, LinkSpeed fields |  |
| 11.3 | RAM details | JSON with CapacityGB, Speed fields |  |
| 11.4 | Important services | JSON array with Name, Status, StartType |  |
| 11.5 | Startup programs | JSON array, not text table |  |

## Phase 12: Edge Cases

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 12.1 | Rapid repeated clicks on action button | Module lock prevents duplicate execution |  |
| 12.2 | Close browser during long action | Job continues, visible on reconnect |  |
| 12.3 | SSD-only actions on HDD | Appropriate not_applicable or runtime check |  |
| 12.4 | Battery report on desktop | Graceful handling |  |
| 12.5 | SQLite DB corruption recovery | init_db() recreates tables |  |
| 12.6 | Non-admin PermissionError on ProgramData | Graceful fallback to local directory |  |

## Automated Test Coverage

| Suite | Tests | Coverage |
|-------|-------|----------|
| test_action_registry.py | Action registration, risk classification | Core |
| test_policy_engine.py | Mode enforcement, session lifecycle, persistence | Core |
| test_routes.py | Routes, CSRF, origin validation, security headers, governed endpoints | API |
| test_snapshots.py | Action-aware snapshots, dispatch, collectors | Snapshots |
| test_hardening.py | Command runner, rollback classification, job runner, locking, persistence | Hardening |

Run: `python -m pytest tests/ -v`

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Tester | | | |
| Developer | | | |
| Tech Lead | | | |
