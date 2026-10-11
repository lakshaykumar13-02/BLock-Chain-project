# ChainVault — Environment & Configuration Management Policy

**Project Root:** `C:\ChainVault` (Local workspace path: `d:\parjaayi project\CHAINVAULT`)

## 1. Objective
Ensure that configuration, secrets, ports, service URLs, and environment-specific settings remain consistent, secure, and recoverable throughout development and testing.

## 2. Configuration Ownership
- **Coding Agent:** Inspects existing configuration, documents required variables, validates configuration loading, and maintains `.env.example`.
- **Project Owner:** Supplies and approves sensitive credentials and authorizes changes that affect persistent data or external resources.
- The agent must never invent credentials, silently change locked ports, or overwrite working configuration without verification.

## 3. Configuration Sources
Before modifying configuration, inspect:
- Root `.env.example` and `.gitignore`.
- Backend configuration files.
- Blockchain `hardhat.config.js` and package configuration.
- Blockchain service environment loading and port settings.
- Frontend API base URLs.
- Existing documentation and tests.

Treat the actual application configuration and registered routes as authoritative over outdated documentation.

## 4. Secrets Management
The following must remain outside source control:
- JWT signing secrets.
- Bootstrap administrator passwords.
- Blockchain private keys.
- Database credentials, where applicable.
- Production API keys or other confidential credentials.

Rules:
1. Read secrets from environment variables or an approved secrets-management mechanism.
2. Never hardcode real secrets in source files, frontend JavaScript, documentation, test fixtures, or screenshots.
3. Keep `.env.example` limited to variable names and safe placeholder values.
4. Check Git status and staged changes before committing.
5. If a real secret is exposed, stop, notify the Project Owner, and follow the secret-rotation and incident-response process. Deleting the visible copy alone is not sufficient.

## 5. Environment Separation
Clearly distinguish:
- Local development.
- Automated testing.
- Final demonstration.

Use the dedicated `chainvault_test` database for automated tests. Tests must not silently connect to or modify the development database.

Use only the local Hardhat development network for routine blockchain testing. Never substitute a real network or wallet without explicit approval.

## 6. Ports and Service URLs
Preserve the established defaults unless the actual configuration requires a documented change:
- Frontend: `http://127.0.0.1:5500`
- FastAPI: `http://127.0.0.1:8000`
- Hardhat RPC: `http://127.0.0.1:8545`

Inspect the actual blockchain service port rather than assuming one.

When a URL or port changes:
1. Update the relevant configuration source.
2. Check dependent frontend, backend, and blockchain service references.
3. Update documentation and tests.
4. Verify startup and health checks for the affected services.
5. Avoid exposing internal blockchain service endpoints to public interfaces.

## 7. Safe Configuration Changes
Before editing:
1. Inspect the current value and its consumers.
2. Record the current working state.
3. Create a checkpoint when required by existing policies.
4. Make the smallest necessary change.
5. Validate parsing and configuration loading.
6. Run focused tests, followed by relevant regression tests.

Do not replace a working `.env` with `.env.example`, regenerate keys unnecessarily, or overwrite contract addresses without confirming the deployment state.

## 8. Dependency and Version Control
- Preserve existing lockfiles.
- Do not run broad dependency upgrades as part of unrelated work.
- Do not use destructive upgrade or cleanup commands without reviewing their impact.
- Document necessary version changes and test affected components.
- Do not use `pip freeze` as a substitute for a reviewed dependency list.

## 9. Configuration Documentation
Maintain `docs/CONFIGURATION_REFERENCE.md` with:
- Variable name.
- Purpose.
- Required or optional status.
- Safe example, if applicable.
- Component that consumes it.
- Environment in which it is used.
- Whether changing it requires a restart, migration, or redeployment.

Never record actual secret values.

## 10. Acceptance Criteria
Configuration work is complete only when:
- Required variables are documented.
- Secret files are excluded from version control.
- Services load configuration correctly.
- Dependent URLs and ports agree.
- Tests use the intended test environment.
- Relevant startup and regression checks pass.
- Changes are documented and a checkpoint is created when required.

**STOP CONDITION:** If a configuration change could expose secrets, affect real evidence, alter persistent data, or connect to a real blockchain, stop and obtain the required approval.
