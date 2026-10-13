// Base API Configuration
const API_BASE_URL = 'http://localhost:8000/api';

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
            });
        }
    } catch (e) {
        console.error('Logout error:', e);
    } finally {
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('user_role');
        sessionStorage.removeItem('user_id');
        sessionStorage.removeItem('role');
    }
}

// Explicit window bindings to ensure cross-script availability
window.API_BASE_URL = API_BASE_URL;
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
window.generateReport = generateReport;
window.fetchReportHistory = fetchReportHistory;
window.downloadReportFile = downloadReportFile;
window.verifyEvidence = verifyEvidence;
window.logoutUser = logoutUser;
