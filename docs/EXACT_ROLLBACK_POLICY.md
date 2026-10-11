# CHAINVAULT — EXACT ROLLBACK OWNERSHIP & TIMING POLICY

This policy extends the existing **Safe Execution & Rollback Policy**.

Project: `C:\ChainVault` (Local workspace path: `d:\parjaayi project\CHAINVAULT`)

The purpose is to define exactly:
- WHO detects a failure
- WHO decides rollback
- WHO performs rollback
- WHEN rollback must happen
- WHO verifies recovery
- WHEN user approval is required

---

# 1. ROLLBACK OWNERSHIP MODEL

ChainVault uses the following ownership model:

```text
┌──────────────────────────────┐
│ Coding Agent                 │
│ Detects + Diagnoses          │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ Rollback Decision            │
│ Agent for reversible changes │
│ User for destructive changes │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ Coding Agent                 │
│ Performs rollback            │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ Coding Agent                 │
│ Verifies recovery            │
└──────────────────────────────┘
```

---

# 2. OWNER DEFINITIONS

## Primary Owner

The **Coding Agent** owns:
- code changes
- configuration changes
- test execution
- failure detection
- diagnosis
- reversible rollback
- regression testing
- technical recovery verification

---

# 3. USER / PROJECT OWNER

The **Project Owner** owns decisions involving:
- real evidence
- irreversible deletion
- production data
- destructive database operations
- Git history destruction
- force push
- real wallet/private key
- real blockchain deployment
- irreversible infrastructure changes

The agent must NOT perform these operations without explicit approval.

---

# 4. ROLLBACK DECISION AUTHORITY

### Automatic rollback is authorized for:
- code changes
- frontend changes
- backend changes
- test changes
- local configuration changes
- local dependency changes
- documentation changes
- reversible local development changes

provided the rollback does not destroy user data.

### User approval is mandatory for:
- real evidence modification/deletion
- persistent database restoration
- destructive migration
- Git history rewrite
- force push
- real blockchain deployment rollback
- real wallet operation
- permanent filesystem deletion

---

# 5. SEVERITY LEVELS

Every failure must be classified immediately.

## SEV-1 — Critical

Examples:
- authentication bypass
- authorization bypass
- private key exposure
- JWT secret exposure
- password exposure
- arbitrary filesystem access
- evidence corruption
- database corruption
- incorrect forensic integrity result
- destructive data loss

Action:
- STOP IMMEDIATELY
- ROLLBACK IMMEDIATELY

Target:
- within 5 minutes of confirmed detection

No additional feature work may continue.

---

# 6. SEV-2 — Major

Examples:
- blockchain integration broken
- custody transfer incorrect
- evidence verification incorrect
- QR verification broken
- report generation corrupt
- core API unavailable
- authentication malfunction
- major regression

Action:
- STOP affected development
- diagnose
- rollback if the fix cannot be safely completed

Target rollback:
- within 15 minutes of confirmed failure

---

# 7. SEV-3 — Moderate

Examples:
- single endpoint failure
- frontend component failure
- non-critical validation issue
- incorrect error message
- report formatting issue
- minor API mismatch

Action:
- isolate affected component
- fix or rollback
- continue only after focused tests pass

Target:
- within 30 minutes of confirmed failure

---

# 8. SEV-4 — Minor

Examples:
- cosmetic UI issue
- documentation typo
- non-functional formatting issue
- minor layout problem

Action:
- record
- fix normally

Rollback is optional unless the change introduces a regression.

---

# 9. FAILURE DETECTION WINDOW

The agent must identify obvious failures during the current operation.

After any change:
- run focused validation immediately

Do not continue to unrelated work if:
- startup fails
- focused test fails
- security test fails
- critical endpoint fails

---

# 10. MANDATORY STOP CONDITIONS

The agent must stop immediately when:
- backend cannot start
- authentication stops working
- RBAC becomes weaker
- evidence hash changes unexpectedly
- evidence becomes corrupted
- blockchain state becomes inconsistent
- custody state becomes inconsistent
- private key appears in output/logs
- JWT secret appears in output/logs
- password appears in output/logs
- arbitrary file access is detected
- database corruption is detected
- critical tests fail

---

# 11. FIRST 5-MINUTE RESPONSE

