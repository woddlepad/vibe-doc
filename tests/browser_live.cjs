// Browser integration checks. Requires Playwright and local Chromium, not an API key.
// NODE_PATH=/tmp/rsi-browser/node_modules node tests/browser_live.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const { chromium } = require("playwright");
const base = process.env.RSI_DEMO_URL || "http://127.0.0.1:8000";

async function unlock(page) {
  if (!(await page.locator("#login-form").isVisible())) return false;
  assert.ok(
    process.env.RSI_DEMO_PASSWORD,
    "Set RSI_DEMO_PASSWORD to test a password-protected demo.",
  );
  await page.locator("#password").fill(process.env.RSI_DEMO_PASSWORD);
  await page.locator("#login-submit").click();
  await page.waitForURL((url) => url.pathname === "/");
  const response = await page.request.get(`${base}/api/cases`);
  assert.equal(response.status(), 200);
  return true;
}

async function run() {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  const failures = [];
  let checks = 0;
  const checked = (label) => {
    checks++;
    console.log(`PASS ${label}`);
  };
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1080 },
      reducedMotion: "reduce",
    });
    page.on("pageerror", (error) => failures.push(error.message));
    const requests = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && !request.url().endsWith("/api/login"))
        requests.push(request.url());
    });
    await page.route("**/api/config", (route) =>
      route.fulfill({
        json: {
          configured: false,
          model: "gpt-realtime",
          default_case: "mqx-004",
        },
      }),
    );
    await page.goto(base);
    if (await unlock(page))
      checked("password sign-in persists across follow-up API requests");
    await page.getByText("62-year-old woman", { exact: true }).waitFor();
    assert.equal(await page.locator("#case-select option").count(), 115);
    assert.equal(await page.locator("#reference-answer").isVisible(), false);
    assert.equal(await page.locator("#text-input").isEnabled(), false);
    await page.locator("#reveal-button").click();
    assert.equal(
      await page
        .locator("#reference-answer")
        .innerText()
        .then((text) => text.includes("Acute interstitial nephritis")),
      true,
    );
    await page.locator("#reveal-button").click();
    await page.locator("#start-button").click();
    assert.equal(await page.locator("#setup-dialog").isVisible(), true);
    assert.equal(requests.length, 0);
    await page.keyboard.press("Escape");
    checked(
      "patient card, answer toggle, keyless setup; no upstream or microphone session",
    );

    await page.locator(".suggestion").first().click();
    assert.match(await page.locator("#mode-label").innerText(), /Scripted/);
    assert.match(await page.locator("#text-input").inputValue(), /tired/);
    await page.locator("#send-button").click();
    assert.equal(await page.locator(".message").count(), 3);
    assert.match(
      await page.locator(".message").last().innerText(),
      /When did this start/,
    );
    const downloadEvent = page.waitForEvent("download");
    await page.locator("#export-button").click();
    const download = await downloadEvent;
    const exportText = await fs.readFile(await download.path(), "utf8");
    assert.match(exportText, /Scripted preview/);
    assert.match(exportText, /Patient: I've been feeling/);
    assert.equal(exportText.includes("Acute interstitial nephritis"), false);
    checked(
      "scripted preview, phrase insertion, patient reply and transcript export",
    );

    await page.locator("#case-select").selectOption("mqx-016");
    await page.getByText("58-year-old female", { exact: true }).waitFor();
    assert.equal(await page.locator(".message").count(), 0);
    assert.equal(await page.locator("#reference-answer").isVisible(), false);
    assert.equal(await page.locator("#assessment-panel").isVisible(), false);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: "/tmp/doctor-live-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.locator("#case-select").selectOption("mqx-004");
    await page.getByText("62-year-old woman", { exact: true }).waitFor();
    await page.screenshot({
      path: "/tmp/doctor-live-desktop.png",
      fullPage: true,
    });
    checked("case switching clears private state; mobile fits viewport");
    await page.close();

    const voice = await browser.newPage({
      viewport: { width: 1440, height: 1080 },
    });
    voice.on("pageerror", (error) => failures.push(error.message));
    // A real browser MediaStream and AudioContext with synthetic input; no physical mic or API.
    await voice.addInitScript(() => {
      window.__sent = [];
      window.__tracks = [];
      window.__peers = [];
      window.__micCount = 0;
      navigator.mediaDevices.getUserMedia = async () => {
        window.__micCount++;
        if (window.__denyMic)
          throw new DOMException("Permission denied", "NotAllowedError");
        const context = new AudioContext();
        await context.resume();
        const source = context.createOscillator();
        source.frequency.value = 220;
        const gain = context.createGain();
        gain.gain.value = 0.1;
        const destination = context.createMediaStreamDestination();
        source.connect(gain).connect(destination);
        source.start();
        const stream = destination.stream;
        window.__tracks.push(...stream.getTracks());
        stream.getTracks()[0].addEventListener("ended", () => {
          source.stop();
          void context.close();
        });
        return stream;
      };
      class Channel extends EventTarget {
        readyState = "connecting";
        send(value) {
          window.__sent.push(JSON.parse(value));
        }
        close() {
          this.readyState = "closed";
          this.dispatchEvent(new Event("close"));
        }
        emit(event) {
          this.onmessage?.({ data: JSON.stringify(event) });
        }
      }
      class Peer {
        connectionState = "new";
        constructor() {
          window.__peers.push(this);
        }
        addTrack() {}
        createDataChannel() {
          return (this.channel = window.__channel = new Channel());
        }
        async createOffer() {
          return { type: "offer", sdp: "v=0\r\nmock-browser-sdp" };
        }
        async setLocalDescription(offer) {
          this.localDescription = offer;
        }
        async setRemoteDescription() {
          this.connectionState = "connected";
          this.channel.readyState = "open";
          this.channel.dispatchEvent(new Event("open"));
        }
        close() {
          this.connectionState = "closed";
        }
      }
      window.RTCPeerConnection = Peer;
      window.__emit = (event) => window.__channel.emit(event);
    });
    const bodies = [];
    await voice.route("**/api/config", (route) =>
      route.fulfill({
        json: {
          configured: true,
          model: "gpt-realtime",
          default_case: "mqx-004",
        },
      }),
    );
    await voice.route("**/api/sessions", async (route) => {
      bodies.push(route.request().postDataJSON());
      if (bodies.length === 2)
        await new Promise((resolve) => setTimeout(resolve, 250));
      await route.fulfill({
        json: { id: "mock-visit", sdp: "v=0\r\nmock-answer" },
      });
    });
    await voice.route("**/api/sessions/mock-visit", (route) =>
      route.fulfill({ json: { ended: true } }),
    );
    let toolRequests = 0;
    await voice.route("**/api/sessions/mock-visit/tools", async (route) => {
      toolRequests++;
      const body = route.request().postDataJSON();
      assert.ok(body.call_id);
      await route.fulfill({
        json:
          body.name === "submit_diagnosis"
            ? {
                output: {
                  status: "submitted",
                  message: "Assessment recorded.",
                },
              }
            : {
                output: {
                  findings: [
                    {
                      name: "Serum biochemistry / Creatinine",
                      value: "Elevated",
                    },
                  ],
                  requests_left: 9,
                  message: "Recorded results.",
                },
              },
      });
    });
    await voice.route("**/api/sessions/mock-visit/result", (route) =>
      route.fulfill({
        json: {
          submitted: true,
          answer: "Acute interstitial nephritis",
          assessment: {
            diagnosis: "AIN",
            reasoning: "Recent drug exposure and renal findings.",
            differential: ["Pyelonephritis"],
          },
          verdict: { correct: true, rationale: "AIN is the abbreviation." },
          findings: [],
        },
      }),
    );
    await voice.goto(base);
    await unlock(voice);
    await voice.getByText("62-year-old woman", { exact: true }).waitFor();
    await voice.locator("#start-button").click();
    await voice.getByText("Voice visit in progress", { exact: true }).waitFor();
    assert.equal(await voice.locator("#mute-button").isEnabled(), true);
    assert.equal(await voice.locator("#case-select").isEnabled(), false);
    assert.deepEqual(Object.keys(bodies[0]).sort(), ["case_id", "sdp"]);
    assert.equal(
      JSON.stringify(bodies).includes("Acute interstitial nephritis"),
      false,
    );
    assert.equal(
      await voice.evaluate(() => window.__sent[0].type),
      "response.create",
    );
    checked(
      "mocked WebRTC startup uses only case ID and SDP, no private role card",
    );

    const emit = (event) =>
      voice.evaluate((event) => window.__emit(event), event);
    await emit({ type: "response.created" });
    await emit({
      type: "response.output_audio_transcript.delta",
      item_id: "doctor-1",
      delta: "Hello. ",
    });
    await emit({
      type: "response.output_audio_transcript.delta",
      item_id: "doctor-1",
      delta: "What brings you in?",
    });
    await emit({
      type: "response.output_audio_transcript.done",
      item_id: "doctor-1",
      transcript: "Hello. What brings you in?",
    });
    await emit({
      type: "response.done",
      response: { status: "completed", output: [] },
    });
    await emit({
      type: "input_audio_buffer.speech_started",
      item_id: "patient-1",
    });
    await emit({
      type: "conversation.item.input_audio_transcription.delta",
      item_id: "patient-1",
      delta: "I have a fever.",
    });
    await emit({
      type: "conversation.item.input_audio_transcription.completed",
      item_id: "patient-1",
      transcript: "I have a fever.",
    });
    assert.equal(await voice.locator(".message").count(), 2);
    assert.match(
      await voice.locator(".message").first().innerText(),
      /Hello\. What brings/,
    );
    await voice.locator("#mute-button").click();
    assert.equal(await voice.evaluate(() => window.__tracks[0].enabled), false);
    assert.equal(
      await voice.locator("#mute-button").getAttribute("aria-pressed"),
      "true",
    );
    await voice.locator("#mute-button").click();
    assert.equal(await voice.evaluate(() => window.__tracks[0].enabled), true);
    await voice
      .locator("#text-input")
      .fill("My symptoms started after antibiotics.");
    await voice.locator("#send-button").click();
    assert.equal(
      await voice.evaluate(
        () =>
          window.__sent.filter(
            (event) =>
              event.type === "conversation.item.create" &&
              event.item.type === "message",
          ).length,
      ),
      1,
    );
    assert.equal(
      await voice.evaluate(() =>
        window.__sent
          .filter((event) => event.item?.type === "message")
          .every((event) => event.item.id.length <= 32),
      ),
      true,
    );
    checked(
      "streaming transcripts, real MediaStream mute/unmute and typed voice messages",
    );

    const toolDone = {
      type: "response.done",
      response: {
        status: "completed",
        output: [
          {
            type: "function_call",
            name: "order_test",
            call_id: "test-1",
            arguments: JSON.stringify({ request: "renal biochemistry" }),
          },
        ],
      },
    };
    await emit(toolDone);
    await voice
      .getByText("Serum biochemistry / Creatinine: Elevated", { exact: false })
      .waitFor();
    await emit(toolDone);
    assert.equal(toolRequests, 1);
    await emit({
      type: "response.done",
      response: {
        status: "completed",
        output: [
          {
            type: "function_call",
            name: "submit_diagnosis",
            call_id: "diagnosis-1",
            arguments: JSON.stringify({
              diagnosis: "AIN",
              reasoning: "Recent drug exposure and renal findings.",
              differential: ["Pyelonephritis"],
            }),
          },
        ],
      },
    });
    await voice
      .getByText("AIN is the abbreviation.", { exact: true })
      .waitFor();
    assert.equal(await voice.locator("#verdict-badge").innerText(), "MATCH");
    assert.equal(
      await voice.evaluate(() =>
        JSON.stringify(window.__sent).includes("Acute interstitial nephritis"),
      ),
      false,
    );
    assert.equal(
      await voice.evaluate(() =>
        window.__sent.some(
          (event) =>
            event.item?.type === "function_call_output" &&
            JSON.parse(event.item.output).correct !== undefined,
        ),
      ),
      false,
    );
    checked(
      "tool callbacks deduplicate; grading and answer never go back to the doctor",
    );

    await voice.locator("#end-button").click();
    await voice.waitForFunction(() =>
      window.__tracks.every((track) => track.readyState === "ended"),
    );
    assert.equal(await voice.locator("#text-input").isEnabled(), false);
    assert.equal(
      await voice.evaluate(() =>
        window.__peers.every((peer) => peer.connectionState === "closed"),
      ),
      true,
    );
    assert.ok((await voice.locator(".message").count()) >= 3);
    checked(
      "ending releases microphone and peer connection while preserving transcript",
    );

    await voice.locator("#start-button").click();
    await voice.getByText("Connecting…", { exact: true }).waitFor();
    await voice.locator("#end-button").click();
    await voice.waitForFunction(() =>
      window.__tracks.every((track) => track.readyState === "ended"),
    );
    await voice.waitForTimeout(350);
    assert.equal(await voice.locator("#start-button").isEnabled(), true);
    assert.equal(await voice.locator("#text-input").isEnabled(), false);
    checked(
      "cancelling startup prevents a late connection and cleans up media",
    );

    await voice.evaluate(() => {
      window.__denyMic = true;
    });
    await voice.locator("#start-button").click();
    await voice
      .getByText("Microphone permission was denied.", { exact: false })
      .waitFor();
    assert.equal(await voice.locator("#start-button").isEnabled(), true);
    checked(
      "microphone denial reports recovery instructions and restores controls",
    );
    assert.deepEqual(failures, []);
    console.log(`${checks} browser checks passed; no page errors.`);
  } finally {
    await browser.close();
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
