# CHAINVAULT — CHECKPOINT CREATION TIMING POLICY

**Project Root:** `C:\ChainVault` (Local workspace path: `d:\parjaayi project\CHAINVAULT`)

## 1. Mandatory Checkpoint Schedule

The coding agent MUST create a recoverable checkpoint at the following times.

| Trigger | Checkpoint Timing | Priority |
|---|---|---|
| Before starting a new phase | Before the first code modification | Mandatory |
| After completing a major feature | Immediately after focused tests pass | Mandatory |
| After completing a phase | After all phase acceptance criteria pass | Mandatory |
| Before modifying authentication, RBAC, or secrets configuration | Before the first modification | Mandatory |
| Before modifying database schemas or migrations | Before the first modification | Mandatory |
| Before modifying Solidity contracts or deployment configuration | Before the first modification | Mandatory |
| Before dependency upgrades or replacements | Before installation or modification | Mandatory |
| Before destructive or potentially irreversible operations | Before execution; obtain required approval first | Mandatory |
| After a successful rollback | After recovery and regression tests pass | Mandatory |
| Before final project demonstration | After the complete end-to-end workflow passes | Mandatory |

## 2. Checkpoint Creation Procedure

For every mandatory checkpoint:

1. Inspect the current Git status.
2. Confirm no unrelated user changes will be overwritten.
3. Run the relevant tests.
4. Record the current phase and project state.
5. Create a Git commit or a verified backup.
6. Record the checkpoint identifier and test results.
7. Continue only after the checkpoint is confirmed.

Example commands:

```powershell
cd C:\ChainVault
git status
git diff --check
git diff
```

If the project is under Git and the working tree is ready, create a meaningful commit:

```powershell
git add <reviewed-files>
git commit -m "Checkpoint: Phase 12 validated"
```

Stage only reviewed project files. Never commit `.env`, private keys, credentials, evidence files, or generated reports containing sensitive information.

If Git is unavailable, create a timestamped backup of the relevant source/configuration files. Do not copy live databases or evidence storage without a safe backup procedure.

## 3. Exact Phase Checkpoint Timing

Every phase follows this sequence:

**Checkpoint A — Before the phase**
- Previous phase is stable.
- Current tests pass.
- Current configuration and Git state are recorded.

**Checkpoint B — After each major milestone**
- The feature is implemented.
- Focused tests pass.
- Relevant regression tests pass.

**Checkpoint C — Phase completion**
- All phase acceptance criteria pass.
- Full relevant test suites pass.
- Application startup and critical workflows are verified.
- Documentation is updated.
- A stable checkpoint is created.

Do not label a failing or partially implemented phase as complete.

## 4. Emergency Checkpoint Timing

If a critical failure occurs, do not create a checkpoint that falsely marks the broken state as stable.

Instead:

1. Stop the current change.
2. Preserve diagnostic information and the current diff.
3. Identify the last known good checkpoint.
4. Roll back the smallest safe change.
5. Run recovery and regression tests.
6. Create a new recovery checkpoint only after recovery passes.

Preserve the failed diff separately when useful for debugging.

## 5. Checkpoint Ownership

- **Coding Agent:** Creates checkpoints, records identifiers, verifies tests, and documents recovery.
- **Project Owner:** Approves destructive operations and any checkpoint procedure that risks real evidence or persistent data.
- **Verification:** The coding agent verifies technical recovery; the project owner accepts recovery involving real evidence or consequential persistent data.

## 6. Checkpoint Retention

- Keep every completed-phase checkpoint.
- Keep the most recent stable checkpoint.
- Keep pre-migration and pre-contract-change checkpoints until the change is verified.
- Keep rollback and recovery checkpoints.
- Never automatically delete backups containing potentially important project data.
- Never store secrets in Git commits or backup logs.

## 7. Checkpoint Naming Convention

Use:

`Checkpoint: Phase <number> — <milestone>`

Examples:

- `Checkpoint: Phase 12 — Pre-Testing`
- `Checkpoint: Phase 12 — Regression Passed`
- `Checkpoint: Phase 12 — Complete`
- `Checkpoint: Phase 12 — Recovery Verified`
- `Checkpoint: Phase 13 — Pre-Demo`

Record the Git commit hash or exact backup location in:

`C:\ChainVault\docs\CHANGELOG.md`

## 8. Mandatory Stop Rule

The coding agent MUST NOT start the next phase until:

- The current phase passes its acceptance criteria.
- Required regression tests pass.
- The final stable checkpoint is verified.
- The checkpoint identifier is recorded.

If checkpoint creation fails, stop and report the reason. Do not claim the checkpoint exists.

**Final rule:** Create checkpoints before risky changes, after verified milestones, at phase completion, and after successful recovery. Never confuse a backup with a verified stable checkpoint.
