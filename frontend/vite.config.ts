import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/calls": "http://localhost:8000",
      "/personas": "http://localhost:8000",
      "/clips": "http://localhost:8000",
      "/voice": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
