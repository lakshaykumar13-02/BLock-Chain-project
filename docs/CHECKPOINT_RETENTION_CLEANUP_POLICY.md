# ChainVault — Checkpoint Retention & Cleanup Policy

**Project Root:** `C:\ChainVault` (Local workspace path: `d:\parjaayi project\CHAINVAULT`)

## 1. Objective
Establish rules for retaining, verifying, archiving, and cleaning up project checkpoints and backups without compromising source code, forensic evidence, database integrity, or recovery capability.

## 2. Ownership
- **Coding Agent:** Maintains checkpoint records, verifies backup integrity, identifies redundant backups, and proposes cleanup.
- **Project Owner:** Approves deletion of important checkpoints, recovery backups, or any item whose impact is uncertain.
- **No automatic destructive cleanup:** The agent must never delete checkpoints or backups simply to save disk space.

## 3. Mandatory Retention Rules
Retain the following until the final project demonstration and acceptance are complete:

1. The latest verified stable checkpoint.
2. At least one previous verified stable checkpoint.
3. Every completed phase checkpoint.
4. Pre-migration and pre-Solidity-deployment checkpoints.
5. Pre-risky-change checkpoints.
6. Rollback and recovery checkpoints.
7. Final-demo checkpoint.

A checkpoint that has not passed recovery verification must be labelled **NOT VERIFIED** and must not replace the latest verified stable checkpoint.

## 4. Cleanup Restrictions
The Coding Agent must never automatically delete:
- Original forensic evidence files.
- Evidence metadata or custody history.
- Blockchain transaction records or deployed-contract references.
- The only known-good checkpoint or backup.
- `.env` files, keys, credentials, or configuration files as a cleanup shortcut.
- Reports or audit logs required for the project.
- Git history or branches through force operations.

Generated temporary files may be removed only after confirming their paths, purpose, and lack of dependency on active workflows.

## 5. Cleanup Approval Workflow
Before any non-trivial cleanup:

1. Inspect `git status`, `git log -1 --oneline`, and `git diff --check`.
2. List the exact files or checkpoints proposed for removal.
3. Confirm that at least two verified recovery points remain where available.
4. Verify that no evidence, configuration, report, or audit data is included.
5. Explain the reason and impact to the Project Owner.
6. Obtain approval whenever a checkpoint, backup, or persistent data may be affected.
7. Delete only the approved targets.
8. Verify the project still starts and run relevant regression tests.
9. Record the operation in `docs/CHANGELOG.md` and, when recovery data is affected, `docs/RECOVERY_LOG.md`.

## 6. Storage and Backup Rules
- Keep checkpoints identifiable by phase, date, and purpose.
- Store backups separately from the files they protect when practical.
- Do not treat a Git commit as a complete backup of MongoDB data, uploaded evidence, environment secrets, or blockchain state.
- Never copy production or sensitive evidence into an ordinary test backup.
- Verify backup checksums or file listings when appropriate.
- Test restoration in an isolated environment before relying on a backup.

## 7. Emergency Disk-Space Procedure
If disk space is critically low:

1. Stop unnecessary build or test processes.
2. Inspect disk usage and identify temporary build artifacts.
3. Propose safe cleanup candidates.
4. Preserve verified recovery points and forensic data.
5. Request approval before deleting important backups or persistent data.
6. Confirm available space and re-run relevant tests.

Never use broad commands such as `rmdir /s /q` against the project root, blanket recursive deletion, or scripts that delete files based only on age.

## 8. Completion Criteria
Cleanup is complete only when:
- Only explicitly approved targets were removed.
- Required recovery points remain available.
- No forensic evidence or required audit data was altered.
- Relevant tests pass.
- Changes and outcomes are documented.

**STOP CONDITION:** If ownership, backup integrity, or the effect of deletion is uncertain, do not delete anything. Preserve the current state and request Project Owner approval.
