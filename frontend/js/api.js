// Base API Configuration (dynamically adapts to separate Render frontend/backend, cloud deployment or local dev)
function getResolvedApiBaseUrl() {
    // 1. Explicit window-level injection (e.g. from index.html or runtime config script)
    if (typeof window !== 'undefined' && window.__CHAINVAULT_API_URL__) {
        return window.__CHAINVAULT_API_URL__.replace(/\/+$/, '');
    }
    // 2. Query parameter override (e.g. ?api=https://chainvault-api.onrender.com)
    try {
        if (typeof window !== 'undefined' && window.location.search) {
            const params = new URLSearchParams(window.location.search);
            const queryApi = params.get('api') || params.get('api_url');
            if (queryApi && queryApi.trim()) {
                const clean = queryApi.trim().replace(/\/+$/, '');
                localStorage.setItem('chainvault_api_url', clean);
                return clean;
            }
        }
    } catch (e) {
        // Storage/URL access may be restricted
    }
    // 3. Browser storage override for separate frontend/backend hosting in staging
    try {
        const storedUrl = localStorage.getItem('chainvault_api_url') || sessionStorage.getItem('chainvault_api_url');
        if (storedUrl && storedUrl.trim()) {
            return storedUrl.trim().replace(/\/+$/, '');
        }
    } catch (e) {
        // Storage access may be restricted in sandbox environments
    }
    // 4. Localhost / local IP development fallback (matches exact current hostname to prevent IPv6 [::1] vs 127.0.0.1 mismatch)
    if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
        return `http://${window.location.hostname}:8000/api`;
    }
    // 5. Render Staging Auto-Detection: If hosted on Render static site (e.g. chainvault-frontend.onrender.com)
    // automatically map to corresponding backend Web Service (e.g. chainvault-api.onrender.com)
    if (typeof window !== 'undefined' && window.location.hostname && window.location.hostname.endsWith('.onrender.com')) {
        const host = window.location.hostname;
        if (host.includes('-frontend') || host.includes('frontend')) {
            const apiHost = host.replace(/-frontend/g, '-api').replace(/frontend/g, 'api');
            return `https://${apiHost}/api`;
        }
    }
    // 6. File-protocol or standalone fallback
    if (typeof window !== 'undefined' && (window.location.protocol === 'file:' || !window.location.hostname)) {
        return 'http://127.0.0.1:8000/api';
    }
    // 7. Same-origin fallback for reverse-proxied or unified domain hosting
    if (typeof window !== 'undefined' && window.location.origin && window.location.origin !== 'null') {
        return `${window.location.origin}/api`;
    }
    return 'http://127.0.0.1:8000/api';
}

function setConfiguredApiBaseUrl(url) {
    try {
        if (url && url.trim()) {
            localStorage.setItem('chainvault_api_url', url.trim().replace(/\/+$/, ''));
        } else {
            localStorage.removeItem('chainvault_api_url');
        }
    } catch (e) {
        console.warn('Could not persist chainvault_api_url to localStorage:', e);
    }
}

const API_BASE_URL = getResolvedApiBaseUrl();

function getStoredToken() {
    return sessionStorage.getItem('access_token') || '';
}

function getAuthHeaders(extraHeaders = {}) {
    const token = getStoredToken();
    const headers = { ...extraHeaders };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

async function checkApiHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        return await response.json();
    } catch (error) {
        console.error('API Health Check Failed:', error);
        return { status: 'error' };
    }
}

async function loginUser(username, password) {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    });
    return response;
}

