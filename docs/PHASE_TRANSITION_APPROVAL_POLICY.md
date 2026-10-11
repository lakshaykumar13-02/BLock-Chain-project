# ChainVault — Phase Transition & Change Approval Policy

**Project Root:** `C:\ChainVault` (Local workspace path: `d:\parjaayi project\CHAINVAULT`)

## 1. Objective
Define strict conditions for moving between development phases, approving scope changes, and preventing incomplete or unverified work from being treated as finished.

## 2. Phase Completion Ownership
- **Coding Agent:** Implements the current phase, runs tests, reviews changes, documents results, and reports blockers.
- **Project Owner:** Reviews phase completion evidence and approves progression when required.
- The agent must never declare a phase complete merely because the code has been written.

## 3. Mandatory Phase Completion Gate
Before marking any phase COMPLETE, the Coding Agent must:

1. Confirm that all phase requirements have been implemented.
2. Run the relevant unit, integration, and regression tests.
3. Inspect test output and report actual pass, fail, and skipped counts.
4. Verify relevant application startup and workflows.
5. Check API routes, frontend calls, configuration, and documentation for consistency.
6. Review `git diff --check`, `git status`, and the final diff.
7. Confirm that no secrets, credentials, evidence files, or sensitive generated reports were accidentally added.
8. Create a verified checkpoint according to the existing checkpoint and recovery policies.
9. Update `docs/CHANGELOG.md` and relevant test documentation.
10. Provide a completion report with evidence and any remaining limitations.

If any mandatory requirement fails, mark the phase **BLOCKED** or **INCOMPLETE**, not COMPLETE.

## 4. Phase Transition Rules
- Start only the phase explicitly authorized by the Project Owner.
- Do not skip phases or silently combine multiple phases.
- Do not begin the next phase while required acceptance tests for the current phase are failing.
- Preserve the current working state and diagnostics when blocked.
- Ask for clarification if the phase requirements conflict with existing architecture or security policies.
- A successful checkpoint does not automatically authorize the next phase.

## 5. Scope Change Approval
The Coding Agent must request approval before:
- Replacing a locked technology or architectural component.
- Introducing a new database or changing the database strategy.
- Adding an unplanned framework or major dependency.
- Changing authentication, RBAC, evidence integrity, or custody semantics.
- Changing Solidity contracts in a way that requires redeployment.
- Removing required features or altering accepted requirements.
- Performing irreversible operations affecting persistent data, Git history, or real blockchain resources.

Small, reversible implementation details may be handled autonomously when they do not change the approved scope or architecture.

## 6. Blocker Reporting
When blocked, report:
- Phase and requirement affected.
- Exact error or failed test.
- Root cause, if established.
- Files or components involved.
- Safe options for resolution.
- Whether rollback is necessary.
- Whether Project Owner approval is required.

Do not hide, bypass, or weaken a failing test simply to achieve a green result.

## 7. Final Status Labels
Use only these labels:
- **NOT STARTED:** No implementation work has begun.
- **IN PROGRESS:** Work is underway.
- **BLOCKED:** Work cannot safely proceed.
- **INCOMPLETE:** Work exists but acceptance requirements are unmet.
- **COMPLETE — VERIFIED:** Acceptance checks passed and evidence is documented.
- **COMPLETE — WITH LIMITATIONS:** Core acceptance checks passed, but documented non-critical limitations remain and are explicitly accepted.

Never use COMPLETE — VERIFIED when tests were not run or their results cannot be confirmed.

## 8. Completion Report Format
For every phase, provide:
- Implemented requirements.
- Files created or modified.
- Commands executed.
- Actual test results.
- Manual verification results.
- Known limitations and blockers.
- Checkpoint identifier and recovery-verification status.
- Recommended next action.

## 9. Stop Condition
After reporting the current phase status, STOP. Do not begin another phase or make unrelated changes without explicit authorization.

This policy supplements the existing safe execution, rollback ownership, checkpoint creation, recovery verification, and retention policies. If rules conflict, preserve data and security first, stop, and request clarification.
