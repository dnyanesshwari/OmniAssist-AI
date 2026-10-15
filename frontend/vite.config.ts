import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/auth": backend,
      "/me": backend,
      "/services": backend,
      "/availability": backend,
      "/appointments": backend,
      "/conversations": backend,
      "/chat": backend,
      "/admin": backend,
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
