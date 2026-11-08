import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 웹은 렌더 엔진과 분리돼 있다: 미리보기·썸네일·자산은 모두 /api (server.mjs) 를 거친다.
export default defineConfig({
  plugins: [react()],
  publicDir: false,
  server: {
    port: 4311,
    proxy: {
      "/api": { target: "http://localhost:4310", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
