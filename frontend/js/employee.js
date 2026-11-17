// ==========================================================================
// ChainVault — Employee Portal Client Controller
// ==========================================================================

let employeeState = {
    tasks: [],
    evidence: [],
    currentTaskForUpdate: null
};

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Strict Role & Authentication Gate
    const token = sessionStorage.getItem('access_token');
    const role = sessionStorage.getItem('role');

    if (!token) {
        window.location.href = 'login.html';
        return;
    }

    if (role !== 'EMPLOYEE') {
        console.warn('Unauthorized role accessing Employee Portal:', role);
        if (role === 'SUPER_ADMIN') {
            window.location.href = 'superadmin.html';
        } else {
            window.location.href = 'dashboard.html';
        }
        return;
    }

    // 2. Populate Identity Information
    const displayName = sessionStorage.getItem('display_name') || sessionStorage.getItem('username') || 'Employee';
    const username = sessionStorage.getItem('username') || '';
    const userId = sessionStorage.getItem('user_id') || '';

    renderEmployeeProfile(displayName, username, userId);

    // Sync profile from server if available
    try {
        const resp = await fetchCurrentUserProfile();
        if (resp.ok) {
            const prof = await resp.json();
            const effName = prof.display_name || prof.full_name || prof.username;
            sessionStorage.setItem('display_name', effName);
            sessionStorage.setItem('username', prof.username);
            sessionStorage.setItem('user_id', prof.user_id);
            renderEmployeeProfile(effName, prof.username, prof.user_id);
        }
    } catch (e) {
        console.warn('Could not sync current profile:', e);
    }

    // 3. Setup Navigation & View Switching
    setupNavigation();
    setupModalListeners();
    setupFilterListeners();

    // 4. Initial Data Load
    await refreshAllData();
});

function renderEmployeeProfile(displayName, username, userId) {
    const nameEl = document.getElementById('empUserName');
    const idEl = document.getElementById('empUserId');
    const headerName = document.getElementById('empHeaderBadgeName');
    const avatar = document.getElementById('empUserAvatar');

    if (nameEl) nameEl.textContent = displayName;
    if (idEl) idEl.textContent = `${username} (${userId})`;
    if (headerName) headerName.textContent = displayName;
    if (avatar) {
        const initials = displayName.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase() || 'EM';
        avatar.textContent = initials;
    }
}

function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-links a');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navLinks.forEach(l => l.parentElement.classList.remove('active'));
            link.parentElement.classList.add('active');

            const viewId = link.getAttribute('data-view');
            document.querySelectorAll('.dashboard-view').forEach(v => v.classList.remove('active'));
            const targetView = document.getElementById(`view-${viewId}`);
            if (targetView) targetView.classList.add('active');
        });
    });

    const logoutBtn = document.getElementById('empLogoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                await logoutUser();
            } catch (e) {}
            sessionStorage.clear();
            window.location.href = 'login.html';
        });
    }

    // Refresh buttons
    document.getElementById('btnRefreshTasks')?.addEventListener('click', loadTasks);
    document.getElementById('btnRefreshEvidence')?.addEventListener('click', loadEvidence);
    document.getElementById('btnRefreshActivity')?.addEventListener('click', renderActivityTrail);
}

function setupFilterListeners() {
    const filter = document.getElementById('filterTaskStatus');
    if (filter) {
        filter.addEventListener('change', () => {
            renderTasks(filter.value);
        });
    }
}

function setupModalListeners() {
    const slider = document.getElementById('modalTaskPercent');
    const display = document.getElementById('modalPercentDisplay');
    if (slider && display) {
        slider.addEventListener('input', () => {
            display.textContent = `${slider.value}%`;
        });
    }

    const form = document.getElementById('formUpdateProgress');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const taskId = document.getElementById('modalTaskId').value;
            const newStatus = document.getElementById('modalTaskStatus').value;
            const newPercent = parseInt(document.getElementById('modalTaskPercent').value, 10);
            const newNote = document.getElementById('modalTaskNote').value;

            try {
                const resp = await updateTaskProgress(taskId, {
                    status: newStatus,
                    progress_percent: newPercent,
                    note: newNote
                });

                if (resp.ok) {
                    closeModal('modalUpdateProgress');
                    showToast('Task progress successfully updated and recorded in audit log.', 'success');
                    await refreshAllData();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    showToast(err.detail || 'Failed to update progress.', 'error');
                }
            } catch (err) {
                showToast('Network error updating task.', 'error');
            }
        });
    }
}

