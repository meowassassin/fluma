import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import wasm from "vite-plugin-wasm";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// ArtCraft 공용 부품(src/vendor/artcraft/**, Fluma 심 _shims/**): `@storyteller/<이름>` → 소스.
// 목록은 tsconfig.json 의 compilerOptions.paths 한 곳에서만 관리한다(여기서는 읽어서 별칭으로 바꾼다).
const here = path.dirname(fileURLToPath(import.meta.url));
const tsPaths: Record<string, string[]> = JSON.parse(readFileSync(path.join(here, "tsconfig.json"), "utf8")).compilerOptions.paths ?? {};
const artcraftAlias = Object.entries(tsPaths)
  .filter(([k]) => k.startsWith("@storyteller/"))
  .map(([k, [target]]) => ({ find: new RegExp(`^${k.replace(/[/.-]/g, "\\$&")}$`), replacement: path.resolve(here, target) }));

// 웹은 렌더 엔진과 분리돼 있다: 미리보기·썸네일·자산은 모두 /api (server.mjs) 를 거친다.
// wasm · topLevelAwait: 영상 편집기(src/vendor/artcraft/video-editor)의 opencut-wasm 렌더러
export default defineConfig({
  plugins: [react(), wasm()],
  resolve: { alias: artcraftAlias, dedupe: ["react", "react-dom", "@preact/signals-core", "@preact/signals-react"] },
  optimizeDeps: { exclude: ["opencut-wasm"] },
  server: {
    port: 4311,
    proxy: {
      "/api": { target: "http://localhost:4310", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false, target: "es2022" },
});
