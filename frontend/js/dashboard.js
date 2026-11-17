// ChainVault Dashboard Controller
// Dynamic View Management, Multi-Tier Evidence Lifecycle, and Blockchain Auditing

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Session & Access Control Check
    const token = sessionStorage.getItem('access_token');
    if (!token) {
        console.warn('No active session token found. Redirecting to login.');
        window.location.href = 'login.html';
        return;
    }

    // 2. Dynamic User Profile Synchronization
    await syncUserProfile();

    // 3. Setup Sidebar Navigation Switching
    setupNavigation();

    // 4. Setup Action Buttons & Forms
    setupFormHandlers();

    // 5. Initial Load: Dashboard Overview
    try {
        await checkSystemStatus();
    } catch (e) {
        console.warn('System status check error:', e);
    }
    try {
        await loadDashboardOverview();
    } catch (e) {
        console.warn('Dashboard overview load error:', e);
    }
});

// Dynamic Authenticated User Profile Management
async function syncUserProfile() {
    let token = sessionStorage.getItem('access_token');
    let userRole = sessionStorage.getItem('role') || 'INVESTIGATOR';
    let userId = sessionStorage.getItem('user_id') || 'USR-UNASSIGNED';
    let username = sessionStorage.getItem('username') || '';
    let displayName = sessionStorage.getItem('display_name') || username || userId;

    // Immediately render current session values
    renderProfileUI(displayName, userId, username, userRole);

    // Fetch verified live profile from backend /api/auth/me
    try {
        const resp = await fetchCurrentUserProfile();
        if (resp.ok) {
            const profile = await resp.json();
            userId = profile.user_id || userId;
            username = profile.username || username;
            userRole = profile.role || userRole;
            displayName = profile.display_name || profile.full_name || username || userId;

            // Update sessionStorage with validated live data
            sessionStorage.setItem('user_id', userId);
            sessionStorage.setItem('username', username);
            sessionStorage.setItem('role', userRole);
            sessionStorage.setItem('display_name', displayName);

            renderProfileUI(displayName, userId, username, userRole);
        } else if (resp.status === 401 || resp.status === 403) {
            sessionStorage.clear();
            window.location.href = 'login.html';
            return;
        }
    } catch (e) {
        console.warn('Could not sync user profile from server, using cached session:', e);
    }
}

function renderProfileUI(displayName, userId, username, userRole) {
    // Header elements
    const badgeRole = document.getElementById('userBadgeRole');
    const badgeName = document.getElementById('userBadgeName');
    if (badgeRole) {
        const roleLabels = {
            'SUPER_ADMIN': 'Platform Owner',
            'ADMIN': 'Admin',
            'INVESTIGATOR': 'Investigator',
            'ANALYST': 'Analyst',
            'VIEWER': 'Viewer',
            'EMPLOYEE': 'Employee'
        };
        badgeRole.textContent = roleLabels[userRole] || userRole;
    }
    if (badgeName) {
        badgeName.textContent = displayName;
    }

    // Sidebar elements
    const sideName = document.getElementById('sidebarUserName');
    const sideId = document.getElementById('sidebarUserId');
    const sideRole = document.getElementById('sidebarUserRole');
    const sideAvatar = document.getElementById('sidebarUserAvatar');

    if (sideName) sideName.textContent = displayName;
    if (sideId) sideId.textContent = `${username || ''} (${userId || ''})`.trim();
    if (sideRole) sideRole.textContent = userRole;
    if (sideAvatar) {
        const initials = displayName.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase() || 'AD';
        sideAvatar.textContent = initials;
    }

    // Show Employees & Tasks nav item if user is ADMIN
    const empNavItem = document.getElementById('navItemEmployees');
    if (empNavItem) {
        empNavItem.style.display = (userRole === 'ADMIN') ? 'block' : 'none';
    }

    // Platform Owner quick switch link for SUPER_ADMIN
    const navLinksList = document.querySelector('.nav-links');
    if (userRole === 'SUPER_ADMIN' && navLinksList && !document.getElementById('navLinkSuperAdmin')) {
        const saNavEl = document.createElement('li');
        saNavEl.id = 'navLinkSuperAdmin';
        saNavEl.innerHTML = `<a href="superadmin.html" style="color:#a78bfa; font-weight:600;" title="Open Super Admin Platform Owner Console">⚡ Platform Owner</a>`;
        navLinksList.appendChild(saNavEl);
    }
}

// Toast Banner Notification
function showToast(message, type = 'success', durationMs = 4000) {
    const banner = document.getElementById('toastBanner');
    if (!banner) return;
    banner.textContent = message;
    banner.className = `toast-banner ${type}`;
    banner.style.display = 'block';

    setTimeout(() => {
        banner.style.display = 'none';
    }, durationMs);
}

// Modal Controllers
window.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
};

window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
};

// Setup Sidebar View Navigation
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-links a[data-view]');
    const views = document.querySelectorAll('.dashboard-view');
    const pageTitle = document.getElementById('pageTitle');

    const viewTitles = {
        'dashboard': 'Dashboard Overview',
        'cases': 'Forensic Cases Management',
        'evidence': 'Digital Evidence Ingestion & Verification',
        'blockchain': 'Blockchain Audit & Custody Handover',
        'reports': 'Forensic Reports (PDF & SHA-256)',
        'employees': 'Employee Accounts & Dispatched Tasks'
    };

    navLinks.forEach(link => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            const targetView = link.getAttribute('data-view');

            // Update Active Nav Link
            navLinks.forEach(l => l.parentElement.classList.remove('active'));
            link.parentElement.classList.add('active');

            // Toggle Active View Section
            views.forEach(v => v.classList.remove('active'));
            const activeSection = document.getElementById(`view-${targetView}`);
            if (activeSection) {
                activeSection.classList.add('active');
            }

            // Update Header Title
            if (pageTitle && viewTitles[targetView]) {
                pageTitle.textContent = viewTitles[targetView];
            }

            // Load Data for Active View
            try {
                if (targetView === 'dashboard') {
                    await loadDashboardOverview();
                } else if (targetView === 'cases') {
                    await loadCasesView();
                } else if (targetView === 'evidence') {
                    await loadEvidenceView();
                } else if (targetView === 'blockchain') {
                    await loadBlockchainView();
                } else if (targetView === 'reports') {
                    await loadReportsView();
                } else if (targetView === 'employees') {
                    await loadAdminEmployees();
                    await loadAdminTasks();
                }
            } catch (err) {
                console.error(`Error loading data for view ${targetView}:`, err);
            }
        });
    });

    // Logout Button
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            await logoutUser();
            window.location.href = 'login.html';
        });
    }
}

