// ==========================================================================
// ChainVault — Super Admin Platform Owner Console Controller
// Real-time Administrator Lifecycle Governance & Diagnostics
// ==========================================================================

let state = {
    admins: [],
    auditLogs: [],
    summary: null,
    activeView: 'overview',
    pendingActionTarget: null
};

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Strict Role & Session Gate
    const token = sessionStorage.getItem('access_token');
    const role = sessionStorage.getItem('role');

    if (!token) {
        window.location.href = 'login.html';
        return;
    }

    if (role !== 'SUPER_ADMIN') {
        console.warn('Unauthorized role accessing Platform Owner Console:', role);
        window.location.href = 'dashboard.html?v=' + Date.now();
        return;
    }

    // Populate Super Admin identity badge
    const ownerEl = document.getElementById('saOwnerUsername');
    const initialName = sessionStorage.getItem('display_name') || sessionStorage.getItem('username') || 'Platform Owner';
    if (ownerEl) ownerEl.textContent = initialName;

    try {
        const profileResp = await fetchCurrentUserProfile();
        if (profileResp.ok) {
            const profile = await profileResp.json();
            sessionStorage.setItem('username', profile.username);
            sessionStorage.setItem('display_name', profile.display_name || profile.full_name || profile.username);
            sessionStorage.setItem('user_id', profile.user_id);
            if (ownerEl) ownerEl.textContent = profile.display_name || profile.username;
        }
    } catch (e) {
        console.warn('Could not sync current super admin profile:', e);
    }

    // 2. Initialize UI Navigation & Listeners
    setupNavigation();
    setupModalListeners();
    setupFilterListeners();
    setupActionListeners();

    // 3. Initial Data Load
    await refreshAllData();
});

// ==========================================================================
// Toast Utility
// ==========================================================================
function showToast(message, type = 'success', durationMs = 4500) {
    const toast = document.getElementById('saToast');
    if (!toast) return;

    toast.className = `sa-toast ${type} visible`;
    toast.innerHTML = `<span>${type === 'success' ? '✅' : type === 'warning' ? '⚠️' : '❌'}</span> <span>${escapeHtml(message)}</span>`;

    setTimeout(() => {
        toast.className = 'sa-toast';
    }, durationMs);
}

