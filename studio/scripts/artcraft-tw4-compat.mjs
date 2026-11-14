#!/usr/bin/env node
// ArtCraft 부품의 Tailwind 4 전용 클래스 문법을 Tailwind 3(이 저장소)이 읽는 문법으로 바꾼다.
// tailwind.config.js 로 표현할 수 없는 "문법" 차이만 다룬다(키 차이 — z-100, shadow-xs, outline-hidden,
// bg-linear-to-* 등 — 는 config/플러그인이 맡는다).
//
//   1) 뒤 느낌표 중요 표시   size-3.5!  hover:bg-primary/5!   →  !size-3.5  hover:!bg-primary/5
//   2) CSS 변수 줄임 값      h-(--radix-x)  min-w-(--a)        →  h-[var(--radix-x)]  min-w-[var(--a)]
//
// 쓰는 법:  node scripts/artcraft-tw4-compat.mjs [--check] <폴더|파일>...
//   --check 는 바꾸지 않고 바뀔 곳만 보여 준다(바뀔 곳이 있으면 종료 코드 1).
// 클래스 문자열이 아닌 글("twice!")을 건드리지 않도록, 알려진 유틸리티 접두어로 시작하는 토큰만 바꾼다.
import fs from "node:fs";
import path from "node:path";

const ROOTS = [
  "absolute", "relative", "fixed", "sticky", "static", "block", "inline", "flex", "grid", "hidden", "contents", "table",
  "bg", "text", "font", "leading", "tracking", "border", "rounded", "ring", "outline", "shadow", "opacity", "size",
  "w", "h", "min-w", "min-h", "max-w", "max-h", "p", "px", "py", "pt", "pr", "pb", "pl", "ps", "pe", "m", "mx", "my",
  "mt", "mr", "mb", "ml", "ms", "me", "gap", "gap-x", "gap-y", "space-x", "space-y", "inset", "inset-x", "inset-y",
  "top", "right", "bottom", "left", "start", "end", "z", "translate-x", "translate-y", "scale", "rotate", "skew",
  "items", "justify", "self", "place", "content", "order", "basis", "grow", "shrink", "overflow", "overscroll",
  "cursor", "pointer-events", "select", "whitespace", "break", "truncate", "line-clamp", "aspect", "object",
  "fill", "stroke", "decoration", "underline", "transition", "duration", "ease", "delay", "animate", "blur",
  "backdrop", "brightness", "invert", "grayscale", "divide", "col", "row", "auto-cols", "auto-rows", "visible",
  "invisible", "sr-only", "outline-hidden", "appearance", "resize", "scroll", "snap", "accent", "caret", "will-change",
];
const ROOT_RE = new RegExp(`^-?(?:${ROOTS.map((r) => r.replace(/[-]/g, "\\-")).join("|")})(?:$|-)`);
// 토큰: 변형(hover:, data-[x]:, [&>svg]: …) + 본체
const TOKEN_RE = /(?<=^|[\s"'`{])((?:[a-z0-9@*&>[\]=_().:-]+?:)*)(-?[a-z][a-z0-9-]*(?:[./][a-z0-9.%]+)*(?:-\[[^\]\s]+\])?)!(?=$|[\s"'`}])/gm;
const VAR_RE = /(?<=^|[\s"'`{:])(-?[a-z][a-z0-9-]*)-\((--[A-Za-z0-9_-]+)\)(?=$|[\s"'`}!/])/gm;

export function rewrite(src) {
  const changes = [];
  let out = src.replace(VAR_RE, (m, util, v) => {
    if (!ROOT_RE.test(util)) return m;
    const r = `${util}-[var(${v})]`;
    changes.push([m, r]);
    return r;
  });
  out = out.replace(TOKEN_RE, (m, variants, body) => {
    if (!ROOT_RE.test(body)) return m;
    const r = `${variants}!${body}`;
    changes.push([m, r]);
    return r;
  });
  return { out, changes };
}

function* walk(p) {
  const st = fs.statSync(p);
  if (st.isDirectory()) {
    for (const e of fs.readdirSync(p)) if (e !== "node_modules") yield* walk(path.join(p, e));
  } else if (/\.(tsx?|jsx?)$/.test(p)) yield p;
}

const args = process.argv.slice(2);
const check = args.includes("--check");
const targets = args.filter((a) => a !== "--check");
if (!targets.length) {
  console.error("usage: node scripts/artcraft-tw4-compat.mjs [--check] <dir|file>...");
  process.exit(2);
}
let total = 0;
for (const t of targets) {
  for (const f of walk(t)) {
    const src = fs.readFileSync(f, "utf8");
    const { out, changes } = rewrite(src);
    if (!changes.length) continue;
    total += changes.length;
    for (const [a, b] of changes) console.log(`${f}: ${a} → ${b}`);
    if (!check) fs.writeFileSync(f, out);
  }
}
console.log(`${check ? "would change" : "changed"} ${total} class token(s)`);
process.exit(check && total ? 1 : 0);
