// Auth functionality
document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    const loginError = document.getElementById('loginError');

    if(loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');

            const username = usernameInput ? usernameInput.value.trim() : '';
            const password = passwordInput ? passwordInput.value : '';

            if (loginError) {
                loginError.textContent = '';
            }

            try {
                const response = await loginUser(username, password);
                if (response.ok) {
                    const data = await response.json();
                    sessionStorage.setItem('access_token', data.access_token);
                    sessionStorage.setItem('user_id', data.user_id);
                    sessionStorage.setItem('role', data.role);
                    window.location.href = 'dashboard.html';
                } else {
                    const err = await response.json().catch(() => ({}));
                    if (loginError) {
                        loginError.textContent = err.detail || 'Authentication failed. Please check badge ID and credentials.';
                    }
                }
            } catch (error) {
                console.error('Authentication request error:', error);
                if (loginError) {
                    loginError.textContent = 'Unable to connect to authentication service.';
                }
            }
        });
    }
});