// ==========================================================================
// Navigation & Views
// ==========================================================================
function setupNavigation() {
    const navItems = document.querySelectorAll('.sa-nav-item[data-view]');
    const views = document.querySelectorAll('.sa-view');
    const titleEl = document.getElementById('saHeaderTitle');
    const subtitleEl = document.getElementById('saHeaderSubtitle');

    const viewMeta = {
        overview: {
            title: 'Platform Overview',
            subtitle: 'ChainVault Infrastructure & Administrator Accounts Directorate'
        },
        admins: {
            title: 'Administrator Directory',
            subtitle: 'Tenant Administrator Provisioning, Status Management & Access Controls'
        },
        audit: {
            title: 'Governance Audit Trail',
            subtitle: 'Immutable Platform-Level Account Lifecycle Events & Actor Provenance'
        },
        security: {
            title: 'Platform Security Architecture',
            subtitle: 'Role Privilege Guardrails, Invalidation Policies & Defense-in-Depth'
        },
        system: {
            title: 'System Diagnostics & Health',
            subtitle: 'FastAPI Backend Engine, Cloud Firestore Staging & Hardhat Ledger Status'
        }
    };

    function switchView(viewId) {
        if (!viewMeta[viewId]) return;

        state.activeView = viewId;
        views.forEach(v => v.classList.remove('active'));
        const targetView = document.getElementById(`sa-view-${viewId}`);
        if (targetView) targetView.classList.add('active');

        navItems.forEach(n => {
            if (n.dataset.view === viewId) {
                n.classList.add('active');
            } else {
                n.classList.remove('active');
            }
        });

        if (titleEl) titleEl.textContent = viewMeta[viewId].title;
        if (subtitleEl) subtitleEl.textContent = viewMeta[viewId].subtitle;
    }

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const viewId = item.dataset.view;
            switchView(viewId);
        });
    });

    // Deep link buttons
    const linkViewAllAdmins = document.getElementById('linkViewAllAdmins');
    if (linkViewAllAdmins) {
        linkViewAllAdmins.addEventListener('click', (e) => {
            e.preventDefault();
            switchView('admins');
        });
    }

    const linkViewAllAudit = document.getElementById('linkViewAllAudit');
    if (linkViewAllAudit) {
        linkViewAllAudit.addEventListener('click', (e) => {
            e.preventDefault();
            switchView('audit');
        });
    }

    // Direct Add Admin Navigation Trigger
    const navItemAddAdmin = document.getElementById('navItemAddAdmin');
    if (navItemAddAdmin) {
        navItemAddAdmin.addEventListener('click', (e) => {
            e.preventDefault();
            openModal('modalAddAdmin');
        });
    }

    // Header buttons
    const btnHeaderAdd = document.getElementById('saHeaderAddAdminBtn');
    if (btnHeaderAdd) {
        btnHeaderAdd.addEventListener('click', () => openModal('modalAddAdmin'));
    }

    const btnViewAdd = document.getElementById('addAdminFromViewBtn');
    if (btnViewAdd) {
        btnViewAdd.addEventListener('click', () => openModal('modalAddAdmin'));
    }

    const btnRefresh = document.getElementById('saRefreshBtn');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', async () => {
            btnRefresh.disabled = true;
            await refreshAllData();
            showToast('Console state synchronized with backend.', 'success');
            btnRefresh.disabled = false;
        });
    }

    const btnRefreshTable = document.getElementById('refreshAdminsTableBtn');
    if (btnRefreshTable) {
        btnRefreshTable.addEventListener('click', async () => {
            await loadAdminsList();
            showToast('Administrator directory refreshed.', 'success');
        });
    }

    const btnRefreshAudit = document.getElementById('refreshAuditBtn');
    if (btnRefreshAudit) {
        btnRefreshAudit.addEventListener('click', async () => {
            await loadAuditTrail();
            showToast('Governance audit trail refreshed.', 'success');
        });
    }

    // Logout
    const btnLogout = document.getElementById('saLogoutBtn');
    if (btnLogout) {
        btnLogout.addEventListener('click', () => {
            sessionStorage.clear();
            localStorage.removeItem('access_token');
            window.location.href = 'login.html';
        });
    }
}

// ==========================================================================
// Data Fetching & Sync
// ==========================================================================
async function refreshAllData() {
    await Promise.all([
        loadPlatformSummary(),
        loadAdminsList(),
        loadAuditTrail(),
        checkSystemHealth()
    ]);
}

async function loadPlatformSummary() {
    try {
        const resp = await fetchSuperAdminSummary();
        if (resp.ok) {
            const data = await resp.json();
            state.summary = data;

            const elTotal = document.getElementById('kpiTotalAdmins');
            const elActive = document.getElementById('kpiActiveAdmins');
            const elInactive = document.getElementById('kpiInactiveAdmins');

            if (elTotal) elTotal.textContent = data.total_admins !== undefined ? data.total_admins : '--';
            if (elActive) elActive.textContent = data.active_admins !== undefined ? data.active_admins : '--';
            if (elInactive) elInactive.textContent = data.inactive_admins !== undefined ? data.inactive_admins : '--';
        }
    } catch (e) {
        console.error('Failed to load platform summary:', e);
    }
}

async function loadAdminsList() {
    try {
        const resp = await fetchSuperAdminAdmins();
        if (resp.ok) {
            const data = await resp.json();
            state.admins = Array.isArray(data) ? data : [];
            renderAdminsDirectory();
            renderOverviewRecentAdmins();
        } else {
            console.error('Error fetching admins:', resp.status);
            showToast('Failed to fetch administrator accounts list', 'error');
        }
    } catch (e) {
        console.error('Network error fetching admins:', e);
    }
}

async function loadAuditTrail() {
    try {
        const resp = await fetchSuperAdminAuditLogs(50);
        if (resp.ok) {
            const data = await resp.json();
            state.auditLogs = Array.isArray(data) ? data : [];

            const kpiAudit = document.getElementById('kpiAuditEvents');
            if (kpiAudit) kpiAudit.textContent = state.auditLogs.length;

            renderAuditTrail();
            renderOverviewAuditStream();
        }
    } catch (e) {
        console.error('Failed to load audit logs:', e);
    }
}

