const api = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async send(path, method, body) {
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

const $ = (id) => document.getElementById(id);
const terminal = $("terminal");
let latestStatus = null;
let recognition = null;
let voiceEnabled = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function print(text) {
  terminal.textContent = `${new Date().toLocaleTimeString()}> ${text}\n\n${terminal.textContent}`.slice(0, 14000);
}

function setRing(id, value) {
  const fixed = Number(value || 0).toFixed(0);
  $(id).closest(".mini-ring").style.setProperty("--value", fixed);
  $(id).textContent = `${fixed}%`;
}

function setPill(id, text, hot = false) {
  const el = $(id);
  el.textContent = text;
  el.classList.toggle("hot", hot);
}

function openPanel(name) {
  $("drawerLayer").classList.add("open");
  document.querySelectorAll(".drawer-panel").forEach((panel) => {
    panel.classList.toggle("open", panel.dataset.panel === name);
  });
  document.querySelectorAll(".nav-card").forEach((button) => {
    button.classList.toggle("active", button.dataset.open === name);
  });
}

function closePanels() {
  $("drawerLayer").classList.remove("open");
  document.querySelectorAll(".drawer-panel, .nav-card").forEach((el) => el.classList.remove("open", "active"));
}

function browserSpeak(text) {
  if (!("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "it-IT";
  utterance.rate = 1;
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
}

async function systemSpeak(text) {
  try {
    await api.send("/api/voice/speak", "POST", { text });
  } catch {
    browserSpeak(text);
  }
}

function addMessage(role, text) {
  const log = $("chatLog");
  const div = document.createElement("div");
  div.className = `message ${role === "user" ? "user" : "jarvis"}`;
  div.innerHTML = `<small>${role === "user" ? "UTENTE" : "JARVIS"}</small>${escapeHtml(text)}`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  if (role !== "user") $("lastResponse").textContent = text;
}

function renderStatus(data) {
  latestStatus = data;
  setPill("apiState", "API ONLINE");
  setPill("brainState", data.brain.available ? `OLLAMA ${data.brain.model}` : "LOCAL FALLBACK", !data.brain.available);
  setPill("agentState", data.agent.status, ["PROCESSING", "EXECUTING", "QUEUED"].includes(data.agent.status));
  $("clock").textContent = new Date(data.time).toLocaleTimeString();
  setRing("cpu", data.system.cpu_percent);
  setRing("ram", data.system.ram_percent);
  setRing("disk", data.system.disk_percent);
  $("processes").textContent = data.system.process_count;
  $("python").textContent = data.system.python;
  $("runtimeState").textContent = data.runtime.running ? "CONTINUO" : "STOP";
  $("modelState").textContent = data.brain.available ? data.brain.model : "fallback";
  $("taskCount").textContent = data.tasks.length;
  $("memoryCount").textContent = data.memory_count;
  $("eventCount").textContent = data.events.length;
  renderTasks(data.tasks);
  renderEvents(data.events);
}

function renderTasks(tasks) {
  $("tasks").innerHTML = tasks
    .map(
      (task) => `
        <div class="item">
          <strong>${escapeHtml(task.title)}</strong>
          <code>${escapeHtml(task.action)}</code>
          <small>${escapeHtml(task.status)} · next ${task.next_run_iso ? new Date(task.next_run_iso).toLocaleString() : "manuale"}</small>
          <div class="item-actions">
            <button data-toggle="${task.id}">${task.status === "active" ? "Pausa" : "Avvia"}</button>
            <button data-delete-task="${task.id}">Elimina</button>
          </div>
        </div>
      `,
    )
    .join("");

  $("miniTasks").innerHTML = tasks.length
    ? tasks
        .slice(0, 4)
        .map(
          (task) => `
            <div class="mini-item">
              <span>${escapeHtml(task.title)}</span>
              <b>${escapeHtml(task.status)}</b>
            </div>
          `,
        )
        .join("")
    : '<div class="mini-item"><span>Nessun task attivo</span><b>OK</b></div>';
}

function renderEvents(events) {
  $("events").innerHTML = events
    .map(
      (event) => `
        <div class="event">
          <time>${new Date(event.created_at_iso).toLocaleTimeString()}</time>
          <span class="${escapeHtml(event.level)}">${escapeHtml(event.level)}</span>
          <span>${escapeHtml(event.message)}</span>
        </div>
      `,
    )
    .join("");

  $("miniEvents").innerHTML = events
    .slice(0, 4)
    .map(
      (event) => `
        <div class="mini-item">
          <span>${escapeHtml(event.message)}</span>
          <b class="${escapeHtml(event.level)}">${escapeHtml(event.level)}</b>
        </div>
      `,
    )
    .join("");
}

async function renderMemory() {
  const memory = await api.get("/api/memory");
  $("memoryList").innerHTML = Object.entries(memory)
    .map(
      ([key, value]) => `
        <div class="item">
          <strong>${escapeHtml(key)}</strong>
          <code>${escapeHtml(typeof value === "string" ? value : JSON.stringify(value))}</code>
          <div class="item-actions"><button data-delete-memory="${escapeHtml(key)}">Elimina</button></div>
        </div>
      `,
    )
    .join("");
}

async function refresh() {
  try {
    renderStatus(await api.get("/api/status"));
    await renderMemory();
  } catch (error) {
    setPill("apiState", "API ERROR", true);
    print(`Errore API: ${error.message}`);
  }
}

async function sendChat(message, source = "chat") {
  addMessage("user", message);
  setPill("agentState", "PROCESSING", true);
  const result = await api.send("/api/agent/chat", "POST", {
    message,
    source,
    speak: $("speakToggle").checked,
  });
  addMessage("jarvis", result.response || "Operazione completata.");
  await refresh();
  return result;
}

async function runCommand(command, confirmed = false) {
  print(`Esecuzione: ${command}`);
  const result = await api.send("/api/command", "POST", { command, confirmed });
  if (result.needs_confirmation && !confirmed) {
    const ok = window.confirm(`${result.error}\n\nConfermi l'esecuzione?`);
    if (ok) return runCommand(command, true);
    print("Comando annullato.");
    return result;
  }
  const output = [result.stdout, result.stderr].filter(Boolean).join("\n");
  print(output || `Comando terminato con codice ${result.returncode ?? "N/D"}`);
  await refresh();
  return result;
}

function setupVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setPill("voiceState", "VOICE N/D", true);
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = "it-IT";
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.onstart = () => {
    $("voiceWave").classList.add("active");
    setPill("voiceState", "LISTENING", true);
  };
  recognition.onresult = async (event) => {
    const transcript = event.results[event.results.length - 1][0].transcript;
    print(`Voce: ${transcript}`);
    try {
      const result = await api.send("/api/voice/transcript", "POST", { transcript, speak: true });
      if (result.wake && result.agent?.response) {
        addMessage("user", transcript);
        addMessage("jarvis", result.agent.response);
      }
      await refresh();
    } catch (error) {
      print(`Errore voce: ${error.message}`);
    }
  };
  recognition.onend = () => {
    $("voiceWave").classList.remove("active");
    setPill("voiceState", voiceEnabled ? "RESTARTING" : "VOICE OFF", voiceEnabled);
    if (voiceEnabled) {
      window.setTimeout(() => recognition.start(), 350);
    }
  };
  recognition.onerror = (event) => {
    print(`Voce: ${event.error}`);
  };
}

document.querySelectorAll("[data-open]").forEach((button) => {
  button.addEventListener("click", () => openPanel(button.dataset.open));
});

document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", closePanels);
});

