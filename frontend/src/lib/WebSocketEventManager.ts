import AudioPlayer from "./AudioPlayer";
import config from "./config";

const audioPlayer = new AudioPlayer();

export class WebSocketEventManager {
  public socket: WebSocket | null = null;
  private promptName: string | null = null;
  private audioContentName: string | null = null;
  public role: string | null = null;
  private isInitialized = false;
  private onDisconnectCallback: (() => void) | null;
  private onConnectCallback: (() => void) | null;
  private systemPrompt: string;
  private audioCleanup: (() => void) | null = null;
  private isProcessingAudio = false;
  private isPlayingAudio = false;
  private audioProcessor: ScriptProcessorNode | null = null;
  private audioContext: AudioContext | null = null;
  private audioStream: MediaStream | null = null;
  private voiceId = "tiffany";
  private endpointingSensitivity: "HIGH" | "MEDIUM" | "LOW" = "MEDIUM";
  private strandsTier = "sonnet";
  private currentAudioConfig: any = null;

  constructor(
    private wsUrl: string,
    onDisconnect?: () => void,
    onConnect?: () => void,
    systemPrompt?: string
  ) {
    this.onDisconnectCallback = onDisconnect || null;
    this.onConnectCallback = onConnect || null;
    this.systemPrompt =
      systemPrompt ||
      "You are a helpful assistant. Keep your responses short, generally two or three sentences.";
    this.connect();
  }

  connect(): void {
    if (this.socket) this.socket.close(1000, "Re-initializing");
    this.socket = new WebSocket(this.wsUrl);
    this.setupSocketListeners();
    this.isInitialized = false;
  }