// Setup Form Submission & Toggle Listeners
function setupFormHandlers() {
    // Refresh button on Dashboard Overview
    const btnRefresh = document.getElementById('btnRefreshDashboard');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', async () => {
            await loadDashboardOverview();
            showToast('Dashboard overview refreshed.');
        });
    }

    // Edit Profile Modal handlers
    const btnEditProfile = document.getElementById('btnEditProfile');
    const sidebarUserCard = document.getElementById('sidebarUserCard');
    const userBadge = document.getElementById('userBadge');

    function openEditProfileModal() {
        const modal = document.getElementById('modalEditProfile');
        const usernameInput = document.getElementById('editProfileUsername');
        const displayInput = document.getElementById('editProfileDisplayName');
        const errorEl = document.getElementById('editProfileError');

        if (errorEl) {
            errorEl.style.display = 'none';
            errorEl.textContent = '';
        }
        if (usernameInput) {
            usernameInput.value = sessionStorage.getItem('username') || sessionStorage.getItem('user_id') || '';
        }
        if (displayInput) {
            displayInput.value = sessionStorage.getItem('display_name') || '';
        }
        if (modal) {
            modal.classList.add('active');
            if (displayInput) displayInput.focus();
        }
    }

    if (btnEditProfile) btnEditProfile.addEventListener('click', (e) => { e.stopPropagation(); openEditProfileModal(); });
    if (sidebarUserCard) sidebarUserCard.addEventListener('click', openEditProfileModal);
    if (userBadge) userBadge.addEventListener('click', openEditProfileModal);

    const formEditProfile = document.getElementById('formEditProfile');
    if (formEditProfile) {
        formEditProfile.addEventListener('submit', async (e) => {
            e.preventDefault();
            const displayInput = document.getElementById('editProfileDisplayName');
            const errorEl = document.getElementById('editProfileError');
            const newName = displayInput ? displayInput.value.trim() : '';

            if (!newName) {
                if (errorEl) {
                    errorEl.textContent = 'Display name cannot be empty.';
                    errorEl.style.display = 'block';
                }
                return;
            }

            try {
                const resp = await updateUserProfile(newName);
                if (resp.ok) {
                    const data = await resp.json();
                    const updatedName = data.display_name || data.full_name || newName;
                    sessionStorage.setItem('display_name', updatedName);
                    renderProfileUI(
                        updatedName,
                        sessionStorage.getItem('user_id'),
                        sessionStorage.getItem('username'),
                        sessionStorage.getItem('role')
                    );
                    closeModal('modalEditProfile');
                    showToast('Profile display name updated successfully.');
                } else {
                    const err = await resp.json().catch(() => ({}));
                    if (errorEl) {
                        errorEl.textContent = err.detail || 'Failed to update profile.';
                        errorEl.style.display = 'block';
                    }
                }
            } catch (err) {
                if (errorEl) {
                    errorEl.textContent = 'Network error updating profile.';
                    errorEl.style.display = 'block';
                }
            }
        });
    }

    // Toggle Create Case Card
    const btnToggleCreateCase = document.getElementById('btnToggleCreateCase');
    const createCaseCard = document.getElementById('createCaseCard');
    const btnCancelCreateCase = document.getElementById('btnCancelCreateCase');
    if (btnToggleCreateCase && createCaseCard) {
        btnToggleCreateCase.addEventListener('click', () => {
            const isHidden = createCaseCard.style.display === 'none';
            createCaseCard.style.display = isHidden ? 'block' : 'none';
        });
    }
    if (btnCancelCreateCase && createCaseCard) {
        btnCancelCreateCase.addEventListener('click', () => {
            createCaseCard.style.display = 'none';
        });
    }

    // Handle Create Case Form
    const createCaseForm = document.getElementById('createCaseForm');
    if (createCaseForm) {
        createCaseForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const caseId = document.getElementById('newCaseId').value.trim();
            const title = document.getElementById('newCaseTitle').value.trim();
            const desc = document.getElementById('newCaseDesc').value.trim();

            try {
                const res = await createCase({
                    case_id: caseId,
                    case_number: caseId,
                    title: title,
                    description: desc
                });

                if (res.ok) {
                    showToast(`Case ${caseId} created successfully!`);
                    createCaseForm.reset();
                    if (createCaseCard) createCaseCard.style.display = 'none';
                    await loadCasesView();
                } else {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Failed to create case', 'error');
                }
            } catch (err) {
                console.error('Case creation error:', err);
                showToast('Network error while creating case', 'error');
            }
        });
    }

    // Toggle Upload Evidence Card
    const btnToggleUpload = document.getElementById('btnToggleUploadEvidence');
    const uploadEvidenceCard = document.getElementById('uploadEvidenceCard');
    const btnCancelUpload = document.getElementById('btnCancelUpload');
    if (btnToggleUpload && uploadEvidenceCard) {
        btnToggleUpload.addEventListener('click', () => {
            const isHidden = uploadEvidenceCard.style.display === 'none';
            uploadEvidenceCard.style.display = isHidden ? 'block' : 'none';
        });
    }
    if (btnCancelUpload && uploadEvidenceCard) {
        btnCancelUpload.addEventListener('click', () => {
            uploadEvidenceCard.style.display = 'none';
        });
    }

    // Handle Upload Evidence Form
    const uploadEvidenceForm = document.getElementById('uploadEvidenceForm');
    if (uploadEvidenceForm) {
        uploadEvidenceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('uploadFile');
            const caseIdInput = document.getElementById('uploadCaseId');
            const evidenceIdInput = document.getElementById('uploadEvidenceId');
            const custodianInput = document.getElementById('uploadCustodian');

            if (!fileInput.files.length) {
                showToast('Please select a file to ingest', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('case_id', caseIdInput.value.trim());
            if (evidenceIdInput.value.trim()) {
                formData.append('evidence_id', evidenceIdInput.value.trim());
            }
            if (custodianInput.value.trim()) {
                formData.append('custodian', custodianInput.value.trim());
            }

            try {
                showToast('Streaming file & computing SHA-256 digest...', 'success');
                const res = await uploadEvidence(formData);
                if (res.ok) {
                    const data = await res.json();
                    showToast(`Evidence ${data.evidence_id} ingested! SHA-256: ${data.file_hash.slice(0, 16)}...`);
                    uploadEvidenceForm.reset();
                    if (uploadEvidenceCard) uploadEvidenceCard.style.display = 'none';
                    await loadEvidenceView();
                } else {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Evidence ingestion failed', 'error');
                }
            } catch (err) {
                console.error('Evidence upload error:', err);
                showToast('Upload network stream error', 'error');
            }
        });
    }

    // Handle Custody Transfer Form
    const custodyTransferForm = document.getElementById('custodyTransferForm');
    if (custodyTransferForm) {
        custodyTransferForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const evId = document.getElementById('transferEvidenceId').value.trim();
            const newCust = document.getElementById('transferNewCustodian').value.trim();
            const reason = document.getElementById('transferReason').value.trim();

            try {
                const res = await transferCustody(evId, newCust, reason);
                if (res.ok) {
                    const data = await res.json();
                    showToast(`Custody of ${evId} transferred to ${newCust}!`);
                    custodyTransferForm.reset();
                    // Auto-load audit history for this item
                    document.getElementById('auditQueryId').value = evId;
                    await loadAuditHistory(evId);
                } else {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Custody transfer failed', 'error');
                }
            } catch (err) {
                console.error('Custody transfer error:', err);
                showToast('Custody handover network error', 'error');
            }
        });
    }

    // Handle On-Chain Lookup Form
    const lookupChainForm = document.getElementById('lookupChainForm');
    if (lookupChainForm) {
        lookupChainForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const evId = document.getElementById('lookupEvidenceId').value.trim();
            const resultBox = document.getElementById('chainLookupResult');
            resultBox.innerHTML = '<p>Querying Ethereum smart contract...</p>';

            try {
                const res = await fetchOnChainEvidence(evId);
                if (res.ok) {
                    const d = await res.json();
                    resultBox.innerHTML = `
                        <div style="background:var(--primary-color); padding:0.75rem; border-radius:6px; border:1px solid var(--accent-color);">
                            <p><strong>Evidence ID:</strong> ${d.evidence_id}</p>
                            <p><strong>Case Reference:</strong> ${d.case_id || 'N/A'}</p>
                            <p><strong>On-Chain Hash:</strong> <span class="mono">${d.file_hash}</span></p>
                            <p><strong>Custodian:</strong> <span class="mono">${d.custodian}</span></p>
                            <p><strong>Transaction:</strong> <span class="mono">${d.tx_hash}</span></p>
                            <p><strong>Block Number:</strong> #${d.block_number}</p>
                            <p><strong>Smart Contract:</strong> <span class="mono">${d.contract_address}</span></p>
                        </div>
                    `;
                } else {
                    resultBox.innerHTML = `<p style="color:var(--danger);">Evidence item '${evId}' not found on-chain.</p>`;
                }
            } catch (err) {
                resultBox.innerHTML = '<p style="color:var(--danger);">Failed to query blockchain node.</p>';
            }
        });
    }

    // Handle Audit History Load Button
    const btnFetchAuditLogs = document.getElementById('btnFetchAuditLogs');
    if (btnFetchAuditLogs) {
        btnFetchAuditLogs.addEventListener('click', async () => {
            const evId = document.getElementById('auditQueryId').value.trim();
            if (!evId) {
                showToast('Please enter an Evidence ID to query', 'error');
                return;
            }
            await loadAuditHistory(evId);
        });
    }

    // Handle Audit Trail Verification Button
    const btnVerifyAuditTrail = document.getElementById('btnVerifyAuditTrail');
    if (btnVerifyAuditTrail) {
        btnVerifyAuditTrail.addEventListener('click', async () => {
            const evId = document.getElementById('auditQueryId').value.trim();
            if (!evId) {
                showToast('Please enter an Evidence ID to verify', 'error');
                return;
            }
            await handleVerifyAuditTrail(evId);
        });
    }

    // Handle Generate Report Form
    const generateReportForm = document.getElementById('generateReportForm');
    if (generateReportForm) {
        generateReportForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const caseId = document.getElementById('reportCaseId').value.trim();
            const title = document.getElementById('reportTitle').value.trim();

            showToast('Compiling tamper-evident PDF report via ReportLab...', 'success');
            try {
                const res = await generateReport(caseId, title);
                if (res.ok) {
                    const data = await res.json();
                    showToast(`Report compiled! SHA-256: ${data.report_hash.slice(0, 16)}...`);
                    await loadReportsView(caseId);
                } else {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Report generation failed', 'error');
                }
            } catch (err) {
                console.error('Report generation error:', err);
                showToast('Report compilation error', 'error');
            }
        });
    }
}

