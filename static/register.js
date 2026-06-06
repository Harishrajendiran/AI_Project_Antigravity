document.addEventListener('DOMContentLoaded', () => {
    const regPwToggle = document.getElementById('reg-pw-toggle');
    const regPasswordInput = document.getElementById('reg-password');
    const pwStrengthBar = document.getElementById('pw-strength-bar');
    const pwStrengthText = document.getElementById('pw-strength-text');

    if (regPwToggle && regPasswordInput) {
        // Toggle password visibility
        regPwToggle.addEventListener('click', () => {
            const isPw = regPasswordInput.type === 'password';
            regPasswordInput.type = isPw ? 'text' : 'password';
            regPwToggle.classList.toggle('visible', isPw);
            regPwToggle.setAttribute('aria-label', isPw ? 'Hide password' : 'Show password');
        });

        // Live password strength
        regPasswordInput.addEventListener('input', (e) => {
            const val = e.target.value;
            if (!val) {
                pwStrengthBar.className = 'strength-indicator';
                pwStrengthText.textContent = 'Password must be at least 8 characters.';
                pwStrengthText.style.color = '';
                return;
            }

            let score = 0;
            if (val.length >= 8) score++;
            if (/[A-Z]/.test(val)) score++;
            if (/[0-9]/.test(val)) score++;
            if (/[^a-zA-Z0-9]/.test(val)) score++;

            let strengthClass = '';
            let strengthLabel = '';

            if (val.length < 8) {
                strengthClass = 'strength-weak';
                strengthLabel = 'Too short (min 8 characters)';
            } else {
                switch(score) {
                    case 1:
                        strengthClass = 'strength-weak';
                        strengthLabel = 'Weak (add numbers/capitals/special characters)';
                        break;
                    case 2:
                        strengthClass = 'strength-fair';
                        strengthLabel = 'Fair password strength';
                        break;
                    case 3:
                        strengthClass = 'strength-good';
                        strengthLabel = 'Good password strength';
                        break;
                    case 4:
                        strengthClass = 'strength-strong';
                        strengthLabel = 'Strong & secure password!';
                        break;
                }
            }

            pwStrengthBar.className = `strength-indicator ${strengthClass}`;
            pwStrengthText.textContent = strengthLabel;
        });
    }
});
