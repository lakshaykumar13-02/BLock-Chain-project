// Base API Configuration
const API_BASE_URL = 'http://localhost:8000/api';

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

async function fetchCases(token) {
    const response = await fetch(`${API_BASE_URL}/cases`, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    return response;
}

async function fetchEvidence(token) {
    const response = await fetch(`${API_BASE_URL}/evidence`, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    return response;
}

async function fetchBlockchainStatus() {
    const response = await fetch(`${API_BASE_URL}/blockchain/status`);
    return response;
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
    }
}
