// Login Manager
const loginManager = {
  credentials: {
    admin: 'jarvis',
  },

  init() {
    this.checkSession();
    this.setupEventListeners();
  },

  checkSession() {
    const session = sessionStorage.getItem('jarvisSession');
    if (session) {
      this.showHUD();
    } else {
      this.showLogin();
    }
  },

  setupEventListeners() {
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
      loginForm.addEventListener('submit', (e) => this.handleLogin(e));
    }

    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    
    if (usernameInput) {
      usernameInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') passwordInput?.focus();
      });
    }
    
    if (passwordInput) {
      passwordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') this.handleLogin(e);
      });
    }
  },

  async handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('username')?.value || '';
    const password = document.getElementById('password')?.value || '';
    const errorMsg = document.getElementById('loginError');

    if (!username || !password) {
      this.showError(errorMsg, 'Username e password richiesti');
      return;
    }

    if (this.credentials[username] === password) {
      sessionStorage.setItem('jarvisSession', JSON.stringify({ username, timestamp: Date.now() }));
      this.transitionToHUD();
    } else {
      this.shakeError();
      this.showError(errorMsg, 'Credenziali non valide');
      document.getElementById('password').value = '';
    }
  },

  showError(element, message) {
    if (!element) return;
    element.textContent = message;
    element.style.opacity = '1';
    setTimeout(() => {
      element.style.opacity = '0';
    }, 3000);
  },

  shakeError() {
    const loginBox = document.getElementById('loginBox');
    if (loginBox) {
      loginBox.style.animation = 'none';
      setTimeout(() => {
        loginBox.style.animation = 'loginShake 0.4s';
      }, 10);
    }
  },

  showLogin() {
    const loginScreen = document.getElementById('loginScreen');
    const hudScreen = document.getElementById('hudScreen');
    if (loginScreen) loginScreen.classList.add('visible');
    if (hudScreen) hudScreen.classList.remove('visible');
  },

  showHUD() {
    const loginScreen = document.getElementById('loginScreen');
    const hudScreen = document.getElementById('hudScreen');
    if (loginScreen) loginScreen.classList.remove('visible');
    if (hudScreen) hudScreen.classList.add('visible');
  },

  transitionToHUD() {
    const loginScreen = document.getElementById('loginScreen');
    if (loginScreen) {
      loginScreen.style.animation = 'loginFadeOut 0.8s ease-in forwards';
      setTimeout(() => this.showHUD(), 800);
    }
  },

  logout() {
    sessionStorage.removeItem('jarvisSession');
    location.reload();
  },
};

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => loginManager.init());
} else {
  loginManager.init();
}
