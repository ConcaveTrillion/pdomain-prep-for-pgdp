import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FastAPI proxies /api/* during `npm run dev`. The dev server runs on :5173;
// the user starts FastAPI separately with `pgdp-prep --frontend-dev http://localhost:5173`.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8765",
      "/cdn": "http://localhost:8765",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
});
