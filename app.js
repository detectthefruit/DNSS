const startButton = document.querySelector("#start-button");
const linkState = document.querySelector("#link-state");
const statusDetail = document.querySelector("#status-detail");
const installButton = document.querySelector("#install-button");
const installMessage = document.querySelector("#install-message");

let monitoring = false;
let monitorTimer;
let installPrompt;

function formatTime(date) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function updateStatus() {
  const online = navigator.onLine;
  const state = online ? "online" : "offline";

  document.body.dataset.connection = state;
  linkState.value = online ? "Online" : "Offline";
  statusDetail.textContent = monitoring
    ? "Monitoring since " + formatTime(new Date())
    : "Monitor stopped";
}

function startMonitoring() {
  monitoring = true;
  startButton.setAttribute("aria-pressed", "true");
  startButton.textContent = "Stop Monitoring";
  monitorTimer = window.setInterval(updateStatus, 3000);
  updateStatus();
}

function stopMonitoring() {
  monitoring = false;
  startButton.setAttribute("aria-pressed", "false");
  startButton.textContent = "Start Network";
  window.clearInterval(monitorTimer);
  updateStatus();
}

startButton.addEventListener("click", () => {
  if (monitoring) {
    stopMonitoring();
  } else {
    startMonitoring();
  }
});

installButton.addEventListener("click", async () => {
  if (!installPrompt) {
    installMessage.textContent = "Open Chrome's menu and choose Install app.";
    return;
  }

  installPrompt.prompt();
  const choice = await installPrompt.userChoice;
  installMessage.textContent = choice.outcome === "accepted"
    ? "Installation started."
    : "Installation dismissed.";
  installPrompt = null;
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  installMessage.textContent = "Ready to install.";
});

window.addEventListener("appinstalled", () => {
  installPrompt = null;
  installButton.disabled = true;
  installButton.textContent = "App installed";
  installMessage.textContent = "";
});

window.addEventListener("online", updateStatus);
window.addEventListener("offline", updateStatus);
updateStatus();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch((error) => {
      console.error("Service worker registration failed:", error);
    });
  });
}