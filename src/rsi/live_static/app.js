import { api, DoctorConnection } from "./realtime.js";

const $ = (id) => document.getElementById(id);
const state = {
  config: null,
  card: null,
  mode: "idle",
  status: "idle",
  messages: new Map(),
  start: 0,
  muted: false,
  previewTurn: 0,
  load: 0,
  epoch: 0,
};
const transport = new DoctorConnection({
  connected: () => {
    state.start = Date.now();
    setMode("live");
    activity("listening");
  },
  activity,
  transcript: addMessage,
  error: (error) => {
    showError(error.message);
    if (
      transport.pc?.connectionState === "failed" ||
      transport.pc?.connectionState === "disconnected"
    ) {
      setMode("idle");
      activity("ended");
    }
  },
  audioBlocked: () => {
    $("play-audio").hidden = false;
  },
  tool: ({ name, args, output }) => {
    if (name === "submit_diagnosis" && output.status === "submitted") {
      $("assessment-panel").hidden = false;
      $("assessment-diagnosis").textContent = args.diagnosis;
      $("assessment-reasoning").textContent = args.reasoning;
      $("assessment-differential").textContent = args.differential.length
        ? `Also considered: ${args.differential.join(", ")}`
        : "";
      $("verdict-badge").textContent = "COMPARING";
      $("assessment-verdict").textContent =
        "Comparing the assessment with the reference diagnosis…";
      return;
    }
    const text = output.findings?.length
      ? `${args.request}\n${output.findings.map((row) => `${row.name}: ${row.value}`).join("\n")}`
      : output.message;
    addMessage({ id: crypto.randomUUID(), role: "tool", text, final: true });
  },
  submitted: (id) => {
    void showResult(id, state.epoch);
  },
});

function showError(message) {
  $("error-message").textContent = message;
  $("error-banner").hidden = false;
}

async function refreshConfig() {
  state.config = await api("/api/config");
  $("connection-badge").classList.toggle("ready", state.config.configured);
  $("connection-badge").replaceChildren();
  $("connection-badge").append(
    document.createElement("i"),
    document.createTextNode(
      state.config.configured
        ? "Voice configured"
        : "Preview ready · add a key for voice",
    ),
  );
  if (state.mode === "idle")
    $("mode-label").textContent = state.config.configured
      ? "OpenAI Realtime voice"
      : "Voice ready to configure";
  $("start-button").disabled = !state.card || state.mode !== "idle";
}

function renderValue(value) {
  const wrapper = document.createElement("div");
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const entry = document.createElement("div");
      if (!Array.isArray(value)) {
        const label = document.createElement("strong");
        label.textContent = key.replaceAll("_", " ");
        entry.append(label);
      }
      entry.append(renderValue(child));
      wrapper.append(entry);
    }
  } else wrapper.textContent = String(value);
  return wrapper;
}

async function loadCase(id) {
  const load = ++state.load;
  ++state.epoch;
  await transport.close();
  setMode("idle");
  state.card = null;
  $("start-button").disabled = true;
  $("reveal-button").disabled = true;
  $("preview-button").disabled = true;
  $("patient-notes").replaceChildren();
  $("suggestions").replaceChildren();
  $("demographics").textContent = "Loading patient…";
  $("complaint").textContent = "—";
  $("answer-text").textContent = "";
  resetConversation();
  try {
    const card = await api(`/api/cases/${encodeURIComponent(id)}`);
    if (load !== state.load) return;
    state.card = card;
    $("patient-id").textContent = `PATIENT ${id.slice(-3)}`;
    $("patient-avatar").textContent = id.slice(-2);
    $("demographics").textContent = card.demographics;
    $("complaint").textContent = card.complaint;
    $("answer-text").textContent = card.answer;
    const fields = Object.entries(card.notes).filter(
      ([key]) => key !== "Demographics",
    );
    for (const [key, value] of fields) {
      const detail = document.createElement("details");
      detail.open = key === "History";
      const summary = document.createElement("summary");
      summary.textContent = key.replaceAll("_", " ");
      const content = renderValue(value);
      content.className = "note-content";
      detail.append(summary, content);
      $("patient-notes").append(detail);
    }
    for (const phrase of card.suggestions) {
      const button = document.createElement("button");
      button.className = "suggestion";
      button.textContent = phrase;
      button.addEventListener("click", () => {
        if (state.mode === "idle") startPreview();
        if (state.mode === "starting") return;
        $("text-input").value = phrase;
        $("text-input").focus();
      });
      $("suggestions").append(button);
    }
    $("case-select").value = id;
    $("case-select").disabled = false;
    $("reveal-button").disabled = false;
    $("preview-button").disabled = false;
    $("start-button").disabled = false;
  } catch (error) {
    showError(error.message);
  }
}

