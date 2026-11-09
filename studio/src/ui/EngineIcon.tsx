import React, { useState } from "react";
import { ENG_COLOR } from "./engines";

/** 엔진 · 모델 아이콘. 공식 마크(studio/public/engine-icons/)가 있으면 그것, 없으면 엔진 색 타일에 머리글자.
 *  open-design 의 AgentIcon 처럼 같은 크기 · 같은 테두리로 맞춘다. */
const ICONS: Record<string, string> = {
  chatterbox: "png", claude: "png", cosyvoice: "png", edge: "svg", elevenlabs: "png",
  melotts: "png", typecast: "png", xtts: "png", supertonic: "png",
};
const FILE: Record<string, string> = { openrouter: "prov-openrouter.png" };   // 공급자 마크를 그대로 쓰는 엔진
const TINT: Record<string, string> = { ...ENG_COLOR, supertonic: "#7c5cff", espeak: "#8a8a8a", silent: "#555" };
const initials = (t: string) => (t.match(/[A-Z가-힣]/g) || [t[0]]).slice(0, 2).join("").toUpperCase();

/** 그림 아이콘은 밝은 타일 위에 — 검은 로고(OpenCode · Gemini 등)가 어두운 바탕에 묻히지 않게. 그림을 못 불러오면 머리글자 */
export const EngineIcon: React.FC<{ id: string; src?: string | null; title: string; size?: number }> = ({ id, src, title, size = 34 }) => {
  const url = src ?? (FILE[id] ? `/api/engine-icons/${FILE[id]}` : ICONS[id] ? `/api/engine-icons/${id}.${ICONS[id]}` : null);
  const [broken, setBroken] = useState(false);
  const img = !!url && !broken;
  return (
    <span className={`eicon ${img ? "img" : ""}`} style={{ width: size, height: size, ["--tint" as string]: TINT[id] ?? "#666" }} title={title}>
      {img ? <img src={url!} alt="" onError={() => setBroken(true)} /> : <b>{initials(title)}</b>}
    </span>
  );
};

/** 모델 이름 → 만든 회사 아이콘 (open-design modelProviderIcon 과 같은 규칙). `anthropic/claude-…` 처럼 제공자/모델 형식이면 앞부분을 본다 */
export function modelIconSrc(modelId: string | null | undefined): string | null {
  if (!modelId) return null;
  const slash = modelId.indexOf("/");
  const v = (slash > 0 ? modelId.slice(0, slash) : modelId.split("-")[0] ?? modelId).toLowerCase();
  const I = (f: string) => `/api/engine-icons/${f}`;
  if (v.includes("anthropic") || v.includes("claude") || ["opus", "sonnet", "haiku", "fable"].includes(v)) return I("agent-claude.svg");
  if (v.includes("openai") || v.includes("gpt") || v === "o1" || v === "o3" || v === "o4") return I("prov-openai.svg");
  if (v.includes("google") || v.includes("gemini")) return I("prov-google-gemini.svg");
  if (v.includes("xai") || v.includes("x-ai") || v.includes("grok")) return I("prov-x.svg");
  if (v.includes("deepseek")) return I("agent-deepseek.svg");
  if (v.includes("glm") || v.includes("zhipu") || v.includes("z-ai")) return I("agent-glm.svg");
  if (v.includes("qwen")) return I("agent-qwen.svg");
  if (v.includes("kimi") || v.includes("moonshot")) return I("agent-kimi.svg");
  if (v.includes("minimax")) return I("prov-minimax.svg");
  if (v.includes("meta") || v.includes("llama")) return I("prov-meta.png");
  if (v.includes("doubao") || v.includes("bytedance")) return I("prov-bytedance.svg");
  if (v.includes("openrouter")) return I("prov-openrouter.png");
  return null;
}
