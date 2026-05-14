// ===== LOGIN HANDLER =====
document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("loginForm");
  const loginScreen = document.getElementById("loginScreen");
  const hudScreen = document.getElementById("hudScreen");
  const loginError = document.getElementById("loginError");
  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");

  // Controlla se utente è già loggato nel sessionStorage
  if (sessionStorage.getItem("jarvis_authenticated")) {
    showHUD();
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.textContent = "";

    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    if (!username || !password) {
      showError("Inserisci username e password");
      return;
    }

    // Verifica semplice (modifica con logica backend se necessario)
    // Per demo: username="admin", password="jarvis"
    if (username === "admin" && password === "jarvis") {
      // Salva sessione
      sessionStorage.setItem("jarvis_authenticated", "true");
      sessionStorage.setItem("jarvis_user", username);

      // Transizione verso HUD
      animateLoginExit();
      setTimeout(() => {
        showHUD();
      }, 600);
    } else {
      showError("Credenziali non valide");
      shakeLoginForm();
    }
  });

  function showError(message) {
    loginError.textContent = message;
    loginError.style.animation = "none";
    setTimeout(() => {
      loginError.style.animation = "shake 0.4s ease";
    }, 10);
  }

  function shakeLoginForm() {
    const form = document.querySelector(".login-form");
    form.style.animation = "none";
    setTimeout(() => {
      form.style.animation = "shake 0.4s ease";
    }, 10);
  }

  function animateLoginExit() {
    loginScreen.style.animation = "loginFadeOut 0.6s ease-in forwards";
  }

  function showHUD() {
    loginScreen.classList.add("hidden");
    hudScreen.style.display = "block";
    setTimeout(() => {
      hudScreen.style.opacity = "1";
    }, 10);
  }

  // Logout handler (opzionale - aggiungi un pulsante logout se vuoi)
  window.logout = () => {
    sessionStorage.removeItem("jarvis_authenticated");
    sessionStorage.removeItem("jarvis_user");
    location.reload();
  };
});

// Aggiungi stile per animazione logout
const style = document.createElement("style");
style.textContent = `
  @keyframes loginFadeOut {
    from {
      opacity: 1;
      visibility: visible;
    }
    to {
      opacity: 0;
      visibility: hidden;
      transform: scale(0.98);
    }
  }
`;
document.head.appendChild(style);