function resetConversation() {
  state.messages.clear();
  state.start = 0;
  state.previewTurn = 0;
  state.muted = false;
  $("transcript").replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.id = "empty-transcript";
  const quote = document.createElement("span");
  quote.textContent = "“";
  quote.setAttribute("aria-hidden", "true");
  const line = document.createElement("p");
  line.textContent = "Every good diagnosis begins with a question.";
  const small = document.createElement("small");
  small.textContent = "Your conversation will appear here as you talk.";
  empty.append(quote, line, small);
  $("transcript").append(empty);
  $("transcript-count").textContent = "Live transcript";
  $("export-button").disabled = true;
  $("assessment-panel").hidden = true;
  $("retry-grade").hidden = true;
  $("reference-answer").hidden = true;
  $("reveal-button").setAttribute("aria-expanded", "false");
  $("reveal-button").textContent = "Reveal diagnosis ↗";
  $("text-input").value = "";
  $("timer").textContent = "00:00";
  $("mute-button").setAttribute("aria-pressed", "false");
  $("mute-button").setAttribute("aria-label", "Mute microphone");
  $("play-audio").hidden = true;
  $("error-banner").hidden = true;
  activity("idle");
}

function setMode(mode) {
  state.mode = mode;
  const active = mode === "live" || mode === "preview";
  $("start-button").disabled = mode !== "idle" || !state.card;
  $("start-button").textContent =
    mode === "starting"
      ? "Connecting…"
      : mode === "live"
        ? "Voice visit in progress"
        : mode === "preview"
          ? "Text preview in progress"
          : "◉ Start voice visit";
  $("start-button").classList.toggle("loading", mode === "starting");
  $("end-button").disabled = !active && mode !== "starting";
  $("mute-button").disabled = mode !== "live";
  $("text-input").disabled = !active;
  $("send-button").disabled = !active;
  $("preview-button").disabled = mode !== "idle" || !state.card;
  $("case-select").disabled = mode === "starting" || mode === "live";
  $("mode-label").textContent =
    mode === "preview"
      ? "Scripted text preview · no AI or microphone"
      : "OpenAI Realtime voice";
  $("text-input").placeholder =
    mode === "preview"
      ? "Type a patient response to try the interface…"
      : "Or type what you’d like to say…";
}

function activity(status) {
  state.status = status;
  $("voice-stage").dataset.state = status;
  const labels = {
    idle: [
      "READY WHEN YOU ARE",
      "A little conversation. A lot of insight.",
      "Your doctor will ask questions, listen, and connect the dots.",
    ],
    starting: [
      "CONNECTING",
      "Opening the consultation room.",
      "Allow microphone access when your browser asks.",
    ],
    listening: [
      "YOUR TURN",
      "I’m listening.",
      "Tell me what’s been bothering you. Take your time.",
    ],
    hearing: [
      "MICROPHONE ACTIVE",
      "Go on. I’m here.",
      "Your voice is being shared with the doctor.",
    ],
    thinking: [
      "CONNECTING THE DOTS",
      "One thoughtful question at a time.",
      "The doctor is considering what you’ve shared.",
    ],
    speaking: [
      "DOCTOR SPEAKING",
      "Let’s understand this together.",
      "You can interrupt naturally, just like a conversation.",
    ],
    preview: [
      "TEXT PREVIEW · SCRIPTED",
      "Try the conversation flow.",
      "This preview uses scripted questions. Add a key for the AI doctor.",
    ],
    ended: [
      "VISIT ENDED",
      "Thanks for the conversation.",
      "Review your transcript or start a fresh consultation.",
    ],
  };
  const row = labels[status] || labels.idle;
  $("orb-label").textContent = row[0];
  $("voice-title").textContent = row[1];
  $("voice-description").textContent = row[2];
}