async function checkSystemHealth() {
    try {
        const health = await checkApiHealth();
        const bcStatus = await fetchBlockchainStatus().then(r => r.json()).catch(() => ({ connected: false }));

        const statusDot = document.querySelector('.sa-status-dot');
        const statusText = document.getElementById('saSystemStatusText');
        const overviewDb = document.getElementById('overviewDbStatus');
        const overviewBc = document.getElementById('overviewBcStatus');

        if (health && (health.status === 'healthy' || health.status === 'ok')) {
            if (statusDot) statusDot.style.backgroundColor = 'var(--sa-success)';
            if (statusText) statusText.textContent = 'API Online';
            if (overviewDb) overviewDb.textContent = `Google Cloud Firestore (${health.database || 'Active'})`;
        } else {
            if (statusDot) statusDot.style.backgroundColor = 'var(--sa-warning)';
            if (statusText) statusText.textContent = 'API Degraded';
        }

        if (bcStatus && bcStatus.connected) {
            if (overviewBc) overviewBc.textContent = `Hardhat Connected (Chain ${bcStatus.chain_id || 31337})`;
        } else {
            if (overviewBc) overviewBc.textContent = 'Hardhat Node Offline (Local)';
        }

        // Diagnostics Tab
        const diagApiBadge = document.getElementById('diagApiBadge');
        const diagBcBadge = document.getElementById('diagBcBadge');
        if (diagApiBadge && health) {
            const isApiOk = health.status === 'healthy' || health.status === 'ok';
            diagApiBadge.textContent = health.status ? (isApiOk ? 'ONLINE (OK)' : health.status.toUpperCase()) : 'UNKNOWN';
            diagApiBadge.className = `sa-badge ${isApiOk ? 'active' : 'inactive'}`;
        }
        if (diagBcBadge && bcStatus) {
            diagBcBadge.textContent = bcStatus.connected ? `CONNECTED (${bcStatus.chain_id})` : 'OFFLINE';
            diagBcBadge.className = `sa-badge ${bcStatus.connected ? 'active' : 'inactive'}`;
        }
    } catch (e) {
        console.warn('System diagnostic check error:', e);
    }
}

