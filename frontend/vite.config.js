import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/mirrors": "http://backend:8000",
      "/health": "http://backend:8000",
      "/m": "http://backend:8000",
      "/r": "http://backend:8000",
      "/stats": "http://backend:8000"
    }
  }
});