function addMessage({ id, role, text, delta, final }) {
  if (!id) return;
  $("empty-transcript")?.remove();
  let message = state.messages.get(id);
  const transcript = $("transcript");
  const shouldScroll =
    transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight <
    70;
  if (!message) {
    const element = document.createElement("div");
    element.className = `message ${role}`;
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.textContent =
      role === "assistant" ? "✚" : role === "tool" ? "↗" : "Y";
    avatar.setAttribute("aria-hidden", "true");
    const content = document.createElement("div");
    content.className = "message-content";
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent =
      role === "assistant"
        ? "Dr. Alex"
        : role === "tool"
          ? "Clinical findings"
          : "You · patient";
    const stamp = new Date();
    const time = document.createElement("time");
    time.dateTime = stamp.toISOString();
    time.textContent = stamp.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    label.append(time);
    const body = document.createElement("p");
    content.append(label, body);
    element.append(avatar, content);
    transcript.append(element);
    message = { role, text: "", body, element, time: stamp.toISOString() };
    state.messages.set(id, message);
  }
  if (delta !== undefined) {
    if (message.text === "Listening…") message.text = "";
    message.text += delta;
  } else if (text !== undefined) message.text = text;
  message.body.textContent = message.text;
  message.element.classList.toggle("pending", !final);
  $("export-button").disabled = false;
  $("transcript-count").textContent = `${state.messages.size} entries`;
  if (shouldScroll) transcript.scrollTop = transcript.scrollHeight;
}

function startPreview() {
  if (state.mode !== "idle" || !state.card) return;
  ++state.epoch;
  resetConversation();
  state.start = Date.now();
  setMode("preview");
  activity("preview");
  addMessage({
    id: crypto.randomUUID(),
    role: "assistant",
    text: "Hi, I’m Dr. Alex. What brings you in today?",
    final: true,
  });
  $("text-input").focus();
}

function previewReply() {
  const questions = [
    "That sounds uncomfortable. When did this start, and has it changed over time?",
    "Thank you. Have you started any new medications or treatments recently?",
    "Have you noticed any other symptoms, even ones that seem unrelated?",
    "Can you tell me a little about your medical history?",
    "In a live visit, I can request relevant exams and tests, then explain my assessment. This is the end of the scripted preview. Add your API key to try the real voice conversation.",
  ];
  const turn = state.previewTurn++;
  addMessage({
    id: crypto.randomUUID(),
    role: "assistant",
    text: questions[Math.min(turn, questions.length - 1)],
    final: true,
  });
  if (turn >= questions.length - 1) {
    setMode("idle");
    activity("ended");
  }
}

async function showResult(id, epoch) {
  try {
    const result = await api(`/api/sessions/${id}/result`);
    if (epoch !== state.epoch || !result.submitted) return;
    $("assessment-panel").hidden = false;
    $("assessment-diagnosis").textContent = result.assessment.diagnosis;
    $("assessment-reasoning").textContent = result.assessment.reasoning;
    $("assessment-differential").textContent = result.assessment.differential
      .length
      ? `Also considered: ${result.assessment.differential.join(", ")}`
      : "";
    $("verdict-badge").textContent = result.verdict.correct
      ? "MATCH"
      : "DIFFERENT";
    $("assessment-verdict").textContent = result.verdict.rationale;
    $("answer-text").textContent = result.answer;
    $("reference-answer").hidden = false;
    $("reveal-button").setAttribute("aria-expanded", "true");
    $("reveal-button").textContent = "Hide diagnosis ↗";
    $("retry-grade").hidden = true;
  } catch (error) {
    if (epoch !== state.epoch) return;
    showError(`Assessment recorded; comparison unavailable. ${error.message}`);
    $("assessment-panel").hidden = false;
    $("verdict-badge").textContent = "PENDING";
    $("assessment-verdict").textContent =
      "The assessment is saved. Retry the comparison when the service is available.";
    $("retry-grade").hidden = false;
  }
}