// ==========================================================================
// Rendering Views
// ==========================================================================
function renderAdminsDirectory() {
    const tbody = document.getElementById('adminsDirectoryTbody');
    const countLabel = document.getElementById('adminsCountLabel');
    if (!tbody) return;

    const searchTerm = (document.getElementById('adminSearchInput')?.value || '').toLowerCase().trim();
    const statusFilter = document.getElementById('adminStatusFilter')?.value || 'ALL';

    const filtered = state.admins.filter(admin => {
        const matchesSearch = !searchTerm ||
            (admin.username && admin.username.toLowerCase().includes(searchTerm)) ||
            (admin.full_name && admin.full_name.toLowerCase().includes(searchTerm)) ||
            (admin.user_id && admin.user_id.toLowerCase().includes(searchTerm));

        const matchesStatus = statusFilter === 'ALL' ||
            (statusFilter === 'ACTIVE' && admin.is_active) ||
            (statusFilter === 'INACTIVE' && !admin.is_active);

        return matchesSearch && matchesStatus;
    });

    if (countLabel) {
        countLabel.textContent = `Showing ${filtered.length} of ${state.admins.length} administrators`;
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--sa-text-dim);">No administrator accounts match the specified criteria.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(admin => {
        const isActive = !!admin.is_active;
        const createdDate = formatDate(admin.created_at);
        const lastActivity = formatDate(admin.last_login || admin.updated_at || admin.created_at);
        const displayName = escapeHtml(admin.display_name || admin.full_name || admin.username || 'Administrator');

        return `
            <tr>
                <td>
                    <div class="sa-user-cell">
                        <div class="sa-user-badge-icon">AD</div>
                        <div class="sa-user-meta">
                            <strong>${escapeHtml(admin.username)}</strong>
                            <span>${escapeHtml(admin.user_id || 'ID: UNASSIGNED')}</span>
                        </div>
                    </div>
                </td>
                <td>${displayName}</td>
                <td>
                    <span class="sa-badge ${isActive ? 'active' : 'inactive'}">
                        ${isActive ? '● Active' : '○ Suspended'}
                    </span>
                </td>
                <td style="color:var(--sa-text-muted); font-size:0.8rem;">${createdDate}</td>
                <td style="color:var(--sa-text-muted); font-size:0.8rem;">${lastActivity}</td>
                <td style="text-align: right;">
                    <div class="sa-actions-group" style="justify-content: flex-end;">
                        <button class="sa-btn-action ${isActive ? 'toggle-active' : 'toggle-inactive'}"
                                onclick="handleToggleStatus('${escapeHtml(admin.username)}', ${isActive})"
                                title="${isActive ? 'Deactivate account and revoke sessions' : 'Reactivate account'}">
                            ${isActive ? 'Deactivate' : 'Activate'}
                        </button>
                        <button class="sa-btn-action reset"
                                onclick="openResetPasswordModal('${escapeHtml(admin.username)}')"
                                title="Issue secure credential reset">
                            Reset Password
                        </button>
                        <button class="sa-btn-action delete"
                                onclick="openRemoveAdminModal('${escapeHtml(admin.username)}')"
                                title="Permanently delete account">
                            Remove
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function renderOverviewRecentAdmins() {
    const tbody = document.getElementById('overviewAdminsTbody');
    if (!tbody) return;

    const recent = state.admins.slice(0, 5);
    if (recent.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:1.5rem; color:var(--sa-text-dim);">No administrator accounts provisioned yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = recent.map(admin => {
        const isActive = !!admin.is_active;
        return `
            <tr>
                <td>
                    <div class="sa-user-cell">
                        <div class="sa-user-badge-icon" style="width:26px; height:26px; font-size:0.7rem;">AD</div>
                        <div class="sa-user-meta">
                            <strong style="font-size:0.85rem;">${escapeHtml(admin.username)}</strong>
                            <span style="font-size:0.7rem;">${escapeHtml(admin.full_name || 'Admin')}</span>
                        </div>
                    </div>
                </td>
                <td>
                    <span class="sa-badge ${isActive ? 'active' : 'inactive'}" style="font-size:0.7rem; padding:0.15rem 0.5rem;">
                        ${isActive ? 'Active' : 'Suspended'}
                    </span>
                </td>
                <td style="font-size:0.75rem; color:var(--sa-text-dim);">${formatDate(admin.created_at)}</td>
            </tr>
        `;
    }).join('');
}

function renderAuditTrail() {
    const tbody = document.getElementById('auditTrailTbody');
    if (!tbody) return;

    const search = (document.getElementById('auditSearchInput')?.value || '').toLowerCase().trim();
    const actionFilter = document.getElementById('auditActionFilter')?.value || 'ALL';

    const filtered = state.auditLogs.filter(log => {
        const matchesAction = actionFilter === 'ALL' || log.action === actionFilter;
        const matchesSearch = !search ||
            (log.action && log.action.toLowerCase().includes(search)) ||
            (log.actor_username && log.actor_username.toLowerCase().includes(search)) ||
            (log.target_username && log.target_username.toLowerCase().includes(search));

        return matchesAction && matchesSearch;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--sa-text-dim);">No governance audit records found.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(log => {
        const detailsStr = log.details ? JSON.stringify(log.details) : 'N/A';
        return `
            <tr>
                <td style="font-size:0.8rem; color:var(--sa-text-muted);">${formatDate(log.timestamp)}</td>
                <td><code class="sa-code-badge">${escapeHtml(log.action)}</code></td>
                <td><strong style="color:#fff;">${escapeHtml(log.actor_username || log.actor_id || 'System')}</strong></td>
                <td><strong style="color:#a78bfa;">${escapeHtml(log.target_username || log.target_account_id || 'Platform')}</strong></td>
                <td><span class="sa-badge ${log.outcome === 'SUCCESS' ? 'active' : 'danger'}">${escapeHtml(log.outcome)}</span></td>
                <td style="font-size:0.75rem; color:var(--sa-text-dim); max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(detailsStr)}">
                    ${escapeHtml(detailsStr)}
                </td>
            </tr>
        `;
    }).join('');
}

function renderOverviewAuditStream() {
    const container = document.getElementById('overviewAuditStream');
    if (!container) return;

    const recent = state.auditLogs.slice(0, 5);
    if (recent.length === 0) {
        container.innerHTML = `<div style="text-align:center; color:var(--sa-text-dim); padding:1.5rem;">No recent audit activity logged.</div>`;
        return;
    }

    container.innerHTML = recent.map(log => `
        <div class="sa-audit-item">
            <div class="sa-audit-top">
                <span class="sa-audit-action">${escapeHtml(log.action)}</span>
                <span class="sa-audit-time">${formatDate(log.timestamp)}</span>
            </div>
            <div class="sa-audit-meta">
                Actor: <strong style="color:#fff;">${escapeHtml(log.actor_username || log.actor_id)}</strong> | Target: <strong style="color:#a78bfa;">${escapeHtml(log.target_username || 'N/A')}</strong>
            </div>
        </div>
    `).join('');
}

// ==========================================================================
// Modals Management
// ==========================================================================
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        const firstInput = modal.querySelector('input:not([readonly])');
        if (firstInput) firstInput.focus();
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        const errorBanner = modal.querySelector('[id$="ErrorBanner"]');
        if (errorBanner) {
            errorBanner.style.display = 'none';
            errorBanner.textContent = '';
        }
    }
}

function setupModalListeners() {
    document.querySelectorAll('[data-close]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.dataset.close;
            closeModal(modalId);
        });
    });

    document.querySelectorAll('.sa-modal-backdrop').forEach(backdrop => {
        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop) {
                closeModal(backdrop.id);
            }
        });
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.sa-modal-backdrop.active').forEach(b => closeModal(b.id));
        }
    });
}

function setupFilterListeners() {
    const adminSearch = document.getElementById('adminSearchInput');
    const adminFilter = document.getElementById('adminStatusFilter');
    if (adminSearch) adminSearch.addEventListener('input', renderAdminsDirectory);
    if (adminFilter) adminFilter.addEventListener('change', renderAdminsDirectory);

    const auditSearch = document.getElementById('auditSearchInput');
    const auditFilter = document.getElementById('auditActionFilter');
    if (auditSearch) auditSearch.addEventListener('input', renderAuditTrail);
    if (auditFilter) auditFilter.addEventListener('change', renderAuditTrail);
}

// ==========================================================================
// Action Handlers
// ==========================================================================
function setupActionListeners() {
    // 1. Create Admin Form
    const formAdd = document.getElementById('formAddAdmin');
    if (formAdd) {
        formAdd.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('inputAdminUsername').value.trim();
            const fullName = document.getElementById('inputAdminFullName').value.trim();
            const password = document.getElementById('inputAdminPassword').value;
            const errorBanner = document.getElementById('addAdminErrorBanner');
            const submitBtn = document.getElementById('btnSubmitAddAdmin');

            if (errorBanner) {
                errorBanner.style.display = 'none';
                errorBanner.textContent = '';
            }

            if (password.length < 8) {
                if (errorBanner) {
                    errorBanner.textContent = 'Password must be at least 8 characters long.';
                    errorBanner.style.display = 'block';
                }
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = 'Provisioning...';

            try {
                const resp = await createSuperAdminAdmin({
                    username,
                    full_name: fullName || username,
                    password
                });

                if (resp.ok) {
                    closeModal('modalAddAdmin');
                    formAdd.reset();
                    showToast(`Administrator account '${username}' provisioned successfully!`, 'success');
                    await loadAdminsList();
                    await loadPlatformSummary();
                    await loadAuditTrail();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    if (errorBanner) {
                        errorBanner.textContent = err.detail || 'Failed to create administrator.';
                        errorBanner.style.display = 'block';
                    }
                }
            } catch (err) {
                console.error('Error creating admin:', err);
                if (errorBanner) {
                    errorBanner.textContent = 'Network communication failure with backend API.';
                    errorBanner.style.display = 'block';
                }
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Provision Account';
            }
        });
    }

    // 2. Reset Password Form
    const formReset = document.getElementById('formResetPassword');
    if (formReset) {
        formReset.addEventListener('submit', async (e) => {
            e.preventDefault();
            const targetUsername = state.pendingActionTarget;
            const newPassword = document.getElementById('inputResetNewPassword').value;
            const errorBanner = document.getElementById('resetErrorBanner');
            const submitBtn = document.getElementById('btnSubmitResetPassword');

            if (!targetUsername) return;

            if (newPassword.length < 8) {
                if (errorBanner) {
                    errorBanner.textContent = 'New password must be at least 8 characters long.';
                    errorBanner.style.display = 'block';
                }
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = 'Applying...';

            try {
                const resp = await resetSuperAdminAdminPassword(targetUsername, newPassword);
                if (resp.ok) {
                    closeModal('modalResetPassword');
                    formReset.reset();
                    showToast(`Password reset for '${targetUsername}'. Active tokens revoked immediately.`, 'success');
                    await loadAuditTrail();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    if (errorBanner) {
                        errorBanner.textContent = err.detail || 'Password reset request failed.';
                        errorBanner.style.display = 'block';
                    }
                }
            } catch (err) {
                if (errorBanner) {
                    errorBanner.textContent = 'Network failure executing password reset.';
                    errorBanner.style.display = 'block';
                }
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Apply New Password';
            }
        });
    }

    // 3. Remove Admin Form
    const formRemove = document.getElementById('formRemoveAdmin');
    if (formRemove) {
        formRemove.addEventListener('submit', async (e) => {
            e.preventDefault();
            const targetUsername = state.pendingActionTarget;
            const errorBanner = document.getElementById('removeErrorBanner');
            const submitBtn = document.getElementById('btnSubmitRemoveAdmin');

            if (!targetUsername) return;

            submitBtn.disabled = true;
            submitBtn.textContent = 'Deleting...';

            try {
                const resp = await removeSuperAdminAdmin(targetUsername, true);
                if (resp.ok) {
                    closeModal('modalRemoveAdmin');
                    formRemove.reset();
                    showToast(`Administrator account '${targetUsername}' removed successfully.`, 'success');
                    await loadAdminsList();
                    await loadPlatformSummary();
                    await loadAuditTrail();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    if (errorBanner) {
                        errorBanner.textContent = err.detail || 'Account deletion failed.';
                        errorBanner.style.display = 'block';
                    }
                }
            } catch (err) {
                if (errorBanner) {
                    errorBanner.textContent = 'Network error deleting administrator.';
                    errorBanner.style.display = 'block';
                }
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Delete Admin Account';
            }
        });
    }

    // Diagnostics Ping
    const btnPing = document.getElementById('btnPingSystem');
    if (btnPing) {
        btnPing.addEventListener('click', async () => {
            btnPing.disabled = true;
            btnPing.textContent = 'Pinging...';
            await checkSystemHealth();
            showToast('System diagnostic checks completed.', 'success');
            btnPing.disabled = false;
            btnPing.textContent = 'Ping All Subsystems';
        });
    }
}

// Global modal invokers (bound to window for onclick attributes)
window.handleToggleStatus = async function(username, currentStatus) {
    const newStatus = !currentStatus;
    const actionLabel = newStatus ? 'activate' : 'deactivate';

    try {
        const resp = await updateSuperAdminAdminStatus(username, newStatus);
        if (resp.ok) {
            showToast(`Administrator '${username}' is now ${newStatus ? 'ACTIVE' : 'DEACTIVATED'}. Sessions updated.`, 'success');
            await loadAdminsList();
            await loadPlatformSummary();
            await loadAuditTrail();
        } else {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || `Failed to ${actionLabel} account '${username}'.`, 'error');
        }
    } catch (e) {
        showToast(`Network error when attempting to ${actionLabel} account.`, 'error');
    }
};

window.openResetPasswordModal = function(username) {
    state.pendingActionTarget = username;
    const displayEl = document.getElementById('resetTargetUsernameDisplay');
    if (displayEl) displayEl.value = username;
    const form = document.getElementById('formResetPassword');
    if (form) form.reset();
    openModal('modalResetPassword');
};

window.openRemoveAdminModal = function(username) {
    state.pendingActionTarget = username;
    const displayEl = document.getElementById('removeTargetUsernameDisplay');
    if (displayEl) displayEl.textContent = username;
    const form = document.getElementById('formRemoveAdmin');
    if (form) form.reset();
    openModal('modalRemoveAdmin');
};

// Utilities
function formatDate(isoStr) {
    if (!isoStr) return 'N/A';
    try {
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return isoStr;
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return isoStr;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