async function refreshAllData() {
    await Promise.all([
        loadTasks(),
        loadEvidence()
    ]);
}

async function loadTasks() {
    try {
        const resp = await fetchMyTasks();
        if (resp.ok) {
            employeeState.tasks = await resp.json();
            updateStats();
            const filterVal = document.getElementById('filterTaskStatus')?.value || 'ALL';
            renderTasks(filterVal);
            renderActivityTrail();
        } else {
            document.getElementById('tasksContainer').innerHTML = `<div class="loading-placeholder">Failed to load assigned tasks.</div>`;
        }
    } catch (e) {
        document.getElementById('tasksContainer').innerHTML = `<div class="loading-placeholder">Network error loading tasks.</div>`;
    }
}

function updateStats() {
    const tasks = employeeState.tasks;
    const total = tasks.length;
    const inProgress = tasks.filter(t => t.status === 'IN_PROGRESS').length;
    const completed = tasks.filter(t => t.status === 'COMPLETED').length;

    // Calculate unique permitted evidence items
    const evidenceSet = new Set();
    tasks.forEach(t => {
        (t.permitted_evidence_ids || []).forEach(eid => evidenceSet.add(eid));
    });

    document.getElementById('statTotalTasks').textContent = total;
    document.getElementById('statInProgressTasks').textContent = inProgress;
    document.getElementById('statCompletedTasks').textContent = completed;
    document.getElementById('statPermittedEvidence').textContent = evidenceSet.size;
}

function renderTasks(filterStatus = 'ALL') {
    const container = document.getElementById('tasksContainer');
    if (!container) return;

    let filtered = employeeState.tasks;
    if (filterStatus !== 'ALL') {
        filtered = filtered.filter(t => t.status === filterStatus);
    }

    if (filtered.length === 0) {
        container.innerHTML = `<div class="loading-placeholder">No assigned tasks matching status "${filterStatus}".</div>`;
        return;
    }

    container.innerHTML = filtered.map(t => {
        const evidenceBadges = (t.permitted_evidence_ids || []).map(eid =>
            `<span class="evidence-tag">${escapeHtml(eid)}</span>`
        ).join('') || '<span style="color:#64748b; font-size:0.75rem;">None</span>';

        const priorityClass = `priority-${t.priority || 'MEDIUM'}`;
        const statusClass = `status-${t.status || 'ASSIGNED'}`;
        const percent = Math.min(100, Math.max(0, t.progress_percent || 0));

        return `
            <div class="task-card">
                <div>
                    <div class="task-header">
                        <span class="task-id-badge">${escapeHtml(t.task_id)}</span>
                        <span class="task-priority-badge ${priorityClass}">${escapeHtml(t.priority || 'MEDIUM')}</span>
                    </div>
                    <div class="task-title">${escapeHtml(t.title)}</div>
                    <div class="task-description">${escapeHtml(t.description || 'No description provided.')}</div>
                    
                    <div class="task-meta-row">
                        <span class="meta-pill"><strong>Case:</strong> ${escapeHtml(t.case_id)}</span>
                        ${t.due_date ? `<span class="meta-pill"><strong>Due:</strong> ${escapeHtml(t.due_date.substring(0, 10))}</span>` : ''}
                    </div>

                    <div style="margin-bottom:0.75rem;">
                        <span style="font-size:0.75rem; color:#94a3b8; display:block; margin-bottom:0.25rem;">Permitted Evidence:</span>
                        <div>${evidenceBadges}</div>
                    </div>

                    <div class="task-progress-box">
                        <div class="progress-header">
                            <span>Progress</span>
                            <strong style="color:#e2e8f0;">${percent}%</strong>
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width: ${percent}%;"></div>
                        </div>
                    </div>
                </div>

                <div class="task-footer">
                    <span class="status-badge-inline ${statusClass}">${escapeHtml(t.status || 'ASSIGNED')}</span>
                    <button class="btn-sm btn-primary" style="background:#10b981;" onclick="openUpdateModal('${t.task_id}')">Update Progress</button>
                </div>
            </div>
        `;
    }).join('');
}