// System Status Indicator
async function checkSystemStatus() {
    const indicator = document.querySelector('.status-indicator');
    const statusText = document.getElementById('systemStatusText');
    const health = await checkApiHealth();

    if (health && health.status === 'ok') {
        if (indicator) {
            indicator.style.backgroundColor = 'var(--success)';
            indicator.style.boxShadow = '0 0 8px var(--success)';
        }
        if (statusText) statusText.textContent = 'Blockchain Network Active';
    } else {
        if (indicator) {
            indicator.style.backgroundColor = 'var(--danger)';
            indicator.style.boxShadow = '0 0 8px var(--danger)';
        }
        if (statusText) statusText.textContent = 'API Offline';
    }
}

// -------------------------------------------------------------
// VIEW 1: DASHBOARD OVERVIEW DATA LOADER
// -------------------------------------------------------------
async function loadDashboardOverview() {
    try {
        const [casesRes, evidenceRes, bcRes] = await Promise.all([
            fetchCases().catch(err => { console.warn('fetchCases error:', err); return null; }),
            fetchEvidence().catch(err => { console.warn('fetchEvidence error:', err); return null; }),
            fetchBlockchainStatus().catch(err => { console.warn('fetchBlockchainStatus error:', err); return null; })
        ]);

        let cases = [];
        let evidence = [];

        if (casesRes && casesRes.ok) {
            cases = await casesRes.json();
            const statCases = document.getElementById('statCases');
            if (statCases) statCases.textContent = cases.length;
        }
        if (evidenceRes && evidenceRes.ok) {
            evidence = await evidenceRes.json();
            const statEvidence = document.getElementById('statEvidence');
            if (statEvidence) statEvidence.textContent = evidence.length;
            const statVerified = document.getElementById('statVerified');
            if (statVerified) statVerified.textContent = evidence.length;
        }

        // Render Recent Evidence
        const tbody = document.getElementById('dashboardEvidenceTbody');
        if (tbody) {
            if (!evidence.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No evidence items registered yet. Use the Evidence tab to ingest records.</td></tr>';
            } else {
                tbody.innerHTML = evidence.slice(0, 5).map(ev => `
                    <tr>
                        <td><strong>${escapeHtml(ev.evidence_id)}</strong></td>
                        <td>${escapeHtml(ev.case_id)}</td>
                        <td><span class="mono">${escapeHtml((ev.file_hash || '').slice(0, 20))}...</span></td>
                        <td><span class="mono">${escapeHtml(ev.custodian || 'investigator1')}</span></td>
                        <td><span class="badge success">Registered</span></td>
                    </tr>
                `).join('');
            }
        }

        // Render Blockchain Status
        if (bcRes && bcRes.ok) {
            const bc = await bcRes.json();
            const bcNetwork = document.getElementById('bcNetwork');
            if (bcNetwork) bcNetwork.textContent = bc.network || 'Hardhat Localhost';
            const bcChainId = document.getElementById('bcChainId');
            if (bcChainId) bcChainId.textContent = bc.chain_id || '31337';
            const bcRpcUrl = document.getElementById('bcRpcUrl');
            if (bcRpcUrl) bcRpcUrl.textContent = bc.rpc_url || 'http://127.0.0.1:8545';
            const bcContract = document.getElementById('bcContract');
            if (bcContract) bcContract.textContent = (bc.contract_address || '').slice(0, 14) + '...';
            const bcStatus = document.getElementById('bcStatus');
            if (bcStatus) {
                bcStatus.textContent = bc.status === 'ok' ? 'Online' : bc.status;
                bcStatus.className = bc.status === 'ok' ? 'badge success' : 'badge danger';
            }
        }
    } catch (err) {
        console.error('Error loading dashboard overview:', err);
    }
}

