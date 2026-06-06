document.addEventListener('DOMContentLoaded', () => {
    const loginPwToggle = document.getElementById('login-pw-toggle');
    const loginPasswordInput = document.getElementById('login-password');

    if (loginPwToggle && loginPasswordInput) {
        loginPwToggle.addEventListener('click', () => {
            const isPw = loginPasswordInput.type === 'password';
            loginPasswordInput.type = isPw ? 'text' : 'password';
            loginPwToggle.classList.toggle('visible', isPw);
            loginPwToggle.setAttribute('aria-label', isPw ? 'Hide password' : 'Show password');
        });
    }
});
