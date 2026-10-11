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