$("drawerLayer").addEventListener("click", (event) => {
  if (event.target === $("drawerLayer")) closePanels();
});

$("refreshBtn").addEventListener("click", refresh);

$("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("chatInput");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  try {
    await sendChat(message);
  } catch (error) {
    addMessage("jarvis", `Errore: ${error.message}`);
  }
});

$("commandForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const command = $("commandInput").value.trim();
  if (!command) return;
  try {
    await runCommand(command);
  } catch (error) {
    print(`Errore: ${error.message}`);
  }
});

$("taskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    title: $("taskTitle").value.trim(),
    action: $("taskAction").value.trim(),
    delay_seconds: Number($("taskDelay").value || 0),
    interval_seconds: Number($("taskInterval").value || 0) || null,
  };
  if (!payload.title || !payload.action) return;
  try {
    await api.send("/api/tasks", "POST", payload);
    event.target.reset();
    await refresh();
  } catch (error) {
    print(`Errore task: ${error.message}`);
  }
});

$("memoryForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = $("memoryKey").value.trim();
  const value = $("memoryValue").value.trim();
  if (!key) return;
  try {
    await api.send("/api/memory", "POST", { key, value });
    event.target.reset();
    await refresh();
  } catch (error) {
    print(`Errore memoria: ${error.message}`);
  }
});

document.body.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.dataset.toggle) {
    await api.send(`/api/tasks/${target.dataset.toggle}/toggle`, "PATCH", {});
    await refresh();
  }
  if (target.dataset.deleteTask) {
    await api.send(`/api/tasks/${target.dataset.deleteTask}`, "DELETE", {});
    await refresh();
  }
  if (target.dataset.deleteMemory) {
    await api.send(`/api/memory/${encodeURIComponent(target.dataset.deleteMemory)}`, "DELETE", {});
    await refresh();
  }
});

$("voiceBtn").addEventListener("click", async () => {
  if (!recognition) return;
  voiceEnabled = !voiceEnabled;
  if (voiceEnabled) {
    recognition.start();
    await systemSpeak("JARVIS online. In ascolto.");
  } else {
    recognition.stop();
    setPill("voiceState", "VOICE OFF");
  }
});

$("pttBtn").addEventListener("click", async () => {
  if (!recognition) return;
  voiceEnabled = false;
  recognition.start();
  await systemSpeak("Dimmi pure.");
  window.setTimeout(() => recognition.stop(), 6500);
});

function wireVoiceTest(id) {
  const button = $(id);
  if (!button) return;
  button.addEventListener("click", () => systemSpeak("Sono online. Voce JARVIS operativa."));
}

wireVoiceTest("voiceTestBtn");
wireVoiceTest("voiceTestBtnPanel");

setupVoice();
addMessage("jarvis", "Sistema online. Schede chiuse, controllo vocale pronto.");
refresh();
setInterval(refresh, 2500);
