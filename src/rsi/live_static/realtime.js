/** OpenAI media transport. Never accepts patient notes, suggestions or the answer key. */
export async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}).`,
    );
  }
  return response.json();
}

export class DoctorConnection {
  constructor(callbacks = {}) {
    this.callbacks = callbacks;
    this.generation = 0;
    this.audio = new Audio();
    this.audio.autoplay = true;
    this.audio.addEventListener("ended", () =>
      this.callbacks.activity?.("listening"),
    );
    this.toolCalls = new Set();
  }

  send(event) {
    if (this.dc?.readyState !== "open")
      throw new Error("The voice connection is not ready. Start a new visit.");
    this.dc.send(JSON.stringify(event));
  }

  async connect(caseId) {
    await this.close();
    const generation = ++this.generation;
    const current = () => generation === this.generation;
    this.toolCalls.clear();
    this.responseActive = false;
    this.pendingResponse = false;
    this.abort = new AbortController();
    const abort = this.abort;
    const startupTimer = setTimeout(() => abort.abort(), 50000);
    try {
      if (!window.isSecureContext)
        throw new Error(
          "Microphone access needs localhost or HTTPS. Open http://localhost:8000 on this machine.",
        );
      if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection)
        throw new Error(
          "This browser does not support microphone voice calls. Use a current Chrome, Edge, Firefox or Safari.",
        );
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (!current()) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      this.stream = stream;
      this.context = new AudioContext();
      await this.context.resume();
      this.inputAnalyser = this.context.createAnalyser();
      this.inputAnalyser.fftSize = 256;
      this.context.createMediaStreamSource(stream).connect(this.inputAnalyser);
      const pc = (this.pc = new RTCPeerConnection());
      stream.getTracks().forEach((track) => pc.addTrack(track, stream));
      pc.ontrack = (event) => {
        if (!current()) return;
        this.audio.srcObject =
          event.streams[0] || new MediaStream([event.track]);
        this.outputAnalyser = this.context.createAnalyser();
        this.outputAnalyser.fftSize = 256;
        this.context
          .createMediaStreamSource(this.audio.srcObject)
          .connect(this.outputAnalyser);
        this.audio.play().catch(() => this.callbacks.audioBlocked?.());
      };
      pc.onconnectionstatechange = () => {
        if (!current()) return;
        if (["failed", "disconnected"].includes(pc.connectionState)) {
          this.callbacks.error?.(
            new Error(
              "The voice connection was interrupted. Start a new visit to reconnect.",
            ),
          );
          void this.close(false);
        }
      };
      this.dc = pc.createDataChannel("oai-events");
      this.dc.onmessage = (event) => {
        if (!current()) return;
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        void this.handleEvent(data, generation).catch((error) => {
          if (current()) this.callbacks.error?.(error);
        });
      };
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const visit = await api("/api/sessions", {
        method: "POST",
        signal: abort.signal,
        body: JSON.stringify({ case_id: caseId, sdp: offer.sdp }),
      });
      if (!current()) {
        void api(`/api/sessions/${visit.id}`, { method: "DELETE" }).catch(
          () => {},
        );
        return;
      }
      this.visitId = visit.id;
      await pc.setRemoteDescription({ type: "answer", sdp: visit.sdp });
      await new Promise((resolve, reject) => {
        if (this.dc.readyState === "open") return resolve();
        const dc = this.dc;
        const cancel = () => {
          cleanup();
          reject(new DOMException("Startup cancelled.", "AbortError"));
        };
        const opened = () => {
          cleanup();
          resolve();
        };
        const closed = () => {
          cleanup();
          reject(
            new Error("The voice channel closed before the visit started."),
          );
        };
        const cleanup = () => {
          dc.removeEventListener("open", opened);
          dc.removeEventListener("close", closed);
          abort.signal.removeEventListener("abort", cancel);
        };
        dc.addEventListener("open", opened);
        dc.addEventListener("close", closed);
        abort.signal.addEventListener("abort", cancel);
        if (abort.signal.aborted) cancel();
      });
      if (!current()) return;
      this.callbacks.connected?.();
      this.requestResponse();
    } catch (error) {
      if (current()) {
        await this.close();
        if (error.name === "NotAllowedError")
          throw new Error(
            "Microphone permission was denied. Allow the microphone in your browser’s site settings, then try again.",
          );
        if (error.name === "NotFoundError")
          throw new Error(
            "No microphone was found. Connect one and start a new visit.",
          );
        if (error.name === "AbortError")
          throw new Error(
            "The voice connection timed out. Check your connection and try again.",
          );
        throw error;
      }
    } finally {
      clearTimeout(startupTimer);
    }
  }

  requestResponse() {
    if (this.responseActive) {
      this.pendingResponse = true;
      return;
    }
    this.pendingResponse = false;
    // Reserve the slot until response.created arrives, preventing duplicate responses.
    this.responseActive = true;
    this.send({ type: "response.create" });
  }

  sendText(text) {
    if (this.responseActive) {
      this.send({ type: "response.cancel" });
      this.send({ type: "output_audio_buffer.clear" });
    }
    const id = `item_${crypto.randomUUID().replaceAll("-", "").slice(0, 27)}`;
    this.send({
      type: "conversation.item.create",
      item: {
        id,
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    });
    this.callbacks.transcript?.({ id, role: "user", text, final: true });
    this.requestResponse();
  }

  async handleEvent(event, generation) {
    if (generation !== this.generation) return;
    switch (event.type) {
      case "input_audio_buffer.speech_started":
        this.callbacks.activity?.("hearing");
        if (event.item_id)
          this.callbacks.transcript?.({
            id: event.item_id,
            role: "user",
            text: "Listening…",
            final: false,
          });
        break;
      case "input_audio_buffer.speech_stopped":
        this.callbacks.activity?.("thinking");
        break;
      case "conversation.item.input_audio_transcription.delta":
        this.callbacks.transcript?.({
          id: event.item_id,
          role: "user",
          delta: event.delta,
          final: false,
        });
        break;
      case "conversation.item.input_audio_transcription.completed":
        this.callbacks.transcript?.({
          id: event.item_id,
          role: "user",
          text: event.transcript,
          final: true,
        });
        break;
      case "conversation.item.input_audio_transcription.failed":
        this.callbacks.transcript?.({
          id: event.item_id,
          role: "user",
          text: "[Audio transcription unavailable]",
          final: true,
        });
        break;
      case "response.created":
        this.responseActive = true;
        this.callbacks.activity?.("thinking");
        break;
      case "output_audio_buffer.started":
        this.callbacks.activity?.("speaking");
        break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        this.callbacks.activity?.("listening");
        break;
      case "response.output_audio_transcript.delta":
      case "response.output_text.delta":
        this.callbacks.transcript?.({
          id: event.item_id,
          role: "assistant",
          delta: event.delta,
          final: false,
        });
        break;
      case "response.output_audio_transcript.done":
      case "response.output_text.done":
        this.callbacks.transcript?.({
          id: event.item_id,
          role: "assistant",
          text: event.transcript ?? event.text,
          final: true,
        });
        break;
      case "response.done": {
        this.responseActive = false;
        if (event.response.status === "failed") {
          this.callbacks.error?.(
            new Error(
              "The doctor could not generate a response. Try another message or start a new visit.",
            ),
          );
          return;
        }
        const calls =
          event.response.status === "completed"
            ? (event.response.output || []).filter(
                (item) =>
                  item.type === "function_call" &&
                  !this.toolCalls.has(item.call_id),
              )
            : [];
        for (const call of calls) {
          this.toolCalls.add(call.call_id);
          this.callbacks.activity?.("thinking");
          let args;
          let result;
          try {
            args = JSON.parse(call.arguments);
            result = await api(`/api/sessions/${this.visitId}/tools`, {
              method: "POST",
              body: JSON.stringify({
                name: call.name,
                call_id: call.call_id,
                arguments: args,
              }),
            });
          } catch (error) {
            // Give the doctor a recoverable tool failure, with no private UI or grading data.
            result = {
              output: {
                status: "error",
                message:
                  "The requested operation failed. Do not invent a result. Retry with a new request or continue the interview.",
              },
            };
            if (generation === this.generation) this.callbacks.error?.(error);
          }
          if (generation !== this.generation || this.dc?.readyState !== "open")
            return;
          this.send({
            type: "conversation.item.create",
            item: {
              type: "function_call_output",
              call_id: call.call_id,
              output: JSON.stringify(result.output),
            },
          });
          this.callbacks.tool?.({
            name: call.name,
            args,
            output: result.output,
          });
          if (result.output.status === "submitted")
            this.callbacks.submitted?.(this.visitId);
        }
        if (generation !== this.generation) return;
        if (calls.length || this.pendingResponse) this.requestResponse();
        break;
      }
      case "error":
        if (event.error?.code === "response_cancel_not_active") return;
        this.callbacks.error?.(
          new Error(
            event.error?.message || "The voice service returned an error.",
          ),
        );
        break;
    }
  }

  mute(muted) {
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }

  async close(deleteVisit = true) {
    ++this.generation;
    this.abort?.abort();
    this.dc?.close();
    this.pc?.close();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.audio.pause();
    this.audio.srcObject = null;
    const context = this.context;
    this.context = null;
    this.inputAnalyser = this.outputAnalyser = null;
    this.dc = this.pc = this.stream = null;
    this.responseActive = this.pendingResponse = false;
    if (context && context.state !== "closed")
      await context.close().catch(() => {});
    if (deleteVisit && this.visitId) {
      const id = this.visitId;
      this.visitId = null;
      void api(`/api/sessions/${id}`, { method: "DELETE" }).catch(() => {});
    }
  }
}
