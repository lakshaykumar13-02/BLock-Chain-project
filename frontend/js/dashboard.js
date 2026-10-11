// Dashboard functionality (Phase 1 stub)
document.addEventListener('DOMContentLoaded', async () => {
    // Check API connection
    const health = await checkApiHealth();
    if(health && health.status === 'ok') {
        console.log('Backend API is reachable:', health.service);
        document.querySelector('.status-indicator').style.backgroundColor = 'var(--success)';
        document.querySelector('.status-indicator').style.boxShadow = '0 0 8px var(--success)';
    } else {
        console.warn('Backend API is not reachable. Showing static data.');
        document.querySelector('.status-indicator').style.backgroundColor = 'var(--danger)';
        document.querySelector('.status-indicator').style.boxShadow = '0 0 8px var(--danger)';
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if(logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            window.location.href = 'login.html';
        });
    }
});
