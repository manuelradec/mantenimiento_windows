# AGENTS.md

## Project
Internal enterprise Windows maintenance application: `mantenimiento_windows`

## Phase Discipline
- Work only on the requested phase.
- Do not mix phases.
- Do not reopen previous phases unless fixing a direct regression.
- Keep changes additive whenever possible.
- Do not redesign the whole application unless explicitly requested.

## Architecture Rules
- Any mutating action must follow the existing governance model.
- Any new governed action must be registered in `core/action_registry.py`.
- Any action requiring rollback coverage must be added to `core/governance.py`.
- Respect the current risk model:
  - SAFE_READONLY
  - SAFE_MUTATION
  - RISKY
  - DISRUPTIVE
  - DESTRUCTIVE
- Do not bypass admin, confirmation, reboot, or mode restrictions.

## Windows Safety Rules
- Use only supported Windows methods.
- Be explicit about environment limitations.
- Do not silently enable insecure legacy features.
- SMB1/CIFS must always be treated as high-risk and separately gated.
- Be careful with Windows Optional Feature states:
  - Enabled
  - Disabled
  - EnablePending
  - DisabledWithPayloadRemoved
  - NotPresent
  - Unknown
- Be honest about Windows edition/version and Group Policy limitations.

## UI / UX Rules
- Technician-facing UI text must be in Spanish.
- Do not imply support that does not actually exist.
- Show clear operator-facing output in the page console/output area.
- Prefer support-oriented UX over consumer-style UX.

## Testing / Validation
After each implementation:
- run flake8 on touched Python files
- run governance tests
- run hardening tests when relevant
- report exact files changed
- report exact action IDs added
- report exact rollback entries added
- state whether the phase is ready for review

## Required Review Output
Always provide:
1. exact code-change summary
2. UI flow
3. backend flow
4. validations run
5. blockers
6. remaining risks
7. whether the phase is ready for review