For SEV-1:

### 0–1 minute
- STOP CURRENT CHANGE
- STOP RELATED TEST/PROCESS IF SAFE

### 1–2 minutes
Identify:
- last change
- affected files
- affected service
- affected data

### 2–3 minutes
Restore the last known stable state.

### 3–5 minutes
Run:
- health check
- focused security test
- affected functional test

If recovery fails:
- STOP
- ESCALATE TO PROJECT OWNER

---

# 12. SEV-2 RESPONSE

Within 15 minutes:
1. stop affected development
2. identify last known good state
3. inspect diff
4. rollback affected change
5. restart affected service
6. run focused tests
7. run related regression tests

Only continue development after the affected functionality is restored.

---

# 13. SEV-3 RESPONSE

Within 30 minutes:
1. isolate failure
2. inspect affected component
3. fix if low-risk
4. otherwise rollback
5. run focused test
6. run related regression test

No project-wide rollback is required unless the failure spreads beyond the affected component.

---

# 14. ROLLBACK SCOPE

Always use the smallest safe rollback.

Priority:
- Level 1: single function/file
- Level 2: single feature/module
- Level 3: single service
- Level 4: entire phase checkpoint

Never jump directly to:
- entire project reset

unless specifically authorized and necessary.

---

# 15. LAST KNOWN GOOD STATE

The last known good state is the most recent checkpoint where:
- application starts
- database connects
- blockchain connects
- authentication works
- critical workflow works
- security tests pass
- relevant regression tests pass

Record:
- Git commit
- timestamp
- phase
- test result

---

# 16. ROLLBACK OWNER BY COMPONENT

| Component | Primary Rollback Owner | Verification Owner |
|---|---|---|
| Frontend | Coding Agent | Coding Agent |
| FastAPI backend | Coding Agent | Coding Agent |
| Python dependencies | Coding Agent | Coding Agent |
| MongoDB schema/code | Coding Agent | Coding Agent |
| Test suite | Coding Agent | Coding Agent |
| QR subsystem | Coding Agent | Coding Agent |
| Report subsystem | Coding Agent | Coding Agent |
| Node blockchain service | Coding Agent | Coding Agent |
| Local Hardhat deployment | Coding Agent | Coding Agent |
| Solidity contract | Coding Agent + Project Owner approval for destructive/live action | Coding Agent |
| Real evidence | Project Owner | Project Owner + Coding Agent |
| Real database restoration | Project Owner approval | Coding Agent |
| Git history rewrite | Project Owner approval | Coding Agent |
| Real wallet/blockchain operation | Project Owner | Project Owner + Coding Agent |

---

# 17. DATABASE ROLLBACK OWNERSHIP

For the test database:
- Coding Agent may perform rollback automatically.

For development data containing meaningful project records:
- Project Owner approval required before destructive restoration.

For any real/production database:
- Project Owner is the final authority.

The agent may provide commands/instructions but must not execute destructive restoration without approval.

---

# 18. EVIDENCE ROLLBACK OWNERSHIP

Actual evidence is treated as immutable.

The agent must NEVER automatically:
- delete evidence
- replace evidence
- restore evidence from an arbitrary backup
- overwrite original evidence

If evidence integrity is affected:
- STOP
- MARK/REPORT THE CONDITION
- PRESERVE ORIGINAL STATE

Any restoration involving actual evidence requires Project Owner authorization.

---

# 19. BLOCKCHAIN ROLLBACK OWNERSHIP

### Local Hardhat development network
Coding Agent may restart/reset the local development blockchain when necessary.
However: MongoDB blockchain references must then be revalidated.

### Real/external blockchain
Project Owner approval is mandatory.
Blockchain transactions are generally not reversible.
The policy therefore treats blockchain rollback as:
- application-state rollback
- NOT blockchain-history deletion

Never claim that an on-chain transaction has been erased.

---

# 20. SMART CONTRACT ROLLBACK

If a Solidity change fails:
- restore previous source
- restore previous deployment configuration
- rerun contract tests

If a new contract was deployed:
- do not pretend the old deployment was modified

Record:
- old contract address
- new contract address
- deployment status

---

# 21. CONFIGURATION ROLLBACK

For `.env` or configuration changes:
- Coding Agent owns reversible rollback.