window.openUpdateModal = function(taskId) {
    const task = employeeState.tasks.find(t => t.task_id === taskId);
    if (!task) return;

    employeeState.currentTaskForUpdate = task;
    document.getElementById('modalTaskId').value = task.task_id;
    document.getElementById('modalTaskTitle').textContent = `${task.task_id} — ${task.title} (Case: ${task.case_id})`;
    document.getElementById('modalTaskStatus').value = task.status || 'ASSIGNED';
    
    const slider = document.getElementById('modalTaskPercent');
    const display = document.getElementById('modalPercentDisplay');
    slider.value = task.progress_percent || 0;
    display.textContent = `${task.progress_percent || 0}%`;

    document.getElementById('modalTaskNote').value = '';

    openModal('modalUpdateProgress');
};

async function loadEvidence() {
    const tbody = document.getElementById('empEvidenceTableBody');
    if (!tbody) return;

    try {
        const resp = await fetchEvidence();
        if (resp.ok) {
            employeeState.evidence = await resp.json();
            renderEvidenceTable();
        } else {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#f87171;">Failed to load authorized evidence.</td></tr>`;
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#f87171;">Network error loading evidence.</td></tr>`;
    }
}

function renderEvidenceTable() {
    const tbody = document.getElementById('empEvidenceTableBody');
    if (!tbody) return;

    const list = employeeState.evidence;
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#94a3b8; padding:2rem;">No authorized evidence items assigned yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map(ev => {
        const hash = ev.file_hash || '';
        const shortHash = hash.length > 16 ? `${hash.substring(0, 10)}...${hash.substring(hash.length - 6)}` : hash;
        const sizeKb = ev.file_size ? `${(ev.file_size / 1024).toFixed(1)} KB` : '--';
        const filename = ev.filename || 'evidence.bin';

        return `
            <tr>
                <td><strong>${escapeHtml(ev.evidence_id)}</strong></td>
                <td><span class="meta-pill">${escapeHtml(ev.case_id)}</span></td>
                <td>${escapeHtml(filename)}</td>
                <td title="${escapeHtml(hash)}"><code style="color:#38bdf8;">${escapeHtml(shortHash)}</code></td>
                <td>${sizeKb}</td>
                <td>
                    <button class="btn-sm btn-outline" onclick="verifyItem('${ev.evidence_id}')" style="margin-right:0.3rem;">Verify</button>
                    <a href="${API_BASE_URL}/evidence/download/${encodeURIComponent(filename)}" target="_blank" class="btn-sm btn-primary" style="text-decoration:none; display:inline-block;">Download</a>
                </td>
            </tr>
        `;
    }).join('');
}

window.verifyItem = async function(evidenceId) {
    try {
        showToast(`Verifying integrity for ${evidenceId}...`, 'info', 2000);
        const resp = await verifyEvidence(evidenceId);
        if (resp.ok) {
            const data = await resp.json();
            const status = data.verification_status || (data.verified ? 'VERIFIED' : 'FAILED');
            if (status === 'VERIFIED') {
                showToast(`✅ ${evidenceId}: Cryptographic integrity verified across file & blockchain ledger.`, 'success', 5000);
            } else {
                showToast(`⚠️ ${evidenceId}: Status is ${status}.`, 'error', 5000);
            }
        } else {
            showToast(`Verification service returned status ${resp.status}.`, 'error');
        }
    } catch (e) {
        showToast('Error executing verification.', 'error');
    }
};

function renderActivityTrail() {
    const container = document.getElementById('activityStreamContainer');
    if (!container) return;

    const allEvents = [];
    employeeState.tasks.forEach(t => {
        (t.activity_log || []).forEach(act => {
            allEvents.push({
                ...act,
                task_id: t.task_id,
                task_title: t.title
            });
        });
    });

    allEvents.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

    if (allEvents.length === 0) {
        container.innerHTML = `<div class="loading-placeholder">No activity recorded yet.</div>`;
        return;
    }

    container.innerHTML = allEvents.map(evt => {
        const time = evt.timestamp ? new Date(evt.timestamp).toLocaleString() : '--';
        return `
            <div class="activity-item">
                <div class="activity-header">
                    <span><strong style="color:#38bdf8;">${escapeHtml(evt.task_id)}</strong> — ${escapeHtml(evt.action || 'UPDATE')} by ${escapeHtml(evt.actor || 'System')}</span>
                    <span>${escapeHtml(time)}</span>
                </div>
                <div class="activity-note">${escapeHtml(evt.note || 'No notes provided.')}</div>
            </div>
        `;
    }).join('');
}

// Global modal helpers
window.openModal = function(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = 'block';
};

window.closeModal = function(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = 'none';
};

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

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
