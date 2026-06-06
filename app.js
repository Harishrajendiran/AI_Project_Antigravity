/**
 * Aura Portal - Front-end Authentication logic
 * 
 * TODO(security): This client-side implementation is a secure mock for demonstration purposes.
 * In a production web application, registration, validation, and login MUST be handled on a 
 * server-side backend. Passwords must never be stored in plain text and should be hashed using
 * Argon2 or bcrypt. Session identifiers must be managed using Secure and HttpOnly cookies.
 */

document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const portalCard = document.getElementById('portal-card');
    const portalTitle = document.getElementById('portal-title');
    const portalSubtitle = document.getElementById('portal-subtitle');

    // Views
    const loginView = document.getElementById('login-view');
    const registerView = document.getElementById('register-view');
    const dashboardView = document.getElementById('dashboard-view');

    // Forms & Inputs
    const loginForm = document.getElementById('login-form');
    const loginUsernameInput = document.getElementById('login-username');
    const loginPasswordInput = document.getElementById('login-password');

    const registerForm = document.getElementById('register-form');
    const regNameInput = document.getElementById('reg-name');
    const regMobileInput = document.getElementById('reg-mobile');
    const regEmailInput = document.getElementById('reg-email');
    const regPasswordInput = document.getElementById('reg-password');
    const pwStrengthBar = document.getElementById('pw-strength-bar');
    const pwStrengthText = document.getElementById('pw-strength-text');

    // Toggles & Switches
    const loginPwToggle = document.getElementById('login-pw-toggle');
    const regPwToggle = document.getElementById('reg-pw-toggle');
    const goToRegisterBtn = document.getElementById('go-to-register');
    const goToLoginBtn = document.getElementById('go-to-login');
    const logoutBtn = document.getElementById('btn-logout');

    // Dashboard dynamic labels
    const dashName = document.getElementById('dash-name');
    const dashEmail = document.getElementById('dash-email');
    const dashMobile = document.getElementById('dash-mobile');

    // Submit Buttons
    const btnLoginSubmit = document.getElementById('btn-login-submit');
    const btnRegisterSubmit = document.getElementById('btn-register-submit');

    // --- Mock User Store Interface ---
    const getMockUsers = () => {
        try {
            const users = localStorage.getItem('aura_mock_users');
            return users ? JSON.parse(users) : [];
        } catch (e) {
            console.error('Failed to parse mock user database', e);
            return [];
        }
    };

    const saveMockUser = (user) => {
        try {
            const users = getMockUsers();
            users.push(user);
            localStorage.setItem('aura_mock_users', JSON.stringify(users));
            return true;
        } catch (e) {
            console.error('Failed to save user in mock store', e);
            return false;
        }
    };

    // --- Helper Helpers & Formatters ---
    const showToast = (title, message, type = 'info') => {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        // Icon element
        const icon = document.createElement('div');
        icon.className = 'toast-icon';
        if (type === 'success') icon.textContent = '✓';
        else if (type === 'error') icon.textContent = '✗';
        else icon.textContent = 'ℹ';
        toast.appendChild(icon);

        // Content element
        const content = document.createElement('div');
        content.className = 'toast-content';

        const toastTitle = document.createElement('div');
        toastTitle.className = 'toast-title';
        toastTitle.textContent = title;
        content.appendChild(toastTitle);

        const toastMsg = document.createElement('div');
        toastMsg.className = 'toast-message';
        toastMsg.textContent = message;
        content.appendChild(toastMsg);

        toast.appendChild(content);
        container.appendChild(toast);

        // Auto-remove after 4 seconds
        const timer = setTimeout(() => {
            removeToast(toast);
        }, 4000);

        // Manual dismiss click logic
        toast.addEventListener('click', () => {
            clearTimeout(timer);
            removeToast(toast);
        });
    };

    const removeToast = (toast) => {
        toast.classList.add('removing');
        toast.addEventListener('animationend', () => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        });
    };

    // PII Masking Utilities to prevent direct leak of user data
    const maskEmail = (email) => {
        const parts = email.split('@');
        if (parts.length !== 2) return '***';
        const name = parts[0];
        const domain = parts[1];
        if (name.length <= 2) {
            return name.charAt(0) + '***@' + domain;
        }
        return name.charAt(0) + '***' + name.charAt(name.length - 1) + '@' + domain;
    };

    const maskMobile = (mobile) => {
        if (mobile.length < 4) return '******';
        return '•'.repeat(mobile.length - 4) + mobile.slice(-4);
    };

    // --- Validation Utilities ---
    const validateEmail = (email) => {
        // Standard robust email validation RFC 5322 regex
        const re = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$/;
        return re.test(email);
    };

    const validateMobile = (mobile) => {
        // Digits only, 10 to 12 digits length
        const re = /^[0-9]{10,12}$/;
        return re.test(mobile.trim());
    };

    const validateName = (name) => {
        // Letters and space, min 2 chars
        const re = /^[a-zA-Z\s]{2,50}$/;
        return re.test(name.trim());
    };

    // --- Password Strength Evaluator ---
    const checkPasswordStrength = (password) => {
        let score = 0;
        if (password.length >= 8) score++;
        if (/[A-Z]/.test(password)) score++;
        if (/[0-9]/.test(password)) score++;
        if (/[^a-zA-Z0-9]/.test(password)) score++;
        return score;
    };

    const updateStrengthUI = (password) => {
        if (!password) {
            pwStrengthBar.className = 'strength-indicator';
            pwStrengthText.textContent = 'Password must be at least 8 characters.';
            pwStrengthText.style.color = '';
            return;
        }

        const score = checkPasswordStrength(password);
        
        let strengthClass = '';
        let strengthLabel = '';

        if (password.length < 8) {
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
    };

    // --- View Controller Transitions ---
    const showView = (targetView) => {
        const allViews = [loginView, registerView, dashboardView];
        
        allViews.forEach(view => {
            if (view === targetView) {
                view.classList.remove('hidden');
            } else {
                view.classList.add('hidden');
            }
        });
    };

    // --- Event Listeners ---

    // Password Toggles
    loginPwToggle.addEventListener('click', () => {
        const isPw = loginPasswordInput.type === 'password';
        loginPasswordInput.type = isPw ? 'text' : 'password';
        loginPwToggle.classList.toggle('visible', isPw);
        loginPwToggle.setAttribute('aria-label', isPw ? 'Hide password' : 'Show password');
    });

    regPwToggle.addEventListener('click', () => {
        const isPw = regPasswordInput.type === 'password';
        regPasswordInput.type = isPw ? 'text' : 'password';
        regPwToggle.classList.toggle('visible', isPw);
        regPwToggle.setAttribute('aria-label', isPw ? 'Hide password' : 'Show password');
    });

    // Form Navigation Switches
    goToRegisterBtn.addEventListener('click', () => {
        portalTitle.textContent = 'Join Aura';
        portalSubtitle.textContent = 'Create a secure client profile to get started.';
        showView(registerView);
        registerForm.reset();
        updateStrengthUI('');
    });

    goToLoginBtn.addEventListener('click', () => {
        portalTitle.textContent = 'Aura Portal';
        portalSubtitle.textContent = 'Welcome back! Please enter your details.';
        showView(loginView);
        loginForm.reset();
    });

    // Live Password Strength Tracking
    regPasswordInput.addEventListener('input', (e) => {
        updateStrengthUI(e.target.value);
    });

    // --- Form Submissions ---

    // Register Form Handler
    registerForm.addEventListener('submit', (e) => {
        e.preventDefault();

        const name = regNameInput.value.trim();
        const mobile = regMobileInput.value.trim();
        const email = regEmailInput.value.trim().toLowerCase();
        const password = regPasswordInput.value;

        // Perform Validation Checks
        if (!validateName(name)) {
            showToast('Invalid Name', 'Name must contain only letters and space (min 2 chars).', 'error');
            regNameInput.focus();
            return;
        }

        if (!validateMobile(mobile)) {
            showToast('Invalid Mobile', 'Mobile number must be digits only (10 to 12 digits).', 'error');
            regMobileInput.focus();
            return;
        }

        if (!validateEmail(email)) {
            showToast('Invalid Email', 'Please enter a valid email format.', 'error');
            regEmailInput.focus();
            return;
        }

        if (password.length < 8) {
            showToast('Weak Password', 'Password must contain at least 8 characters.', 'error');
            regPasswordInput.focus();
            return;
        }

        // Check if user already exists
        const users = getMockUsers();
        const userExists = users.some(u => u.email === email || u.mobile === mobile);
        if (userExists) {
            showToast('Registration Refused', 'An account with this email or mobile already exists.', 'error');
            return;
        }

        // Loader state
        btnRegisterSubmit.disabled = true;
        const btnText = btnRegisterSubmit.querySelector('.btn-text');
        const btnLoader = btnRegisterSubmit.querySelector('.btn-loader');
        btnText.textContent = 'Registering...';
        btnLoader.classList.remove('hidden');

        // Simulate secure database transaction network delay
        setTimeout(() => {
            const newUser = { name, mobile, email, password };
            const success = saveMockUser(newUser);

            // Revert state
            btnRegisterSubmit.disabled = false;
            btnText.textContent = 'Create Account';
            btnLoader.classList.add('hidden');

            if (success) {
                showToast('Success', 'Profile registered successfully. Please log in.', 'success');
                // Switch to Login View
                portalTitle.textContent = 'Aura Portal';
                portalSubtitle.textContent = 'Account created! Enter your credentials to access.';
                showView(loginView);
                loginForm.reset();
            } else {
                showToast('Database Error', 'Could not write register entry.', 'error');
            }
        }, 1000);
    });

    // Login Form Handler
    loginForm.addEventListener('submit', (e) => {
        e.preventDefault();

        const username = loginUsernameInput.value.trim().toLowerCase();
        const password = loginPasswordInput.value;

        if (!username || !password) {
            showToast('Missing Fields', 'Please complete all required fields.', 'error');
            return;
        }

        // Loader state
        btnLoginSubmit.disabled = true;
        const btnText = btnLoginSubmit.querySelector('.btn-text');
        const btnLoader = btnLoginSubmit.querySelector('.btn-loader');
        btnText.textContent = 'Authenticating...';
        btnLoader.classList.remove('hidden');

        // Simulate secure verification delay
        setTimeout(() => {
            const users = getMockUsers();
            
            // Search in mock DB by email or username
            const authenticatedUser = users.find(u => 
                (u.email === username || u.email.split('@')[0] === username) && u.password === password
            );

            // Revert state
            btnLoginSubmit.disabled = false;
            btnText.textContent = 'Sign In';
            btnLoader.classList.add('hidden');

            if (authenticatedUser) {
                showToast('Access Granted', 'Welcome back to Aura Portal.', 'success');
                
                // Show masked PII inside UI labels
                dashName.textContent = authenticatedUser.name;
                dashEmail.textContent = maskEmail(authenticatedUser.email);
                dashMobile.textContent = maskMobile(authenticatedUser.mobile);

                // Show Dashboard
                portalTitle.textContent = 'Aura Dashboard';
                portalSubtitle.textContent = 'Review your secure workspace status.';
                showView(dashboardView);
                loginForm.reset();
            } else {
                showToast('Access Denied', 'Invalid username or password.', 'error');
                loginPasswordInput.value = ''; // Clear password field on failure
                loginPasswordInput.focus();
            }
        }, 800);
    });

    // Logout Handler
    logoutBtn.addEventListener('click', () => {
        showToast('Signed Out', 'Your session has been terminated.', 'info');
        
        // Reset and clear memory variables/caches & redirect
        portalTitle.textContent = 'Aura Portal';
        portalSubtitle.textContent = 'Welcome back! Please enter your details.';
        showView(loginView);
    });
});
