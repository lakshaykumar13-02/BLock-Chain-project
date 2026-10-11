# CHAINVAULT — CHECKPOINT VERIFICATION & RECOVERY TESTING POLICY

**Project Root:** `C:\ChainVault` (Local workspace path: `d:\parjaayi project\CHAINVAULT`)

## 1. Objective

Every stable checkpoint must be identifiable, intact, and suitable for recovery. A checkpoint must not be considered verified merely because a Git commit or backup file exists.

## 2. Verification Timing

Verify checkpoints at these exact points:

- **Before a risky change:** Confirm the previous stable checkpoint exists and its identifier is recorded.
- **After a major milestone:** Confirm the new commit or backup is valid and relevant tests pass.
- **At phase completion:** Verify the checkpoint and record the final test results.
- **After rollback:** Verify restored files, configuration, startup, and affected functionality.
- **Before the final demonstration:** Confirm the final stable checkpoint and recovery instructions are available.

## 3. Git Checkpoint Verification

Run:

```powershell
cd C:\ChainVault
git status
git log -1 --oneline
git diff --check
```

Confirm:

- The intended checkpoint commit exists.
- The expected files are included.
- No secrets or sensitive evidence were committed.
- No unrelated user changes were overwritten.
- The relevant test results are recorded.

A clean Git working tree is desirable, but do not discard unrelated changes just to achieve one.

## 4. Backup Verification

For a filesystem backup:

1. Confirm the backup directory exists.
2. Confirm expected files are present.
3. Compare file counts or checksums where appropriate.
4. Confirm configuration templates are present without copying secrets into logs.
5. Restore into a separate temporary directory when practical.
6. Never overwrite the active project merely to test a backup.

For database backups, verify that the backup can be restored into a separate test database before treating it as a proven recovery point.

## 5. Recovery Test Procedure

Use an isolated recovery location, for example:

`C:\ChainVault-recovery-test` (or isolated test workspace directory)

Then:

1. Restore the selected checkpoint into the isolated location.
2. Verify required files and dependencies.
3. Use a test database and safe development configuration.
4. Run focused tests.
5. Run relevant regression tests.
6. Confirm application startup where the isolated setup supports it.
7. Record the result without modifying the original project.

Do not connect recovery tests to real evidence or a live blockchain account.

## 6. Recovery Success Criteria

A recovery test passes only when:

- Expected source files are restored.
- Configuration is valid without exposing secrets.
- The backend starts in the isolated environment.
- The database connection works against the designated test database.
- Blockchain tests pass against the intended development network.
- Relevant functional and regression tests pass.
- No original evidence or historical report was modified.

If an isolated recovery cannot be tested, record it as **Not Verified**, not Passed.

## 7. Failure Handling

If checkpoint verification fails:

1. Stop risky development.
2. Preserve the current project state.
3. Inspect the checkpoint and its metadata.
4. Select the most recent verified stable checkpoint.
5. Restore into isolation and retest.
6. Escalate before any destructive restoration.

Never delete the only known-good checkpoint while investigating a failure.

## 8. Recovery Log

Maintain:

`C:\ChainVault\docs\RECOVERY_LOG.md`

Record:

| Field | Required information |
|---|---|
| Checkpoint ID | Commit hash or backup identifier |
| Verification time | Local timestamp |
| Verification owner | Coding agent or project owner |
| Recovery location | Isolated test path |
| Tests executed | Actual commands and suites |
| Result | Passed, Failed, or Not Verified |
| Issues | Actual failures found |
| Follow-up | Required recovery action |

## 9. Final Rule

A checkpoint becomes **Verified Stable** only after its identity is recorded and its relevant tests pass. A backup that has never been restored and tested must not be described as a proven recovery point.

Do not start the next phase automatically. Follow the existing phase-boundary and approval policies.
