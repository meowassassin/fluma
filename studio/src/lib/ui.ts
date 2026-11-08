/* 화면 배치 상태(에이전트 패널 열림 · 마지막 영상 등) — 새로고침해도 유지 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RenderOpts } from "./api";

interface UiState {
  agentOpen: boolean; boardOpen: boolean; leftOpen: boolean; chatsOpen: boolean; renderOpts: RenderOpts; inspOpen: boolean; lastProject: string | null; paletteOpen: boolean; shortcutsOpen: boolean;
  timelineH: number;
  set: (p: Partial<Omit<UiState, "set">>) => void;
}
export const useUi = create<UiState>()(persist((set) => ({
  agentOpen: true, boardOpen: true, leftOpen: true, chatsOpen: true, renderOpts: { size: "1080", quality: "high", fps: 30 }, inspOpen: true, lastProject: null, paletteOpen: false, shortcutsOpen: false, timelineH: 200,
  set: (p) => set(p),
}), { name: "fluma.ui", partialize: (s) => ({ agentOpen: s.agentOpen, boardOpen: s.boardOpen, leftOpen: s.leftOpen, chatsOpen: s.chatsOpen, renderOpts: s.renderOpts, inspOpen: s.inspOpen, lastProject: s.lastProject, timelineH: s.timelineH }) }));

/** 입력칸에서 친 키는 단축키로 쓰지 않는다 */
export const typing = (e: KeyboardEvent) => {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable;
};
