import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/interact-s2s": {
        target: "ws://localhost:8080",
        ws: true,
      },
      "/health": {
        target: "http://localhost:8080",
      },
    },
  },
});