If rollback would expose or replace secrets:
- do not print secret values
- Restore the previous configuration securely.

Then verify:
- backend startup
- database connection
- blockchain connection
- frontend communication

---

# 22. DEPENDENCY ROLLBACK

If a dependency causes regression:
1. identify changed dependency
2. restore previous known-good version
3. reinstall
4. run affected tests
5. run complete regression suite

Do not randomly upgrade other packages.

---

# 23. GIT ROLLBACK

For normal local code changes:
- Coding Agent may revert its own uncommitted changes.

For committed history:
- `git revert` is preferred over destructive history rewriting.

Never automatically use:
- `git reset --hard`
- `git push --force`

for shared or important work. User approval is required for destructive Git history operations.

---

# 24. ROLLBACK VERIFICATION OWNER

The same agent that performs rollback must perform the initial technical verification.

Verification must include:
- startup
- health endpoint
- affected functionality
- focused tests
- related regression tests
- security tests where relevant

The Project Owner performs final acceptance for:
- real evidence
- persistent data restoration
- live blockchain state
- production-like deployment

---

# 25. ROLLBACK COMPLETION DEFINITION

A rollback is NOT complete merely because files were restored.

Rollback is complete only when:
- previous implementation restored
AND
- application starts
AND
- affected functionality works
AND
- relevant tests pass
AND
- no new security issue exists

---

# 26. ROLLBACK REPORT

After every SEV-1 or SEV-2 rollback, create/update:
`docs/ROLLBACK_LOG.md` (Mapped from `C:\ChainVault\docs\ROLLBACK_LOG.md`)

Record:
- Incident ID
- Date
- Time
- Severity
- Detected By
- Affected Component
- Last Known Good Checkpoint
- Failure
- Root Cause
- Rollback Action
- Rollback Start Time
- Rollback Completion Time
- Verification Result
- Remaining Impact
- Project Owner Notified

Never record secrets.

---

# 27. TIMESTAMP FORMAT

Use: `YYYY-MM-DD HH:mm:ss`
with the project's local development timezone where possible.

Example: `2026-10-07 01:32:14`

---

# 28. ESCALATION RULE

Escalate to the Project Owner immediately when:
- rollback fails
- data integrity is uncertain
- actual evidence may be affected
- database restoration is required
- real blockchain state may be affected
- private key exposure is suspected
- authentication bypass is suspected
- rollback requires destructive commands

The agent must not guess in these situations.

---

# 29. NO CONTINUATION AFTER CRITICAL FAILURE

After a SEV-1 incident:
DO NOT:
- continue Phase 13
- add unrelated features
- perform cleanup that may destroy evidence
- hide the failure
- mark tests as skipped

First:
- recover
- verify
- document

Then continue only after Project Owner acceptance where required.

---

# 30. FINAL ROLLBACK CHECKLIST

Before declaring recovery complete:
- [ ] Failure classified
- [ ] Correct owner identified
- [ ] Last known good state identified
- [ ] Rollback scope minimized
- [ ] Rollback performed
- [ ] Backend starts
- [ ] Database connects
- [ ] Blockchain connects
- [ ] Authentication works
- [ ] Affected endpoint works
- [ ] Relevant tests pass
- [ ] Security tests pass where applicable
- [ ] No data loss detected
- [ ] Rollback documented
- [ ] Project Owner notified if required

---

# 31. AUTHORITATIVE TIMING TABLE

| Severity | Detection Action | Rollback Target | Approval |
|---|---|---|---|
| SEV-1 Critical | Immediate | ≤ 5 min | Not required for reversible rollback |
| SEV-2 Major | Immediate | ≤ 15 min | Not required for reversible rollback |
| SEV-3 Moderate | Same work cycle | ≤ 30 min | Not normally required |
| SEV-4 Minor | Normal workflow | No fixed deadline | Not required |

These are **development response targets**, not guarantees.

---

# 32. FINAL RULE

When in doubt:
- STOP
- PRESERVE DATA
- DO NOT GUESS
- IDENTIFY LAST KNOWN GOOD STATE
- ROLLBACK THE SMALLEST SAFE CHANGE
- VERIFY
- DOCUMENT
- ESCALATE IF DESTRUCTIVE ACTION IS REQUIRED