$("start-button").addEventListener("click", async () => {
  if (state.mode !== "idle" || !state.card) return;
  if (!state.config?.configured) {
    $("setup-dialog").showModal();
    return;
  }
  const epoch = ++state.epoch;
  resetConversation();
  setMode("starting");
  activity("starting");
  try {
    await transport.connect(state.card.id);
  } catch (error) {
    if (epoch === state.epoch) {
      showError(error.message);
      setMode("idle");
      activity("idle");
    }
  }
});
$("end-button").addEventListener("click", async () => {
  const id = transport.visitId;
  const epoch = state.epoch;
  setMode("idle");
  activity("ended");
  state.muted = false;
  $("mute-button").setAttribute("aria-pressed", "false");
  $("play-audio").hidden = true;
  await transport.close(false);
  if (id) void showResult(id, epoch);
});
$("mute-button").addEventListener("click", () => {
  state.muted = !state.muted;
  transport.mute(state.muted);
  $("mute-button").setAttribute("aria-pressed", String(state.muted));
  $("mute-button").setAttribute(
    "aria-label",
    state.muted ? "Unmute microphone" : "Mute microphone",
  );
  if (state.muted)
    $("voice-description").textContent =
      "Your microphone is muted. You can still type a response.";
  else activity("listening");
});
$("preview-button").addEventListener("click", startPreview);
$("text-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("text-input").value.trim();
  if (!text || !["live", "preview"].includes(state.mode)) return;
  try {
    if (state.mode === "live") transport.sendText(text);
    else {
      addMessage({ id: crypto.randomUUID(), role: "user", text, final: true });
      previewReply();
    }
    $("text-input").value = "";
  } catch (error) {
    showError(error.message);
  }
});
$("case-select").addEventListener("change", () => {
  void loadCase($("case-select").value);
});
$("reveal-button").addEventListener("click", () => {
  const reveal = $("reference-answer").hidden;
  $("reference-answer").hidden = !reveal;
  $("reveal-button").setAttribute("aria-expanded", String(reveal));
  $("reveal-button").textContent = reveal
    ? "Hide diagnosis ↗"
    : "Reveal diagnosis ↗";
});
$("retry-grade").addEventListener("click", () => {
  if (transport.visitId) void showResult(transport.visitId, state.epoch);
});
$("setup-button").addEventListener("click", () =>
  $("setup-dialog").showModal(),
);
$("close-setup").addEventListener("click", () => $("setup-dialog").close());
$("check-config").addEventListener("click", async () => {
  try {
    await refreshConfig();
    $("setup-status").textContent = state.config.configured
      ? "API key configured. Close this window and start your visit."
      : "No API key yet. Add it to .env and restart the server.";
  } catch (error) {
    $("setup-status").textContent = error.message;
  }
});
$("dismiss-error").addEventListener("click", () => {
  $("error-banner").hidden = true;
});
$("play-audio").addEventListener("click", () => {
  transport.audio
    .play()
    .then(() => {
      $("play-audio").hidden = true;
    })
    .catch((error) => showError(error.message));
});
$("export-button").addEventListener("click", () => {
  const lines = [...state.messages.values()]
    .map(
      (m) =>
        `${m.role === "assistant" ? "Dr. Alex" : m.role === "tool" ? "Clinical findings" : "Patient"}: ${m.text}`,
    )
    .join("\n\n");
  const text = `Doctor Live — ${state.card.id}\nMode: ${state.mode === "preview" || state.status === "preview" || state.previewTurn ? "Scripted preview" : "OpenAI voice"}\n${state.card.demographics}\n\n${lines}`;
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `doctor-live-${state.card.id}.txt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

window.addEventListener("pagehide", () => {
  void transport.close();
});
setInterval(() => {
  if (state.start && ["live", "preview", "starting"].includes(state.mode)) {
    const seconds = Math.floor((Date.now() - state.start) / 1000);
    $("timer").textContent =
      `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }
}, 1000);

