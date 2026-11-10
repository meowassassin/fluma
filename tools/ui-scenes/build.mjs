// 영상 · 데모 속 UI 화면 만들기 — 장면 파일(.tsx, Astryx 컴포넌트) 하나 → 정적 페이지(dist/index.html) · 원하면 PNG.
//   node tools/ui-scenes/build.mjs <장면.tsx> <출력 폴더> [--mode dark|light] [--png 1080x1920]
// 장면 파일은 default export 로 React 컴포넌트 하나(props 없음). 컴포넌트 문서: npm --prefix tools/ui-scenes run -s astryx -- component <이름>
// 페이지는 file:// 로 열린다(상대 경로) → engine/capture/uianim.py 로 움직이게 하거나 webrec 으로 녹화한다.
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { mkdirSync, copyFileSync, writeFileSync, readFileSync, rmSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const here = path.dirname(fileURLToPath(import.meta.url));
const [scene, outDir, ...rest] = process.argv.slice(2);
if (!scene || !outDir) { console.error("사용: node tools/ui-scenes/build.mjs <장면.tsx> <출력 폴더> [--mode dark] [--png 1080x1920]"); process.exit(2); }
const opt = (k, d) => { const i = rest.indexOf(k); return i >= 0 ? rest[i + 1] : d; };
const mode = opt("--mode", "dark");
const work = path.join(here, ".build");
rmSync(work, { recursive: true, force: true }); mkdirSync(work, { recursive: true });
// 장면을 작업 공간 안으로 복사 — 그래야 @astryxdesign · react 가 이 폴더의 node_modules 에서 풀린다
copyFileSync(path.resolve(scene), path.join(work, "scene.tsx"));
writeFileSync(path.join(work, "main.tsx"), `import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { Theme } from '@astryxdesign/core/theme';
import { neutralTheme } from '@astryxdesign/theme-neutral/built';
import Scene from './scene';
createRoot(document.getElementById('root')!).render(<Theme theme={neutralTheme} mode=${JSON.stringify(mode)}><Scene /></Theme>);
`);
writeFileSync(path.join(work, "index.html"), `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>scene</title>
<style>html,body,#root{height:100%;margin:0}</style></head><body><div id="root"></div><script type="module" src="./main.tsx"></script></body></html>`);
// 먼저 타입 검사 — 없는 속성(예: Badge 는 children 이 아니라 label) · 잘못된 값을 렌더 전에 잡는다
writeFileSync(path.join(work, "tsconfig.json"), JSON.stringify({ compilerOptions: { target: "ES2022", module: "ESNext", moduleResolution: "Bundler", jsx: "react-jsx", strict: true, skipLibCheck: true, noEmit: true, types: [], typeRoots: [path.join(here, "node_modules", "@types")] }, include: ["*.tsx"] }));
const tsc = spawnSync(process.execPath, [path.join(here, "node_modules", "typescript", "bin", "tsc"), "-p", work], { encoding: "utf8" });
if (tsc.status !== 0) { console.error("[UI 장면] 타입 오류 — 컴포넌트 문서: npm --prefix tools/ui-scenes run -s astryx -- component <이름>\n" + (tsc.stdout || tsc.stderr).replaceAll(work + "/", "")); process.exit(1); }
const out = path.resolve(outDir);
// file:// 에서 열려야 한다 — 크로미움은 file:// 의 모듈 스크립트(type=module)를 막는다 → 한 덩어리 일반 스크립트(iife)로 묶는다
await build({ root: work, base: "./", logLevel: "warn", plugins: [react()],
  build: { outDir: out, emptyOutDir: true, minify: !rest.includes("--debug"), assetsInlineLimit: 0, modulePreload: false, chunkSizeWarningLimit: 4000,
    rollupOptions: { output: { format: "iife", inlineDynamicImports: true } } } });
const ip = path.join(out, "index.html");
writeFileSync(ip, readFileSync(ip, "utf8").replace(/<script type="module" crossorigin src=/g, "<script defer src=").replace(/ crossorigin/g, ""));
console.log(`[UI 장면] → ${path.join(out, "index.html")}`);
const png = opt("--png", null);
if (png) {   // 확인용 정지 화면 — 프로젝트 파이썬의 Playwright 로
  const [w, h] = png.split("x").map(Number);
  const root = path.resolve(here, "..", "..");
  const py = existsSync(path.join(root, ".venv", "bin", "python")) ? path.join(root, ".venv", "bin", "python") : "python3";
  const code = `from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n b=p.chromium.launch(); pg=b.new_page(viewport={'width':${w},'height':${h}})\n pg.goto('file://${path.join(out, "index.html")}'); pg.wait_for_timeout(600); pg.screenshot(path='${path.join(out, "scene.png")}'); b.close()`;
  const r = spawnSync(py, ["-c", code], { stdio: "inherit" });
  if (r.status === 0) console.log(`[UI 장면] 정지 화면 → ${path.join(out, "scene.png")}`);
}
