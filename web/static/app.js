const form = document.getElementById("chatForm");
const input = document.getElementById("messageInput");
const messages = document.getElementById("messages");
const statusText = document.getElementById("statusText");
const typingIndicator = document.getElementById("typingIndicator");
const sendButton = document.getElementById("sendButton");
const themeToggle = document.getElementById("themeToggle");
const thinkingLog = document.getElementById("thinkingLog");
const thinkingText = document.getElementById("thinkingText");

const storageKey = "agente-maritimo-theme";
const history = [];

function applyTheme(theme) {
  document.body.dataset.theme = theme;
  const label = theme === "light" ? "Light Mode" : "Dark Mode";
  themeToggle.querySelector(".theme-toggle__label").textContent = label;
  localStorage.setItem(storageKey, theme);
}

function appendMessage(role, content) {
  const wrapper = document.createElement("article");
  wrapper.className = `message message--${role}`;

  const avatar = document.createElement("div");
  avatar.className = "message__avatar";
  avatar.textContent = role === "user" ? "VO" : "AM";

  const bubble = document.createElement("div");
  bubble.className = "message__bubble";
  bubble.textContent = content;

  wrapper.appendChild(avatar);
  wrapper.appendChild(bubble);
  messages.appendChild(wrapper);
  messages.scrollTop = messages.scrollHeight;
}

function setLoading(isLoading) {
  typingIndicator.classList.toggle("typing--hidden", !isLoading);
  thinkingLog.classList.toggle("thinking-log--hidden", !isLoading);
  sendButton.disabled = isLoading;
  input.disabled = isLoading;
  statusText.textContent = isLoading
    ? "Consultando os dados em tempo real. Vou esperar a resposta ficar pronta."
    : "Pronto para analisar o mar.";

  if (isLoading) {
    thinkingText.textContent = "Consultando swell, vento e marés em tempo real. Isso pode levar um pouco mais.";
    messages.scrollTop = messages.scrollHeight;
  }
}

async function sendMessage(message) {
  appendMessage("user", message);
  history.push({ role: "user", content: message });
  setLoading(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        history,
      }),
    });
    const rawText = await response.text();
    let data;
    try {
      data = JSON.parse(rawText);
    } catch {
      throw new Error("O servidor retornou uma resposta inválida.");
    }

    if (!response.ok) {
      throw new Error(data.error || "Falha ao consultar o agente.");
    }

    appendMessage("assistant", data.reply);
    history.push({ role: "assistant", content: data.reply });
    statusText.textContent = `Resposta pronta em ${data.duration_seconds ?? "alguns"}s.`;
  } catch (error) {
    const messageText = `Não consegui responder agora: ${error.message}`;
    appendMessage("assistant", messageText);
    statusText.textContent = "A resposta demorou demais ou falhou.";
  } finally {
    setLoading(false);
    input.focus();
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) {
    return;
  }

  input.value = "";
  input.style.height = "auto";
  await sendMessage(message);
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
});

document.querySelectorAll(".chip").forEach((button) => {
  button.addEventListener("click", async () => {
    input.value = button.textContent.trim();
    input.dispatchEvent(new Event("input"));
    await sendMessage(input.value.trim());
    input.value = "";
    input.style.height = "auto";
  });
});

themeToggle.addEventListener("click", () => {
  const current = document.body.dataset.theme === "light" ? "dark" : "light";
  applyTheme(current);
});

applyTheme(localStorage.getItem(storageKey) || "dark");
