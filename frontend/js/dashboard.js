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

    // Populate User Badge Info
    const userRole = sessionStorage.getItem('role') || 'INVESTIGATOR';
    const userId = sessionStorage.getItem('user_id') || 'investigator1';
    const badgeRole = document.getElementById('userBadgeRole');
    const badgeName = document.getElementById('userBadgeName');
    if (badgeRole) badgeRole.textContent = userRole;
    if (badgeName) badgeName.textContent = userId;

    // 2. Setup Sidebar Navigation Switching
    setupNavigation();

    // 3. Setup Action Buttons & Forms
    setupFormHandlers();

    // 4. Initial Load: Dashboard Overview
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
        'reports': 'Forensic Reports (PDF & SHA-256)'
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
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Querying audit logs for ' + escapeHtml(evidenceId) + '...</td></tr>';

    try {
        const res = await fetchAuditLogs(evidenceId);
        if (res.ok) {
            const data = await res.json();
            const logs = data.logs || [];
            if (!logs.length) {
                tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No audit transitions recorded for '${escapeHtml(evidenceId)}'.</td></tr>`;
                return;
            }

            tbody.innerHTML = logs.map(log => `
                <tr>
                    <td><strong>${escapeHtml(log.log_id)}</strong></td>
                    <td><span class="badge ${log.action === 'CUSTODY_TRANSFER' ? 'success' : 'info'}">${escapeHtml(log.action)}</span></td>
                    <td><span class="mono">${escapeHtml(log.previous_custodian || 'None')}</span></td>
                    <td><span class="mono">${escapeHtml(log.new_custodian)}</span></td>
                    <td>${escapeHtml((log.timestamp || '').slice(0, 19).replace('T', ' '))}</td>
                    <td><span class="mono">${escapeHtml(log.blockchain_tx || 'Pending')}</span></td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state" style="color:var(--danger);">Failed to retrieve audit records.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state" style="color:var(--danger);">Error connecting to API.</td></tr>';
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
                        <button class="btn-sm btn-success" onclick="handleDownloadReport('${escapeHtml(r.report_filename)}')">Download PDF</button>
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
    modalContent.innerHTML = '<p>Recomputing SHA-256 from disk, MongoDB metadata, and Ethereum ledger...</p>';
    openModal('verifyModal');

    try {
        const res = await verifyEvidence(evidenceId);
        if (res.ok) {
            const data = await res.json();
            const isMatch = data.verified;
            const isTampered = data.tampered;

            modalContent.innerHTML = `
                <div style="text-align:center; padding: 0.75rem 0; margin-bottom: 1rem; border-radius:6px; background:${isMatch ? 'rgba(46,204,113,0.15)' : 'rgba(231,76,60,0.15)'}; border: 1px solid ${isMatch ? 'var(--success)' : 'var(--danger)'};">
                    <h4 style="color:${isMatch ? 'var(--success)' : 'var(--danger)'}; margin:0;">
                        ${isMatch ? '✓ INTEGRITY CONFIRMED — ALL THREE HASHES MATCH' : '⚠ TAMPERING DETECTED — HASH MISMATCH'}
                    </h4>
                </div>
                <ul class="verify-checklist">
                    <li>
                        <span><strong>1. Physical Disk Hash:</strong></span>
                        <span class="mono">${escapeHtml(data.physical_file_hash || 'N/A')}</span>
                    </li>
                    <li>
                        <span><strong>2. Database Recorded Hash:</strong></span>
                        <span class="mono">${escapeHtml(data.database_hash || 'N/A')}</span>
                    </li>
                    <li>
                        <span><strong>3. Blockchain Ledger Hash:</strong></span>
                        <span class="mono">${escapeHtml(data.blockchain_hash || 'N/A')}</span>
                    </li>
                    <li>
                        <span><strong>Physical == Database:</strong></span>
                        <span class="badge ${data.file_vs_database ? 'success' : 'danger'}">${data.file_vs_database ? 'Match' : 'Mismatch'}</span>
                    </li>
                    <li>
                        <span><strong>Database == Blockchain:</strong></span>
                        <span class="badge ${data.database_vs_blockchain ? 'success' : 'danger'}">${data.database_vs_blockchain ? 'Match' : 'Mismatch'}</span>
                    </li>
                </ul>
            `;
        } else {
            modalContent.innerHTML = '<p style="color:var(--danger);">Verification endpoint returned an error.</p>';
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
