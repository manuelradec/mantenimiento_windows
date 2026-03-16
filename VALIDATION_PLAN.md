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
| 3.1 | Cleanup > User Temp | Files cleaned, before/after snapshot, rollback info shown |  |
| 3.2 | Cleanup > DNS Cache | ipconfig /flushdns executes, success |  |
| 3.3 | Network > Flush DNS | Same as above via network route |  |
| 3.4 | Network > Test Connectivity | Ping results displayed |  |
| 3.5 | Update > Scan | Windows Update scan initiated |  |
| 3.6 | Security > Quick Scan | Defender quick scan starts |  |
| 3.7 | Verify audit log | GET /api/jobs shows completed jobs with timestamps |  |
| 3.8 | Verify JSONL log | logs/events.jsonl contains action_executed entries |  |

## Phase 4: Admin-Required Actions (Run as Admin)

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 4.1 | Restart as admin | "ADMIN" badge visible |  |
| 4.2 | Cleanup > Windows Temp | System temp cleaned (requires admin) |  |
| 4.3 | Cleanup > Software Distribution | WU cache cleaned |  |
| 4.4 | Repair > SFC (change to Advanced mode first) | sfc /scannow runs |  |
| 4.5 | Repair > DISM Check Health | DISM CheckHealth runs |  |
| 4.6 | Network > Reset Winsock | Winsock reset, reboot warning shown |  |
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

## Phase 7: Reporting

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 7.1 | Reports page loads | Lists available report types |  |
| 7.2 | Generate HTML report | Incident-grade HTML with executive summary |  |
| 7.3 | Generate text report | Structured text report |  |
| 7.4 | Generate JSON export | Full bundle with audit, snapshots, jobs |  |
| 7.5 | Verify snapshots in report | Before/after disk/RAM data present |  |

## Phase 8: Command Security

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 8.1 | Verify sfc /scannow allowed | Command executes |  |
| 8.2 | Verify DISM allowed subcommands only | /CheckHealth, /ScanHealth, /RestoreHealth work |  |
| 8.3 | Verify `net user` blocked | net with 'user' as first arg rejected |  |
| 8.4 | Verify `net stop wuauserv` allowed | net stop with service name works |  |
| 8.5 | Verify `sc delete` blocked | sc with 'delete' rejected |  |
| 8.6 | Verify unknown commands blocked | evil.exe rejected by allowlist |  |
| 8.7 | Verify argument sanitization | Semicolons, pipes, backticks blocked |  |

## Phase 9: Edge Cases

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 9.1 | Rapid repeated clicks on action button | Module lock prevents duplicate execution |  |
| 9.2 | Close browser during long action | Job continues, visible on reconnect |  |
| 9.3 | SSD-only actions on HDD | Appropriate not_applicable or runtime check |  |
| 9.4 | Battery report on desktop | Graceful handling |  |
| 9.5 | SQLite DB corruption recovery | init_db() recreates tables |  |

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Tester | | | |
| Developer | | | |
| Tech Lead | | | |
