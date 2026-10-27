import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// Built into demo/console/, which src/serve.py serves at /console/. The dev server proxies /api to serve.py.
export default defineConfig({
  plugins: [preact()],
  base: "./",
  build: { outDir: "../demo/console", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