const canvas = $("voice-canvas");
const ctx = canvas.getContext("2d");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const data = new Uint8Array(128);
function level(analyser) {
  if (!analyser) return 0;
  analyser.getByteTimeDomainData(data);
  return Math.min(
    1,
    Math.sqrt(
      data.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) /
        data.length,
    ) * 5,
  );
}
let smoothed = 0;
function draw(time) {
  const input = state.muted ? 0 : level(transport.inputAnalyser);
  const output = level(transport.outputAnalyser);
  smoothed = smoothed * 0.8 + Math.max(input, output) * 0.2;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const x = 260,
    y = 130,
    radius = 61 + smoothed * 15;
  const glow = ctx.createRadialGradient(x, y, 40, x, y, 125 + smoothed * 24);
  glow.addColorStop(0, "#c9dfb36b");
  glow.addColorStop(1, "#d9ecc000");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, 520, 290);
  for (let ring = 3; ring >= 0; ring--) {
    ctx.beginPath();
    for (let a = 0; a <= Math.PI * 2 + 0.03; a += 0.03) {
      const wobble = reducedMotion.matches
        ? 0
        : Math.sin(a * 5 + time * 0.0006 + ring) * (1.3 + smoothed * 5);
      const r = radius + ring * 9 + wobble;
      const px = x + Math.cos(a) * r,
        py = y + Math.sin(a) * r;
      if (a === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.strokeStyle = ["#6e916554", "#a5bd873f", "#b5c99a33", "#b5c99a24"][
      ring
    ];
    ctx.lineWidth = 1;
    ctx.stroke();
  }
  const sphere = ctx.createLinearGradient(x - 50, y - 60, x + 50, y + 60);
  sphere.addColorStop(0, "#769864");
  sphere.addColorStop(0.42, "#456c4c");
  sphere.addColorStop(1, "#1b4c3d");
  ctx.beginPath();
  ctx.arc(x, y, radius - 6, 0, Math.PI * 2);
  ctx.fillStyle = sphere;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x - 11, y - 12, 36, 0.9 * Math.PI, 1.75 * Math.PI);
  ctx.strokeStyle = "#d2e7b037";
  ctx.lineWidth = 0.8;
  ctx.stroke();
  // Bottom bars are microphone amplitude, not an idle or fabricated input animation.
  for (let i = 0; i < 31; i++) {
    const centre = 1 - Math.abs(i - 15) / 16;
    const amplitude = reducedMotion.matches
      ? input
      : input * (0.4 + 0.6 * Math.abs(Math.sin(i * 1.9 + time * 0.013)));
    const h = 2 + amplitude * centre * 22;
    ctx.fillStyle = input > 0.01 ? "#789f63" : "#bccbab";
    ctx.beginPath();
    ctx.roundRect(x - 90 + i * 6, 248 - h / 2, 2, h, 1);
    ctx.fill();
  }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

async function init() {
  try {
    const [config, cases] = await Promise.all([
      api("/api/config"),
      api("/api/cases"),
    ]);
    state.config = config;
    $("case-select").replaceChildren();
    for (const row of cases) {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = `${row.id.slice(-3)} · ${row.complaint}`;
      $("case-select").append(option);
    }
    await loadCase(config.default_case);
    await refreshConfig();
  } catch (error) {
    showError(`Could not load the demo. ${error.message}`);
  }
}
void init();