  private setupSocketListeners(): void {
    if (!this.socket) return;

    this.socket.onopen = () => {
      this.onConnectCallback?.();
      this.startSession();
      audioPlayer.start();
    };

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
        if (data.event) {
          window.dispatchEvent(new CustomEvent("nova-sonic-event", { detail: data }));
        }
      } catch (e) {
        console.error("Parse error:", e);
      }
    };

    this.socket.onerror = () => {
      this.isInitialized = false;
    };

    this.socket.onclose = () => {
      audioPlayer.stop();
      this.isInitialized = false;
      this.promptName = null;
      this.audioContentName = null;
      this.onDisconnectCallback?.();
    };
  }

  private sendEvent(event: any): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    try {
      this.socket.send(JSON.stringify(event));
    } catch (e) {
      console.error("Send error:", e);
    }
  }

  private handleMessage(data: any): void {
    if (!data.event) return;
    const event = data.event;

    if (event.completionStart) {
      this.promptName = event.completionStart.promptName;
      this.isInitialized = true;
      this.pauseAudioProcessing();
    } else if (event.contentStart) {
      this.role = event.contentStart.role;
      if (event.contentStart.type === "AUDIO") {
        if (event.contentStart.role === "USER") {
          if (!this.audioContentName) {
            this.audioContentName = event.contentStart.contentName || null;
          }
        } else {
          this.currentAudioConfig = event.contentStart.audioOutputConfiguration || null;
          this.isInitialized = true;
          if (this.isProcessingAudio) this.pauseAudioProcessing();
        }
      }
    } else if (event.audioOutput) {
      if (this.currentAudioConfig) {
        const saved = this.audioContentName;
        if (!this.isPlayingAudio) {
          this.isPlayingAudio = true;
          if (this.isProcessingAudio) this.pauseAudioProcessing();
        }
        this.audioContentName = saved;
        audioPlayer.playAudio(this.base64ToFloat32(event.audioOutput.content));
      }
    } else if (event.contentEnd) {
      if (event.contentEnd.type === "TEXT") {
        if (event.contentEnd.stopReason?.toUpperCase() === "INTERRUPTED") {
          audioPlayer.bargeIn();
        }
        this.resumeAudioProcessing();
      } else if (event.contentEnd.type === "AUDIO") {
        const saved = { audioContentName: this.audioContentName, role: this.role };
        if (this.role === "ASSISTANT") this.isPlayingAudio = false;
        setTimeout(() => {
          this.audioContentName = saved.audioContentName;
          this.role = saved.role;
          this.resumeAudioProcessing();
        }, 100);
      }
    } else if (event.completionEnd) {
      this.resumeAudioProcessing();
    }
  }

  private base64ToFloat32(b64: string): Float32Array {
    const bin = window.atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const int16 = new Int16Array(bytes.buffer);
    const f32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768.0;
    return f32;
  }

  setEndpointingSensitivity(s: "HIGH" | "MEDIUM" | "LOW"): void {
    this.endpointingSensitivity = s;
  }

  setVoiceId(v: string): void {
    this.voiceId = v;
  }

  setStrandsTier(tier: string): void {
    this.strandsTier = tier;
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "config", strandsTier: tier }));
    }
  }

  private startSession(): void {
    this.sendEvent({
      event: {
        sessionStart: {
          inferenceConfiguration: { maxTokens: 4096, topP: 0.9, temperature: 0.7 },
          turnDetectionConfiguration: { endpointingSensitivity: this.endpointingSensitivity },
        },
      },
    });
    this.startPrompt();
  }

  private startPrompt(): void {
    const promptName = crypto.randomUUID();
    this.promptName = promptName;

    this.sendEvent({
      event: {
        promptStart: {
          promptName,
          textOutputConfiguration: { mediaType: "text/plain" },
          audioOutputConfiguration: {
            mediaType: "audio/lpcm",
            sampleRateHertz: 24000,
            sampleSizeBits: 16,
            channelCount: 1,
            voiceId: this.voiceId,
            encoding: "base64",
            audioType: "SPEECH",
          },
          toolUseOutputConfiguration: { mediaType: "application/json" },
          toolConfiguration: {
            tools: [
              {
                toolSpec: {
                  name: "getDateTool",
                  description: "Get the current date and time",
                  inputSchema: { json: '{"type":"object","properties":{},"required":[]}' },
                },
              },
              {
                toolSpec: {
                  name: "externalAgent",
                  description:
                    "Handle clinical tasks including patient matching, encounter management, symptom triage, facility lookup, and nurse escalation.",
                  inputSchema: {
                    json: '{"type":"object","properties":{"query":{"type":"string","description":"The task or question to process"}},"required":["query"]}',
                  },
                },
              },
            ],
          },
        },
      },
    });
    this.sendSystemPrompt();
  }

  private sendSystemPrompt(): void {
    if (!this.promptName) return;
    const cn = crypto.randomUUID();
    this.sendEvent({
      event: { contentStart: { promptName: this.promptName, contentName: cn, type: "TEXT", role: "SYSTEM", interactive: true, textInputConfiguration: { mediaType: "text/plain" } } },
    });
    this.sendEvent({
      event: { textInput: { promptName: this.promptName, contentName: cn, content: this.systemPrompt } },
    });
    this.sendEvent({
      event: { contentEnd: { promptName: this.promptName, contentName: cn } },
    });
    this.startAudioContent();
  }

  private pauseAudioProcessing(): void {
    if (!this.isProcessingAudio) return;
    this.isProcessingAudio = false;
    this.audioProcessor?.disconnect();
  }

  private resumeAudioProcessing(): void {
    if (!this.promptName || !this.isInitialized || this.isProcessingAudio) return;
    this.isProcessingAudio = true;
    if (this.audioProcessor && this.audioContext) {
      this.audioProcessor.connect(this.audioContext.destination);
    }
    if (!this.audioContentName) this.startAudioContent();
  }

  async startAudioContent(): Promise<void> {
    if (!this.promptName || this.isProcessingAudio) return;
    try {
      if (this.audioCleanup) { this.audioCleanup(); this.audioCleanup = null; }

      this.audioStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: config.audioChannels, sampleRate: config.audioSampleRate, sampleSize: 16, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });

      this.audioContext = new AudioContext({ sampleRate: config.audioSampleRate, latencyHint: "interactive" });
      if (this.audioContext.state === "suspended") await this.audioContext.resume();

      const source = this.audioContext.createMediaStreamSource(this.audioStream);
      this.audioProcessor = this.audioContext.createScriptProcessor(256, 1, 1);
      source.connect(this.audioProcessor);
      this.audioProcessor.connect(this.audioContext.destination);

      const audioContentName = crypto.randomUUID();
      this.audioContentName = audioContentName;

      this.sendEvent({
        event: {
          contentStart: {
            promptName: this.promptName, contentName: audioContentName, type: "AUDIO", interactive: true, role: "USER",
            audioInputConfiguration: { mediaType: "audio/lpcm", sampleRateHertz: config.audioSampleRate, sampleSizeBits: 16, channelCount: config.audioChannels, audioType: "SPEECH", encoding: "base64" },
          },
        },
      });

      this.audioProcessor.onaudioprocess = (e) => {
        if (!this.isProcessingAudio) return;
        const input = e.inputBuffer.getChannelData(0);
        const buf = new ArrayBuffer(input.length * 2);
        const view = new DataView(buf);
        for (let i = 0; i < input.length; i++) {
          view.setInt16(i * 2, Math.max(-32768, Math.min(32767, Math.round(input[i] * 32767))), true);
        }
        let data = "";
        for (let i = 0; i < view.byteLength; i++) data += String.fromCharCode(view.getUint8(i));
        this.sendAudioChunk(btoa(data));
      };

      this.audioCleanup = () => {
        this.audioProcessor?.disconnect();
        this.audioProcessor = null;
        this.audioStream?.getTracks().forEach((t) => t.stop());
        this.audioStream = null;
        this.audioContext?.close();
        this.audioContext = null;
      };

      this.isInitialized = true;
      this.isProcessingAudio = true;

      this.sendTextInput("hi");
    } catch (e) {
      console.error("Audio setup error:", e);
      this.cleanup();
    }
  }

  sendTextInput(text: string): void {
    if (!this.isInitialized || !this.promptName) return;
    const cn = crypto.randomUUID();
    this.sendEvent({ event: { contentStart: { promptName: this.promptName, contentName: cn, type: "TEXT", role: "USER", interactive: true, textInputConfiguration: { mediaType: "text/plain" } } } });
    this.sendEvent({ event: { textInput: { promptName: this.promptName, contentName: cn, content: text } } });
    this.sendEvent({ event: { contentEnd: { promptName: this.promptName, contentName: cn } } });
  }

  private sendAudioChunk(b64: string): void {
    if (!this.isInitialized || !this.promptName || !this.audioContentName) return;
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    try {
      this.socket.send(JSON.stringify({ event: { audioInput: { promptName: this.promptName, contentName: this.audioContentName, content: b64 } } }));
    } catch (e) { /* ignore */ }
  }

  cleanup(): void {
    try {
      this.audioCleanup?.();
      this.audioCleanup = null;
      this.isProcessingAudio = false;
      this.isPlayingAudio = false;

      if (this.socket?.readyState === WebSocket.OPEN) {
        this.sendEvent({ event: { sessionEnd: {} } });
      }
      if (this.socket && this.socket.readyState !== WebSocket.CLOSED && this.socket.readyState !== WebSocket.CLOSING) {
        this.socket.close(1000, "Cleanup");
      }
      this.isInitialized = false;
      this.promptName = null;
      this.audioContentName = null;
    } catch (e) {
      console.error("Cleanup error:", e);
    }
  }
}
