const config = {
  websocketUrl: import.meta.env.VITE_WS_URL || `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`,
  audioSampleRate: 16000,
  audioChannels: 1,
};

export default config;
