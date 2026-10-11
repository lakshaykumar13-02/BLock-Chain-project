// Auth functionality (Phase 1 stub)
document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    
    if(loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            // Phase 1: Just redirect to dashboard to demonstrate flow
            window.location.href = 'dashboard.html';
        });
    }
});