async function fetchCases(token = getStoredToken()) {
    const response = await fetch(`${API_BASE_URL}/cases`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function createCase(caseData) {
    const response = await fetch(`${API_BASE_URL}/cases`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(caseData)
    });
    return response;
}

async function fetchEvidence(token = getStoredToken()) {
    const response = await fetch(`${API_BASE_URL}/evidence`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function uploadEvidence(formData) {
    // Note: fetch automatically adds boundary when passing FormData without manual Content-Type
    const response = await fetch(`${API_BASE_URL}/evidence/upload`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
    });
    return response;
}

async function fetchBlockchainStatus() {
    const response = await fetch(`${API_BASE_URL}/blockchain/status`);
    return response;
}

async function fetchOnChainEvidence(evidenceId) {
    const response = await fetch(`${API_BASE_URL}/blockchain/evidence/${encodeURIComponent(evidenceId)}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function registerEvidenceOnChain(evidenceId, fileHash, caseId = 'CV-DEMO-2026-001') {
    const response = await fetch(`${API_BASE_URL}/blockchain/register`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            evidence_id: evidenceId,
            hash: fileHash,
            case_id: caseId
        })
    });
    return response;
}

async function transferCustody(evidenceId, newCustodian, reason = 'Custody handover') {
    const response = await fetch(`${API_BASE_URL}/custody/transfer`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            evidence_id: evidenceId,
            new_custodian: newCustodian,
            reason: reason
        })
    });
    return response;
}

async function fetchAuditLogs(evidenceId) {
    const response = await fetch(`${API_BASE_URL}/audit/logs/${encodeURIComponent(evidenceId)}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function verifyAuditTrail(evidenceId, requireBlockchain = false) {
    const response = await fetch(`${API_BASE_URL}/audit/verify/${encodeURIComponent(evidenceId)}?require_blockchain=${Boolean(requireBlockchain)}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function generateReport(caseId, title = 'Forensic Investigation Report') {
    const response = await fetch(`${API_BASE_URL}/reports/generate`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            case_id: caseId,
            title: title
        })
    });
    return response;
}

async function fetchReportHistory(caseId) {
    const response = await fetch(`${API_BASE_URL}/reports/history/${encodeURIComponent(caseId)}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function verifyReport(reportId) {
    const response = await fetch(`${API_BASE_URL}/reports/verify/${encodeURIComponent(reportId)}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function downloadReportFile(filename) {
    const response = await fetch(`${API_BASE_URL}/reports/download/${encodeURIComponent(filename)}`, {
        headers: getAuthHeaders()
    });
    if (!response.ok) {
        throw new Error(`Report download failed with status ${response.status}`);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
}

async function verifyEvidence(evidenceId) {
    const response = await fetch(`${API_BASE_URL}/verification/verify`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ evidence_id: evidenceId })
    });
    return response;
}

async function logoutUser() {
    try {
        const token = sessionStorage.getItem('access_token');
        if (token) {
            await fetch(`${API_BASE_URL}/auth/logout`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            }).catch(() => {});
        }
    } catch (e) {
        console.error('Logout error:', e);
    } finally {
        sessionStorage.clear();
        localStorage.removeItem('access_token');
    }
}

async function fetchCurrentUserProfile() {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function updateUserProfile(displayName) {
    const response = await fetch(`${API_BASE_URL}/auth/profile`, {
        method: 'PUT',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ display_name: displayName })
    });
    return response;
}

async function fetchSuperAdminSummary() {
    const response = await fetch(`${API_BASE_URL}/superadmin/summary`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function fetchSuperAdminAdmins() {
    const response = await fetch(`${API_BASE_URL}/superadmin/admins`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function createSuperAdminAdmin(payload) {
    const response = await fetch(`${API_BASE_URL}/superadmin/admins`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload)
    });
    return response;
}

async function updateSuperAdminAdminStatus(username, isActive) {
    const response = await fetch(`${API_BASE_URL}/superadmin/admins/${encodeURIComponent(username)}/status`, {
        method: 'PUT',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ is_active: isActive })
    });
    return response;
}

async function resetSuperAdminAdminPassword(username, newPassword) {
    const response = await fetch(`${API_BASE_URL}/superadmin/admins/${encodeURIComponent(username)}/reset-password`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ new_password: newPassword })
    });
    return response;
}

async function removeSuperAdminAdmin(username, confirm = true) {
    const response = await fetch(`${API_BASE_URL}/superadmin/admins/${encodeURIComponent(username)}?confirm=${confirm}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
    });
    return response;
}

async function fetchSuperAdminAuditLogs(limit = 50) {
    const response = await fetch(`${API_BASE_URL}/superadmin/audit-logs?limit=${limit}`, {
        headers: getAuthHeaders()
    });
    return response;
}

// -----------------------------------------------------------------------------
// Admin Employee Management APIs
// -----------------------------------------------------------------------------

async function fetchAdminEmployees() {
    const response = await fetch(`${API_BASE_URL}/admin/employees`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function createAdminEmployee(payload) {
    const response = await fetch(`${API_BASE_URL}/admin/employees`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return response;
}

async function updateAdminEmployeeStatus(username, isActive) {
    const response = await fetch(`${API_BASE_URL}/admin/employees/${encodeURIComponent(username)}/status`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive })
    });
    return response;
}

async function resetAdminEmployeePassword(username, newPassword) {
    const response = await fetch(`${API_BASE_URL}/admin/employees/${encodeURIComponent(username)}/reset-password`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword })
    });
    return response;
}

async function removeAdminEmployee(username, confirm = true) {
    const response = await fetch(`${API_BASE_URL}/admin/employees/${encodeURIComponent(username)}?confirm=${confirm}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
    });
    return response;
}

// -----------------------------------------------------------------------------
// Tasks & Workflow APIs
// -----------------------------------------------------------------------------

async function fetchTasks(caseId = null) {
    const query = caseId ? `?case_id=${encodeURIComponent(caseId)}` : '';
    const response = await fetch(`${API_BASE_URL}/tasks${query}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function fetchMyTasks() {
    const response = await fetch(`${API_BASE_URL}/tasks/my-tasks`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function fetchTaskById(taskId) {
    const response = await fetch(`${API_BASE_URL}/tasks/${encodeURIComponent(taskId)}`, {
        headers: getAuthHeaders()
    });
    return response;
}

async function createTask(payload) {
    const response = await fetch(`${API_BASE_URL}/tasks`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return response;
}

async function updateTaskProgress(taskId, payload) {
    const response = await fetch(`${API_BASE_URL}/tasks/${encodeURIComponent(taskId)}/progress`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return response;
}

window.API_BASE_URL = API_BASE_URL;
window.getResolvedApiBaseUrl = getResolvedApiBaseUrl;
window.setConfiguredApiBaseUrl = setConfiguredApiBaseUrl;
window.getStoredToken = getStoredToken;
window.getAuthHeaders = getAuthHeaders;
window.checkApiHealth = checkApiHealth;
window.loginUser = loginUser;
window.fetchCases = fetchCases;
window.createCase = createCase;
window.fetchEvidence = fetchEvidence;
window.uploadEvidence = uploadEvidence;
window.fetchBlockchainStatus = fetchBlockchainStatus;
window.fetchOnChainEvidence = fetchOnChainEvidence;
window.registerEvidenceOnChain = registerEvidenceOnChain;
window.transferCustody = transferCustody;
window.fetchAuditLogs = fetchAuditLogs;
window.verifyAuditTrail = verifyAuditTrail;
window.generateReport = generateReport;
window.fetchReportHistory = fetchReportHistory;
window.verifyReport = verifyReport;
window.downloadReportFile = downloadReportFile;
window.verifyEvidence = verifyEvidence;
window.logoutUser = logoutUser;
window.fetchSuperAdminSummary = fetchSuperAdminSummary;
window.fetchSuperAdminAdmins = fetchSuperAdminAdmins;
window.createSuperAdminAdmin = createSuperAdminAdmin;
window.updateSuperAdminAdminStatus = updateSuperAdminAdminStatus;
window.resetSuperAdminAdminPassword = resetSuperAdminAdminPassword;
window.removeSuperAdminAdmin = removeSuperAdminAdmin;
window.fetchSuperAdminAuditLogs = fetchSuperAdminAuditLogs;
window.fetchCurrentUserProfile = fetchCurrentUserProfile;
window.updateUserProfile = updateUserProfile;

// Employee & Tasks Window Exports
window.fetchAdminEmployees = fetchAdminEmployees;
window.createAdminEmployee = createAdminEmployee;
window.updateAdminEmployeeStatus = updateAdminEmployeeStatus;
window.resetAdminEmployeePassword = resetAdminEmployeePassword;
window.removeAdminEmployee = removeAdminEmployee;
window.fetchTasks = fetchTasks;
window.fetchMyTasks = fetchMyTasks;
window.fetchTaskById = fetchTaskById;
window.createTask = createTask;
window.updateTaskProgress = updateTaskProgress;