// -------------------------------------------------------------
// VIEW 2: CASES VIEW DATA LOADER
// -------------------------------------------------------------
async function loadCasesView() {
    const tbody = document.getElementById('casesTableBody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Fetching cases from server...</td></tr>';

    try {
        const res = await fetchCases();
        if (res.ok) {
            const cases = await res.json();
            if (!cases.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No active cases registered. Click "+ Create Case" to begin.</td></tr>';
                return;
            }

            tbody.innerHTML = cases.map(c => `
                <tr>
                    <td><strong>${escapeHtml(c.case_id)}</strong></td>
                    <td>${escapeHtml(c.title)}</td>
                    <td>${escapeHtml(c.description || 'N/A')}</td>
                    <td>${escapeHtml((c.created_at || '').slice(0, 19).replace('T', ' '))}</td>
                    <td><span class="badge success">Active</span></td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state" style="color:var(--danger);">Failed to load cases.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state" style="color:var(--danger);">Error connecting to API.</td></tr>';
    }
}

// -------------------------------------------------------------
// VIEW 3: EVIDENCE VIEW DATA LOADER
// -------------------------------------------------------------
async function loadEvidenceView() {
    const tbody = document.getElementById('evidenceTableBody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Fetching evidence items...</td></tr>';

    try {
        const res = await fetchEvidence();
        if (res.ok) {
            const evidence = await res.json();
            if (!evidence.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No evidence records ingested yet. Click "+ Ingest Evidence" to upload.</td></tr>';
                return;
            }

            tbody.innerHTML = evidence.map(ev => {
                const sz = ev.file_size ? `${ev.file_size} B` : '0 B';
                const hTrunc = (ev.file_hash || '').slice(0, 18) + '...';
                const isReg = ev.blockchain_registered;

                return `
                    <tr>
                        <td><strong>${escapeHtml(ev.evidence_id)}</strong></td>
                        <td>${escapeHtml(ev.case_id)}</td>
                        <td>${escapeHtml(ev.filename || ev.stored_filename || 'evidence.bin')}</td>
                        <td>${sz}</td>
                        <td><span class="mono" title="${escapeHtml(ev.file_hash)}">${escapeHtml(hTrunc)}</span></td>
                        <td><span class="mono">${escapeHtml(ev.custodian || 'investigator1')}</span></td>
                        <td>
                            <div style="display:flex; gap:0.35rem;">
                                <button class="btn-sm btn-primary" onclick="handleVerifyTripartite('${escapeHtml(ev.evidence_id)}')">Verify</button>
                                <button class="btn-sm btn-outline" onclick="handleShowQr('${escapeHtml(ev.evidence_id)}')">QR Badge</button>
                                ${!isReg ? `<button class="btn-sm btn-success" onclick="handleAnchorEvidence('${escapeHtml(ev.evidence_id)}', '${escapeHtml(ev.file_hash)}', '${escapeHtml(ev.case_id)}')">Anchor</button>` : ''}
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state" style="color:var(--danger);">Failed to load evidence.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state" style="color:var(--danger);">Error connecting to API.</td></tr>';
    }
}

// -------------------------------------------------------------
// VIEW 4: BLOCKCHAIN AUDIT VIEW DATA LOADER
// -------------------------------------------------------------
async function loadBlockchainView() {
    // Populate default query if demo item exists
    const auditInput = document.getElementById('auditQueryId');
    if (auditInput && !auditInput.value) {
        auditInput.value = 'EV-DEMO-FORENSIC-001';
        await loadAuditHistory('EV-DEMO-FORENSIC-001');
    }
}

async function loadAuditHistory(evidenceId) {
    const tbody = document.getElementById('auditTableBody');
    const banner = document.getElementById('auditVerificationBanner');
    if (banner) banner.style.display = 'none';
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Querying audit trail for ' + escapeHtml(evidenceId) + '...</td></tr>';

    try {
        const res = await fetchAuditLogs(evidenceId);
        if (res.ok) {
            const data = await res.json();
            const logs = data.logs || [];
            if (!logs.length) {
                tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No audit transitions recorded for '${escapeHtml(evidenceId)}'.</td></tr>`;
                return;
            }

            tbody.innerHTML = logs.map((log, idx) => {
                const seq = log.sequence_number || (idx + 1);
                const evHash = log.event_hash ? `${log.event_hash.slice(0, 8)}...${log.event_hash.slice(-6)}` : 'N/A';
                const prevHash = log.previous_event_hash === 'GENESIS' ? '<span class="badge success" style="font-size:0.7rem;">GENESIS</span>' : (log.previous_event_hash ? `<span class="mono" style="font-size:0.75rem;">${log.previous_event_hash.slice(0, 6)}...</span>` : 'N/A');
                const anchor = log.anchor_reference || log.blockchain_tx;
                const anchorDisplay = (anchor && anchor !== '0x0' && anchor !== 'Pending')
                    ? `<span class="mono" style="font-size:0.75rem;" title="${escapeHtml(anchor)}">${escapeHtml(anchor.slice(0, 8))}...</span>`
                    : '<span style="color:var(--text-muted); font-size:0.75rem;">None</span>';

                return `
                    <tr>
                        <td><strong>#${seq}</strong></td>
                        <td><code style="font-size:0.75rem;">${escapeHtml(log.event_id || log.log_id || 'N/A')}</code></td>
                        <td><span class="badge ${log.action === 'CUSTODY_TRANSFER' ? 'success' : 'info'}">${escapeHtml(log.action)}</span></td>
                        <td><span class="mono">${escapeHtml(log.new_custodian || log.actor_id || 'System')}</span></td>
                        <td>${escapeHtml((log.timestamp || '').slice(0, 19).replace('T', ' '))}</td>
                        <td><span class="mono" style="font-size:0.75rem;" title="${escapeHtml(log.event_hash || '')}">${evHash}</span></td>
                        <td>${prevHash}</td>
                        <td>${anchorDisplay}</td>
                    </tr>
                `;
            }).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state" style="color:var(--danger);">Failed to retrieve audit records.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state" style="color:var(--danger);">Error connecting to API.</td></tr>';
    }
}

async function handleVerifyAuditTrail(evidenceId) {
    const banner = document.getElementById('auditVerificationBanner');
    const tbody = document.getElementById('auditTableBody');
    if (banner) {
        banner.style.display = 'block';
        banner.innerHTML = '<p style="margin:0; color:var(--text-light);">Recomputing canonical event hashes and validating predecessor chain links...</p>';
        banner.style.background = 'rgba(255,255,255,0.05)';
        banner.style.border = '1px solid var(--accent-color)';
    }

    try {
        const res = await verifyAuditTrail(evidenceId);
        if (res.ok) {
            const data = await res.json();
            const status = data.verification_status || (data.verified ? 'VERIFIED' : 'TAMPERED');

            let bannerBg = 'rgba(231,76,60,0.15)';
            let bannerBorder = 'var(--danger)';
            let bannerColor = 'var(--danger)';
            let bannerTitle = '⚠ AUDIT INTEGRITY VIOLATION DETECTED';

            if (status === 'VERIFIED') {
                bannerBg = 'rgba(46,204,113,0.15)';
                bannerBorder = 'var(--success)';
                bannerColor = 'var(--success)';
                bannerTitle = '✓ AUDIT TRAIL VERIFIED — ALL PREDECESSOR HASHES & CANONICAL DIGESTS VALID';
            } else if (status === 'INCONSISTENT') {
                bannerBg = 'rgba(241,196,15,0.15)';
                bannerBorder = 'var(--warning)';
                bannerColor = 'var(--warning)';
                bannerTitle = '⚡ STRUCTURAL INCONSISTENCY — SEQUENCE GAP OR UNANCHORED EVENT';
            } else if (status === 'TAMPERED') {
                bannerBg = 'rgba(231,76,60,0.15)';
                bannerBorder = 'var(--danger)';
                bannerColor = 'var(--danger)';
                bannerTitle = '⚠ TAMPERING DETECTED — EVENT CONTENT OR PREDECESSOR HASH MODIFIED';
            } else if (status === 'UNAVAILABLE') {
                bannerBg = 'rgba(231,76,60,0.15)';
                bannerBorder = 'var(--danger)';
                bannerColor = 'var(--danger)';
                bannerTitle = '🔌 BLOCKCHAIN OFFLINE — VERIFICATION FAILED CLOSED';
            } else if (status === 'NOT_FOUND') {
                bannerBg = 'rgba(149,165,166,0.15)';
                bannerBorder = '#95a5a6';
                bannerColor = '#95a5a6';
                bannerTitle = '🔍 EVIDENCE OR AUDIT RECORD NOT FOUND';
            }

            if (banner) {
                banner.style.display = 'block';
                banner.style.background = bannerBg;
                banner.style.border = `1px solid ${bannerBorder}`;
                banner.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
                        <div>
                            <strong style="color:${bannerColor}; font-size:0.95rem;">${bannerTitle}</strong>
                            <div style="margin-top:0.35rem; color:var(--text-light); font-size:0.8rem;">
                                Status: <strong style="color:${bannerColor};">${escapeHtml(status)}</strong>
                                &bull; Events Verified: <strong>${data.event_count || 0}</strong>
                                &bull; Hash Chain: <strong>${data.chain_intact ? 'Intact' : 'Broken'}</strong>
                                &bull; Blockchain Anchored: <strong>${data.blockchain_reconciled ? 'Reconciled' : 'Unconfirmed / Pending'}</strong>
                            </div>
                        </div>
                        <div>
                            ${data.technical_error ? `<span class="badge danger" style="font-size:0.75rem;">${escapeHtml(data.technical_error)}</span>` : '<span class="badge success" style="font-size:0.75rem;">ALL CHECKS PASSED</span>'}
                        </div>
                    </div>
                    ${data.failure_reason ? `
                        <div style="margin-top:0.5rem; padding:0.4rem 0.6rem; background:rgba(0,0,0,0.2); border-radius:4px; font-size:0.8rem; color:${bannerColor};">
                            <strong>Reason:</strong> ${escapeHtml(data.failure_reason)}
                        </div>
                    ` : ''}
                `;
            }

            // Render verified event rows with status indicators
            const events = data.events || [];
            if (tbody && events.length) {
                tbody.innerHTML = events.map(ev => {
                    const hashMatch = ev.hash_valid ? '✓ Valid' : '✗ Tampered';
                    const linkMatch = ev.link_valid ? '✓ Linked' : '✗ Broken';
                    const rowBorder = (!ev.hash_valid || !ev.link_valid) ? 'border-left: 3px solid var(--danger); background: rgba(231,76,60,0.05);' : '';

                    return `
                        <tr style="${rowBorder}">
                            <td><strong>#${ev.sequence_number}</strong></td>
                            <td><code style="font-size:0.75rem;">${escapeHtml(ev.event_id || 'N/A')}</code></td>
                            <td><span class="badge ${ev.action === 'CUSTODY_TRANSFER' ? 'success' : 'info'}">${escapeHtml(ev.action)}</span></td>
                            <td><span class="mono">${escapeHtml(ev.actor_id || 'System')}</span></td>
                            <td>${escapeHtml((ev.timestamp || '').slice(0, 19).replace('T', ' '))}</td>
                            <td>
                                <span class="badge ${ev.hash_valid ? 'success' : 'danger'}" style="font-size:0.7rem;" title="Stored: ${escapeHtml(ev.stored_event_hash)}&#10;Calculated: ${escapeHtml(ev.calculated_event_hash)}">
                                    ${hashMatch}
                                </span>
                            </td>
                            <td>
                                <span class="badge ${ev.link_valid ? 'success' : 'danger'}" style="font-size:0.7rem;">
                                    ${linkMatch}
                                </span>
                            </td>
                            <td>
                                ${ev.anchor_reference ? `<span class="mono" style="font-size:0.75rem;" title="${escapeHtml(ev.anchor_reference)}">${escapeHtml(ev.anchor_reference.slice(0, 8))}...</span>` : '<span style="color:var(--text-muted); font-size:0.75rem;">None</span>'}
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        } else {
            if (banner) {
                banner.style.display = 'block';
                banner.style.background = 'rgba(231,76,60,0.15)';
                banner.style.border = '1px solid var(--danger)';
                banner.innerHTML = '<p style="margin:0; color:var(--danger);">Audit verification endpoint returned an error response.</p>';
            }
        }
    } catch (err) {
        if (banner) {
            banner.style.display = 'block';
            banner.style.background = 'rgba(231,76,60,0.15)';
            banner.style.border = '1px solid var(--danger)';
            banner.innerHTML = '<p style="margin:0; color:var(--danger);">Network error during audit trail verification.</p>';
        }
    }
}


// -------------------------------------------------------------
// VIEW 5: FORENSIC REPORTS VIEW DATA LOADER
// -------------------------------------------------------------
async function loadReportsView(caseId = 'CV-DEMO-2026-001') {
    const inputCaseId = document.getElementById('reportCaseId');
    if (inputCaseId && !inputCaseId.value) {
        inputCaseId.value = caseId;
    }

    const tbody = document.getElementById('reportsTableBody');
    if (!tbody) return;

    try {
        const res = await fetchReportHistory(caseId);
        if (res.ok) {
            const reports = await res.json();
            if (!reports.length) {
                tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No compiled reports found for case '${escapeHtml(caseId)}'. Click "Compile Forensic PDF Report" above to generate one.</td></tr>`;
                return;
            }

            tbody.innerHTML = reports.map(r => `
                <tr>
                    <td><strong>${escapeHtml(r.report_id)}</strong></td>
                    <td>${escapeHtml(r.case_id)}</td>
                    <td>${escapeHtml(r.report_filename)}</td>
                    <td><span class="mono" title="${escapeHtml(r.report_hash)}">${escapeHtml((r.report_hash || '').slice(0, 20))}...</span></td>
                    <td>${escapeHtml((r.generated_at || '').slice(0, 19).replace('T', ' '))}</td>
                    <td>
                        <div style="display:flex; gap:0.35rem;">
                            <button class="btn-sm btn-success" onclick="handleDownloadReport('${escapeHtml(r.report_filename)}')">Download</button>
                            <button class="btn-sm btn-primary" onclick="handleVerifyReport('${escapeHtml(r.report_id)}')">Verify</button>
                            <button class="btn-sm btn-outline" onclick="handleShowReportQr('${escapeHtml(r.report_id)}')">QR</button>
                        </div>
                    </td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No report history available yet.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Unable to query reports list.</td></tr>';
    }
}

// -------------------------------------------------------------
// ACTION HANDLERS (CALLED FROM HTML ROW BUTTONS)
// -------------------------------------------------------------

// Tripartite Verification Action
window.handleVerifyTripartite = async function(evidenceId) {
    const modalContent = document.getElementById('verifyModalContent');
    const modalTitle = document.getElementById('verifyModalTitle');
    modalTitle.textContent = `Tripartite Verification: ${evidenceId}`;
    modalContent.innerHTML = '<p>Recomputing fresh SHA-256 from disk, MongoDB metadata, and Ethereum ledger...</p>';
    openModal('verifyModal');

    try {
        const res = await verifyEvidence(evidenceId);
        if (res.ok) {
            const data = await res.json();
            const status = data.verification_status || (data.verified ? 'VERIFIED' : 'TAMPERED');
            const comparisons = data.comparisons || {};
            const fileVsDb = data.file_vs_database ?? comparisons.file_vs_database ?? false;
            const fileVsChain = data.file_vs_blockchain ?? comparisons.file_vs_blockchain ?? false;
            const dbVsChain = data.database_vs_blockchain ?? comparisons.database_vs_blockchain ?? false;

            let bannerBg = 'rgba(231,76,60,0.15)';
            let bannerBorder = 'var(--danger)';
            let bannerColor = 'var(--danger)';
            let bannerText = '⚠ INTEGRITY VIOLATION DETECTED';

            if (status === 'VERIFIED') {
                bannerBg = 'rgba(46,204,113,0.15)';
                bannerBorder = 'var(--success)';
                bannerColor = 'var(--success)';
                bannerText = '✓ INTEGRITY CONFIRMED — ALL THREE HASHES MATCH';
            } else if (status === 'INCONSISTENT') {
                bannerBg = 'rgba(241,196,15,0.15)';
                bannerBorder = 'var(--warning)';
                bannerColor = 'var(--warning)';
                bannerText = '⚡ DATABASE INCONSISTENCY — LEDGER MISMATCH';
            } else if (status === 'TAMPERED') {
                bannerBg = 'rgba(231,76,60,0.15)';
                bannerBorder = 'var(--danger)';
                bannerColor = 'var(--danger)';
                bannerText = '⚠ TAMPERING DETECTED — FILE & LEDGER MISMATCH';
            } else if (status === 'UNAVAILABLE') {
                bannerBg = 'rgba(231,76,60,0.15)';
                bannerBorder = 'var(--danger)';
                bannerColor = 'var(--danger)';
                bannerText = '🔌 BLOCKCHAIN OFFLINE — VERIFICATION FAILED CLOSED';
            } else if (status === 'NOT_FOUND') {
                bannerBg = 'rgba(149,165,166,0.15)';
                bannerBorder = '#95a5a6';
                bannerColor = '#95a5a6';
                bannerText = '🔍 EVIDENCE RECORD NOT FOUND';
            }

            modalContent.innerHTML = `
                <div style="text-align:center; padding: 0.75rem 0.5rem; margin-bottom: 1rem; border-radius:6px; background:${bannerBg}; border: 1px solid ${bannerBorder};">
                    <h4 style="color:${bannerColor}; margin:0; font-size:1rem; letter-spacing:0.5px;">
                        ${bannerText}
                    </h4>
                    <div style="margin-top:0.35rem; font-size:0.8rem; color:var(--text-light);">
                        Status: <strong style="color:${bannerColor};">${escapeHtml(status)}</strong>
                        ${data.technical_error ? ` &bull; Code: <code>${escapeHtml(data.technical_error)}</code>` : ''}
                    </div>
                </div>

                <ul class="verify-checklist">
                    <li>
                        <span><strong>1. Physical Disk Hash:</strong></span>
                        <span class="mono" style="font-size:0.75rem;">${escapeHtml(data.physical_file_hash || 'N/A (Missing from disk)')}</span>
                    </li>
                    <li>
                        <span><strong>2. Database Recorded Hash:</strong></span>
                        <span class="mono" style="font-size:0.75rem;">${escapeHtml(data.database_hash || 'N/A (Not found in DB)')}</span>
                    </li>
                    <li>
                        <span><strong>3. Blockchain Ledger Hash:</strong></span>
                        <span class="mono" style="font-size:0.75rem;">${escapeHtml(data.blockchain_hash || 'N/A (Unregistered or Offline)')}</span>
                    </li>
                    <li>
                        <span><strong>Physical == Database:</strong></span>
                        <span class="badge ${fileVsDb ? 'success' : 'danger'}">${fileVsDb ? 'Match' : 'Mismatch'}</span>
                    </li>
                    <li>
                        <span><strong>Physical == Blockchain:</strong></span>
                        <span class="badge ${fileVsChain ? 'success' : 'danger'}">${fileVsChain ? 'Match' : 'Mismatch'}</span>
                    </li>
                    <li>
                        <span><strong>Database == Blockchain:</strong></span>
                        <span class="badge ${dbVsChain ? 'success' : 'danger'}">${dbVsChain ? 'Match' : 'Mismatch'}</span>
                    </li>
                    <li>
                        <span><strong>Blockchain Ledger Verified:</strong></span>
                        <span class="badge ${data.blockchain_verified ? 'success' : 'neutral'}">${data.blockchain_verified ? 'Yes (On-Chain)' : 'No (Pending/Unreachable)'}</span>
                    </li>
                </ul>

                <div style="margin-top:1rem; padding:0.75rem; background:rgba(255,255,255,0.03); border-radius:6px; font-size:0.82rem; border-left:3px solid ${bannerBorder};">
                    <div style="font-weight:600; margin-bottom:0.25rem; color:var(--text-color);">Verification Explanation:</div>
                    <div style="color:var(--text-light); line-height:1.4;">${escapeHtml(data.explanation || 'Verification completed.')}</div>
                    ${data.contract_address ? `
                        <div style="margin-top:0.5rem; font-size:0.75rem; color:var(--text-muted);">
                            Chain ID: <code>${escapeHtml(String(data.chain_id || '31337'))}</code> &bull; Contract: <code>${escapeHtml(data.contract_address)}</code>
                        </div>
                    ` : ''}
                </div>
            `;
        } else {
            modalContent.innerHTML = '<p style="color:var(--danger);">Verification endpoint returned an error response.</p>';
        }
    } catch (err) {
        modalContent.innerHTML = '<p style="color:var(--danger);">Network error during tripartite verification.</p>';
    }
};

// QR Badge Preview Action
window.handleShowQr = function(evidenceId) {
    const modalImg = document.getElementById('qrModalImg');
    const modalDesc = document.getElementById('qrModalDesc');
    const modalTitle = document.getElementById('qrModalTitle');

    modalTitle.textContent = `QR Verification Badge: ${evidenceId}`;
    modalImg.src = `${API_BASE_URL}/reports/qr/${encodeURIComponent(evidenceId)}?t=${Date.now()}`;
    modalDesc.textContent = `Direct URI: http://localhost:8000/api/verification/verify?evidence_id=${evidenceId}`;
    openModal('qrModal');
};

// Report QR Badge Preview Action
window.handleShowReportQr = function(reportId) {
    const modalImg = document.getElementById('qrModalImg');
    const modalDesc = document.getElementById('qrModalDesc');
    const modalTitle = document.getElementById('qrModalTitle');

    modalTitle.textContent = `QR Report Verification: ${reportId}`;
    modalImg.src = `${API_BASE_URL}/reports/qr/report/${encodeURIComponent(reportId)}?t=${Date.now()}`;
    modalDesc.textContent = `Direct URI: http://localhost:8000/api/reports/verify/${reportId}`;
    openModal('qrModal');
};

// Verify Report Action
window.handleVerifyReport = async function(reportId) {
    const modalTitle = document.getElementById('verifyModalTitle');
    const modalContent = document.getElementById('verifyModalContent');

    modalTitle.textContent = `Report Verification: ${reportId}`;
    modalContent.innerHTML = '<p>Verifying report SHA-256 bitstream checksum and current evidence state...</p>';
    openModal('verifyModal');

    try {
        const res = await verifyReport(reportId);
        if (res.ok) {
            const data = await res.json();
            const status = data.report_verification_status || 'UNKNOWN';
            const pdfIntact = data.pdf_integrity && data.pdf_integrity.checksum_matches;

            let bannerBg = 'rgba(46,204,113,0.15)';
            let bannerBorder = 'var(--success)';
            let bannerColor = 'var(--success)';
            let bannerText = '✔ REPORT CHECKSUM & INTEGRITY VERIFIED';

            if (status === 'TAMPERED') {
                bannerBg = 'rgba(231,76,60,0.15)';
                bannerBorder = 'var(--danger)';
                bannerColor = 'var(--danger)';
                bannerText = '⚠ REPORT TAMPERING DETECTED';
            } else if (status === 'INCONSISTENT') {
                bannerBg = 'rgba(241,196,15,0.15)';
                bannerBorder = 'var(--warning)';
                bannerColor = 'var(--warning)';
                bannerText = '⚡ REPORT DATA INCONSISTENCY DETECTED';
            } else if (status === 'UNAVAILABLE') {
                bannerBg = 'rgba(231,76,60,0.15)';
                bannerBorder = 'var(--danger)';
                bannerColor = 'var(--danger)';
                bannerText = '🔌 VERIFICATION INFRASTRUCTURE OFFLINE';
            } else if (status === 'NOT_FOUND') {
                bannerBg = 'rgba(149,165,166,0.15)';
                bannerBorder = '#95a5a6';
                bannerColor = '#95a5a6';
                bannerText = '🔍 REPORT RECORD NOT FOUND';
            }

            modalContent.innerHTML = `
                <div style="text-align:center; padding: 0.75rem 0.5rem; margin-bottom: 1rem; border-radius:6px; background:${bannerBg}; border: 1px solid ${bannerBorder};">
                    <h4 style="color:${bannerColor}; margin:0; font-size:1rem; letter-spacing:0.5px;">
                        ${bannerText}
                    </h4>
                    <div style="margin-top:0.35rem; font-size:0.8rem; color:var(--text-light);">
                        Status: <strong style="color:${bannerColor};">${escapeHtml(status)}</strong>
                        ${data.technical_error ? ` &bull; Code: <code>${escapeHtml(data.technical_error)}</code>` : ''}
                    </div>
                </div>

                <ul class="verify-checklist">
                    <li>
                        <span><strong>PDF File Checksum Matches:</strong></span>
                        <span class="badge ${pdfIntact ? 'success' : 'danger'}">${pdfIntact ? 'INTACT' : 'MODIFIED/TAMPERED'}</span>
                    </li>
                    <li>
                        <span><strong>Recorded SHA-256:</strong></span>
                        <span class="mono" style="font-size:0.7rem;">${escapeHtml(data.pdf_integrity?.recorded_sha256 || 'N/A')}</span>
                    </li>
                    <li>
                        <span><strong>Current SHA-256:</strong></span>
                        <span class="mono" style="font-size:0.7rem;">${escapeHtml(data.pdf_integrity?.current_sha256 || 'N/A')}</span>
                    </li>
                    ${data.evidence_integrity ? `
                        <li>
                            <span><strong>Current Evidence Status:</strong></span>
                            <span class="badge ${data.evidence_integrity.evidence_verified ? 'success' : 'warning'}">${escapeHtml(data.evidence_integrity.current_status)}</span>
                        </li>
                        <li>
                            <span><strong>Findings Match Report:</strong></span>
                            <span class="badge ${data.evidence_integrity.findings_match_report ? 'success' : 'danger'}">${data.evidence_integrity.findings_match_report ? 'Match' : 'Evidence Changed'}</span>
                        </li>
                    ` : ''}
                </ul>

                <div style="margin-top:1rem; padding:0.75rem; background:rgba(255,255,255,0.03); border-radius:6px; font-size:0.82rem; border-left:3px solid ${bannerBorder};">
                    <div style="font-weight:600; margin-bottom:0.25rem; color:var(--text-color);">Explanation & Disclaimer:</div>
                    <div style="color:var(--text-light); line-height:1.4;">${escapeHtml(data.explanation || 'Report verification finished.')}</div>
                    <div style="margin-top:0.5rem; font-size:0.7rem; color:var(--text-muted); font-style:italic;">
                        ${escapeHtml(data.pdf_integrity?.disclaimer || '')}
                    </div>
                </div>
            `;
        } else {
            modalContent.innerHTML = '<p style="color:var(--danger);">Report verification endpoint returned an error response.</p>';
        }
    } catch (err) {
        modalContent.innerHTML = '<p style="color:var(--danger);">Network error during report verification.</p>';
    }
};

// Anchor Evidence On-Chain
window.handleAnchorEvidence = async function(evidenceId, fileHash, caseId) {
    if (!confirm(`Anchor cryptographic hash of ${evidenceId} to Ethereum blockchain?`)) {
        return;
    }
    showToast('Registering on Ethereum smart contract...', 'success');
    try {
        const res = await registerEvidenceOnChain(evidenceId, fileHash, caseId);
        if (res.ok) {
            const data = await res.json();
            showToast(`Evidence anchored! Block #${data.block_number}, TX: ${data.tx_hash.slice(0, 16)}...`);
            await loadEvidenceView();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || 'Blockchain registration failed', 'error');
        }
    } catch (err) {
        showToast('Network error during on-chain registration', 'error');
    }
};

// Download Report Action
window.handleDownloadReport = async function(filename) {
    showToast(`Downloading forensic PDF: ${filename}...`, 'success');
    try {
        await downloadReportFile(filename);
        showToast('Download complete.');
    } catch (err) {
        console.error('Download error:', err);
        showToast('Failed to download report PDF', 'error');
    }
};

// HTML Entity Escaping Utility
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// =============================================================================
// ADMIN EMPLOYEE & TASK MANAGEMENT CONTROLLERS
// =============================================================================

let adminEmployeesList = [];

async function loadAdminEmployees() {
    const tbody = document.getElementById('employeesTableBody');
    if (!tbody) return;

    try {
        const resp = await fetchAdminEmployees();
        if (resp.ok) {
            adminEmployeesList = await resp.json();
            renderAdminEmployeesTable();
            populateTaskAssigneeDropdown();
        } else {
            tbody.innerHTML = `<tr><td colspan="6" class="empty-state" style="color:#f87171;">Failed to load employee accounts.</td></tr>`;
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state" style="color:#f87171;">Network error loading employee accounts.</td></tr>`;
    }
}

function renderAdminEmployeesTable() {
    const tbody = document.getElementById('employeesTableBody');
    if (!tbody) return;

    if (adminEmployeesList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No employee accounts provisioned yet. Click "+ New Employee" above.</td></tr>`;
        return;
    }

    tbody.innerHTML = adminEmployeesList.map(emp => {
        const statusBadge = emp.is_active
            ? `<span style="background:rgba(16,185,129,0.15); color:#10b981; padding:0.2rem 0.5rem; border-radius:4px; font-size:0.75rem; font-weight:700;">ACTIVE</span>`
            : `<span style="background:rgba(239,68,68,0.15); color:#f87171; padding:0.2rem 0.5rem; border-radius:4px; font-size:0.75rem; font-weight:700;">INACTIVE</span>`;
        const toggleText = emp.is_active ? 'Deactivate' : 'Activate';
        const toggleClass = emp.is_active ? 'btn-outline' : 'btn-primary';
        const created = emp.created_at ? new Date(emp.created_at).toLocaleDateString() : '--';

        return `
            <tr>
                <td><strong>${escapeHtml(emp.username)}</strong></td>
                <td>${escapeHtml(emp.display_name || emp.full_name || '--')}</td>
                <td><code>${escapeHtml(emp.user_id || '--')}</code></td>
                <td>${statusBadge}</td>
                <td>${created}</td>
                <td>
                    <button class="btn-sm ${toggleClass}" onclick="handleToggleEmployeeStatus('${emp.username}', ${emp.is_active})" style="margin-right:0.3rem;">${toggleText}</button>
                    <button class="btn-sm btn-outline" onclick="handleResetEmployeePassword('${emp.username}')" style="margin-right:0.3rem;">Reset Pwd</button>
                    <button class="btn-sm btn-outline" style="border-color:#ef4444; color:#ef4444;" onclick="handleDeleteEmployee('${emp.username}')">Remove</button>
                </td>
            </tr>
        `;
    }).join('');
}

function populateTaskAssigneeDropdown() {
    const select = document.getElementById('taskAssignee');
    if (!select) return;

    const activeEmployees = adminEmployeesList.filter(e => e.is_active);
    select.innerHTML = '<option value="">Select an employee...</option>' +
        activeEmployees.map(e => `<option value="${escapeHtml(e.username)}">${escapeHtml(e.display_name || e.username)} (${escapeHtml(e.username)})</option>`).join('');
}

async function populateTaskCaseDropdown() {
    const select = document.getElementById('taskCaseId');
    if (!select) return;

    try {
        const resp = await fetchCases();
        if (resp.ok) {
            const cases = await resp.json();
            select.innerHTML = '<option value="">Select a case...</option>' +
                cases.map(c => `<option value="${escapeHtml(c.case_id)}">${escapeHtml(c.case_id)} — ${escapeHtml(c.title)}</option>`).join('');
        }
    } catch (e) {}
}

async function loadAdminTasks() {
    const tbody = document.getElementById('adminTasksTableBody');
    if (!tbody) return;

    try {
        const resp = await fetchTasks();
        if (resp.ok) {
            const tasks = await resp.json();
            renderAdminTasksTable(tasks);
        } else {
            tbody.innerHTML = `<tr><td colspan="8" class="empty-state" style="color:#f87171;">Failed to load dispatched tasks.</td></tr>`;
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state" style="color:#f87171;">Network error loading tasks.</td></tr>`;
    }
}

function renderAdminTasksTable(tasks) {
    const tbody = document.getElementById('adminTasksTableBody');
    if (!tbody) return;

    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No operational tasks dispatched yet. Click "+ Dispatch New Task" above.</td></tr>`;
        return;
    }

    tbody.innerHTML = tasks.map(t => {
        const priorityColors = {
            'HIGH': '#f87171',
            'CRITICAL': '#ef4444',
            'MEDIUM': '#fbbf24',
            'LOW': '#94a3b8'
        };
        const statusColors = {
            'ASSIGNED': '#fbbf24',
            'IN_PROGRESS': '#38bdf8',
            'COMPLETED': '#10b981',
            'BLOCKED': '#f87171'
        };

        const pColor = priorityColors[t.priority] || '#94a3b8';
        const sColor = statusColors[t.status] || '#94a3b8';
        const updated = t.updated_at ? new Date(t.updated_at).toLocaleString() : '--';
        const percent = Math.min(100, Math.max(0, t.progress_percent || 0));

        return `
            <tr>
                <td><code>${escapeHtml(t.task_id)}</code></td>
                <td><strong>${escapeHtml(t.title)}</strong></td>
                <td><span style="background:rgba(56,189,248,0.12); color:#38bdf8; padding:0.15rem 0.4rem; border-radius:4px; font-size:0.75rem;">${escapeHtml(t.case_id)}</span></td>
                <td>${escapeHtml(t.assigned_to_username)}</td>
                <td><span style="color:${pColor}; font-weight:700; font-size:0.75rem;">${escapeHtml(t.priority || 'MEDIUM')}</span></td>
                <td><span style="color:${sColor}; font-weight:700; font-size:0.75rem;">${escapeHtml(t.status || 'ASSIGNED')}</span></td>
                <td>
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        <div style="flex:1; background:#1e293b; height:6px; border-radius:3px; overflow:hidden;">
                            <div style="width:${percent}%; background:#10b981; height:100%;"></div>
                        </div>
                        <span style="font-size:0.75rem; color:#94a3b8;">${percent}%</span>
                    </div>
                </td>
                <td style="font-size:0.75rem; color:#94a3b8;">${updated}</td>
            </tr>
        `;
    }).join('');
}

window.handleToggleEmployeeStatus = async function(username, currentActive) {
    const action = currentActive ? 'deactivate' : 'activate';
    if (!confirm(`Are you sure you want to ${action} Employee account "${username}"?`)) return;

    try {
        const resp = await updateAdminEmployeeStatus(username, !currentActive);
        if (resp.ok) {
            showToast(`Employee "${username}" successfully ${action}d.`, 'success');
            await loadAdminEmployees();
        } else {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || `Failed to ${action} employee.`, 'error');
        }
    } catch (e) {
        showToast(`Network error updating employee.`, 'error');
    }
};

window.handleResetEmployeePassword = async function(username) {
    const newPwd = prompt(`Enter new password for Employee "${username}" (min 8 characters):`);
    if (!newPwd) return;

    if (newPwd.length < 8) {
        alert('Password must be at least 8 characters long.');
        return;
    }

    try {
        const resp = await resetAdminEmployeePassword(username, newPwd);
        if (resp.ok) {
            showToast(`Password for "${username}" has been reset and prior sessions revoked.`, 'success');
        } else {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || 'Failed to reset password.', 'error');
        }
    } catch (e) {
        showToast('Network error resetting password.', 'error');
    }
};

window.handleDeleteEmployee = async function(username) {
    if (!confirm(`CAUTION: Are you sure you want to permanently remove Employee "${username}"?`)) return;

    try {
        const resp = await removeAdminEmployee(username, true);
        if (resp.ok) {
            showToast(`Employee "${username}" has been safely removed.`, 'success');
            await loadAdminEmployees();
        } else {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || 'Failed to delete employee.', 'error');
        }
    } catch (e) {
        showToast('Network error deleting employee.', 'error');
    }
};

// Wire Admin Modals & Form Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Open Modal buttons
    document.getElementById('btnOpenCreateEmployee')?.addEventListener('click', () => {
        const errEl = document.getElementById('createEmployeeError');
        if (errEl) errEl.style.display = 'none';
        document.getElementById('formCreateEmployee')?.reset();
        openModal('modalCreateEmployee');
    });

    document.getElementById('btnOpenCreateTask')?.addEventListener('click', async () => {
        const errEl = document.getElementById('createTaskError');
        if (errEl) errEl.style.display = 'none';
        document.getElementById('formCreateTask')?.reset();
        await populateTaskCaseDropdown();
        populateTaskAssigneeDropdown();
        openModal('modalCreateTask');
    });

    // Refresh buttons
    document.getElementById('btnRefreshEmployees')?.addEventListener('click', loadAdminEmployees);
    document.getElementById('btnRefreshAdminTasks')?.addEventListener('click', loadAdminTasks);

    // Form: Create Employee
    document.getElementById('formCreateEmployee')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('newEmpUsername').value.trim();
        const fullName = document.getElementById('newEmpFullName').value.trim();
        const password = document.getElementById('newEmpPassword').value;
        const errEl = document.getElementById('createEmployeeError');

        try {
            const resp = await createAdminEmployee({
                username: username,
                full_name: fullName,
                password: password
            });

            if (resp.ok) {
                closeModal('modalCreateEmployee');
                showToast(`Employee "${username}" provisioned successfully.`, 'success');
                await loadAdminEmployees();
            } else {
                const err = await resp.json().catch(() => ({}));
                if (errEl) {
                    errEl.textContent = err.detail || 'Failed to create employee.';
                    errEl.style.display = 'block';
                }
            }
        } catch (err) {
            if (errEl) {
                errEl.textContent = 'Network error provisioning employee.';
                errEl.style.display = 'block';
            }
        }
    });

    // Form: Create Task
    document.getElementById('formCreateTask')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const title = document.getElementById('taskTitle').value.trim();
        const assignee = document.getElementById('taskAssignee').value;
        const caseId = document.getElementById('taskCaseId').value;
        const evidenceStr = document.getElementById('taskEvidenceIds').value.trim();
        const priority = document.getElementById('taskPriority').value;
        const description = document.getElementById('taskDescription').value.trim();
        const errEl = document.getElementById('createTaskError');

        const evidenceIds = evidenceStr
            ? evidenceStr.split(',').map(s => s.trim()).filter(s => s.length > 0)
            : [];

        try {
            const resp = await createTask({
                title: title,
                assigned_to_username: assignee,
                case_id: caseId,
                permitted_evidence_ids: evidenceIds,
                priority: priority,
                description: description
            });

            if (resp.ok) {
                closeModal('modalCreateTask');
                showToast(`Task dispatched to "${assignee}" successfully.`, 'success');
                await loadAdminTasks();
            } else {
                const err = await resp.json().catch(() => ({}));
                if (errEl) {
                    errEl.textContent = err.detail || 'Failed to dispatch task.';
                    errEl.style.display = 'block';
                }
            }
        } catch (err) {
            if (errEl) {
                errEl.textContent = 'Network error dispatching task.';
                errEl.style.display = 'block';
            }
        }
    });
});
