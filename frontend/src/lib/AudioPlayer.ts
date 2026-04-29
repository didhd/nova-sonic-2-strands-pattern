const audioPlayerProcessorCode = `
class AudioPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.isPlaying = false;
    this.port.onmessage = this.handleMessage.bind(this);
  }
  handleMessage(event) {
    const data = event.data;
    switch (data.type) {
      case "audio":
        this.buffer.push(...data.audioData);
        if (!this.isPlaying) this.isPlaying = true;
        break;
      case "barge-in":
        this.buffer = [];
        this.isPlaying = false;
        break;
    }
  }
  process(inputs, outputs) {
    const output = outputs[0];
    const channel = output[0];
    if (this.isPlaying && this.buffer.length > 0) {
      const n = Math.min(channel.length, this.buffer.length);
      for (let i = 0; i < n; i++) channel[i] = this.buffer.shift();
      for (let i = n; i < channel.length; i++) channel[i] = 0;
    } else {
      for (let i = 0; i < channel.length; i++) channel[i] = 0;
    }
    return true;
  }
}
registerProcessor("audio-player-processor", AudioPlayerProcessor);
`;

export default class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private initialized = false;

  async start(): Promise<void> {
    this.audioContext = new AudioContext({ sampleRate: 24000 });
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 512;

    const blob = new Blob([audioPlayerProcessorCode], { type: "application/javascript" });
    const url = URL.createObjectURL(blob);
    try {
      await this.audioContext.audioWorklet.addModule(url);
      this.workletNode = new AudioWorkletNode(this.audioContext, "audio-player-processor");
      this.workletNode.connect(this.analyser);
      this.analyser.connect(this.audioContext.destination);
      this.initialized = true;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  bargeIn(): void {
    this.workletNode?.port.postMessage({ type: "barge-in" });
  }

  stop(): void {
    this.audioContext?.close();
    this.analyser?.disconnect();
    this.workletNode?.disconnect();
    this.initialized = false;
    this.audioContext = null;
    this.analyser = null;
    this.workletNode = null;
  }

  playAudio(samples: Float32Array): void {
    if (!this.initialized || !this.workletNode) return;
    this.workletNode.port.postMessage({ type: "audio", audioData: samples });
  }

  getVolume(): number {
    if (!this.initialized || !this.analyser) return 0;
    const buf = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(buf);
    const norm = Array.from(buf).map((e) => e / 128 - 1);
    let sum = 0;
    for (const s of norm) sum += s * s;
    return Math.sqrt(sum / norm.length);
  }
}
