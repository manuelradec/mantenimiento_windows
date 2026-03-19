"""
Event Viewer Collection Module.

Collects, normalizes, and stores Windows Event Log entries for:
- Application events (errors/warnings)
- Disk/storage errors
- Windows Update events
- Display/DWM events
- Defender events

All results are stored as structured JSON and persisted to SQLite.
"""
import logging
import sys

from services.command_runner import run_powershell_json

logger = logging.getLogger('cleancpu.event_viewer')


def collect_events(log_name: str, provider: str = '', level: str = '',
                   max_events: int = 50, keyword: str = '') -> list[dict]:
    """
    Collect events from Windows Event Log using PowerShell JSON output.

    Args:
        log_name: Event log name (System, Application, Security, etc.)
        provider: Optional provider name filter (supports wildcards)
        level: Optional level filter (1=Critical, 2=Error, 3=Warning)
        max_events: Maximum events to retrieve
        keyword: Optional keyword to filter in Message

    Returns:
        List of normalized event dicts.
    """
    if sys.platform != 'win32':
        return [{'note': 'Event Viewer not available on non-Windows platforms'}]

    # Build FilterHashtable
    filters = [f"LogName='{log_name}'"]
    if level:
        filters.append(f"Level={level}")
    if provider:
        filters.append(f"ProviderName='{provider}'")

    filter_str = ';'.join(filters)
    script = (
        f"Get-WinEvent -FilterHashtable @{{{filter_str}}} "
        f"-MaxEvents {max_events} -ErrorAction SilentlyContinue | "
        f"Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message"
    )

    result = run_powershell_json(script, timeout=30, description=f'Collect {log_name} events')

    # rc=1 from Get-WinEvent is common (no events matching filter, or partial read)
    # — treat as acceptable and process any data returned
    if not result.is_success and result.return_code != 1:
        return []

    data = result.details.get('data', [])
    if isinstance(data, dict):
        data = [data]

    events = []
    for evt in data:
        if not isinstance(evt, dict):
            continue
        normalized = {
            'log_name': log_name,
            'provider': evt.get('ProviderName', ''),
            'event_id': evt.get('Id'),
            'level': evt.get('LevelDisplayName', ''),
            'time_created': str(evt.get('TimeCreated', '')),
            'message': str(evt.get('Message', ''))[:500],
        }
        if keyword and keyword.lower() not in normalized['message'].lower():
            continue
        events.append(normalized)

    return events


def collect_application_errors(max_events: int = 30) -> list[dict]:
    """Collect recent Application log errors and warnings."""
    return collect_events('Application', level='2,3', max_events=max_events)


def collect_disk_errors(max_events: int = 30) -> list[dict]:
    """Collect disk/storage related errors from System log."""
    return collect_events('System', provider='*disk*,*ntfs*,*storage*', max_events=max_events)


def collect_update_events(max_events: int = 30) -> list[dict]:
    """Collect Windows Update related events."""
    events = collect_events(
        'System', provider='*Microsoft-Windows-WindowsUpdateClient*',
        max_events=max_events)
    events += collect_events('Setup', max_events=max_events)
    return events[:max_events]


def collect_display_events(max_events: int = 30) -> list[dict]:
    """Collect display/DWM/GPU related events."""
    return collect_events(
        'System', provider='*dwm*,*display*,*gpu*,*video*',
        max_events=max_events)


def collect_defender_events(max_events: int = 30) -> list[dict]:
    """Collect Defender/security events."""
    return collect_events(
        'Microsoft-Windows-Windows Defender/Operational',
        max_events=max_events)


def collect_all_relevant_events(max_per_category: int = 20) -> dict:
    """Collect all relevant event categories for incident reporting."""
    return {
        'application_errors': collect_application_errors(max_per_category),
        'disk_errors': collect_disk_errors(max_per_category),
        'update_events': collect_update_events(max_per_category),
        'display_events': collect_display_events(max_per_category),
        'defender_events': collect_defender_events(max_per_category),
    }


def store_collected_events(session_id: str, events_by_category: dict, job_id: str = ''):
    """Persist collected events to SQLite."""
    from core.persistence import EventViewerStore
    for category, events in events_by_category.items():
        EventViewerStore.store_events(session_id, events, job_id)
    logger.info(f"Stored event viewer data for session {session_id}")
