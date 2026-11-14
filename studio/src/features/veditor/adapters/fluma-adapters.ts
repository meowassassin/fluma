/* Fluma 서버 연동 어댑터 번들 (엔진 2 — 비디오 에디터).
   - 저장소: data/compositions/<id>/editor/project.json (GET/PUT /api/projects/:id/editor)
   - 미디어 소스: 서버 미디어(클립, 나레이션 음성) 및 로컬 업로드
   - 내보내기 싱크: data/compositions/<id>/editor/exported.mp4 및 data/out/<id>-editor.mp4 (POST /api/projects/:id/editor/export) */

import { toast } from "sonner";
import { api, uploadExportedVideo, uploadFile } from "../../../lib/api";
import {
  anonymousAuthUser,
  kindFromMime,
  type EditorProject,
  type ExportArtifact,
  type ExportSinkAdapter,
  type ExportSinkOptions,
  type MediaHandle,
  type MediaSourceAdapter,
  type ProjectMeta,
  type ProjectStorageAdapter,
  type ResolvedMedia,
  type ToastAdapter,
  type ToastOptions,
  type VideoEditorAdapters,
  type SoundsAdapter,
  type SoundEffect,
  type AssetGalleryAdapter,
  type MediaKind,
  type MediaPickerSelection,
} from "../../../vendor/artcraft/video-editor/src";

export const flumaToast: ToastAdapter = {
  info: (m: string, o?: ToastOptions) => toast.info(m, { description: o?.description }),
  success: (m: string, o?: ToastOptions) => toast.success(m, { description: o?.description }),
  warning: (m: string, o?: ToastOptions) => toast.warning(m, { description: o?.description }),
  error: (m: string, o?: ToastOptions) => toast.error(m, { description: o?.description }),
};

/** 문서의 타임라인 요소가 가리키는 mediaId 전부 */
function referencedMediaIds(doc: Record<string, unknown>): Set<string> {
  const ids = new Set<string>();
  const project = doc.project as { scenes?: Array<{ tracks?: { overlay?: unknown[]; main?: unknown; audio?: unknown[] } }> } | undefined;
  for (const sc of project?.scenes ?? []) {
    const t = sc.tracks ?? {};
    for (const tr of [...(t.overlay ?? []), t.main, ...(t.audio ?? [])] as Array<{ elements?: Array<{ mediaId?: string }> } | undefined>) {
      for (const el of tr?.elements ?? []) if (el.mediaId) ids.add(el.mediaId);
    }
  }
  return ids;
}

export function createFlumaProjectStorage(
  projectId: string,
  mediaMap: Map<string, { url: string; mime: string }>,
): ProjectStorageAdapter {
  // 불러온 문서의 media 항목(원본 그대로). 편집기는 불러오기에 실패한 미디어(주소 404 · 디코딩 실패)를 미디어함에서 빼고
  // 자동 저장 때 그 항목까지 목록에서 지운다 — 그러면 요소만 남고 미디어는 영영 사라졌다(2026-11 'Insert 7' 달 사진).
  // 그래서 저장할 때, 요소가 아직 가리키는데 목록에서 빠진 항목은 불러온 원본으로 되살려 둔다.
  const loadedMedia = new Map<string, Record<string, unknown>>();
  return {
    async loadProject(id: string) {
      try {
        const doc = (await api.editorGet(id)) as {
          version?: number;
          project?: { metadata?: { name?: string; updatedAt?: string } };
          media?: Array<{ id: string; name?: string; type?: string; url?: string }>;
        } | null;
        if (!doc) return null;

        // 나레이션 음성 기본 매핑 보장
        const defaultVoiceUrl = `/api/projects/${id}/studio-file?p=data/public/audio/${id}.voice.wav`;
        mediaMap.set("media_narration_voice", { url: defaultVoiceUrl, mime: "audio/wav" });

        loadedMedia.clear();
        if (Array.isArray(doc.media)) {
          for (const m of doc.media) {
            if (m.id) loadedMedia.set(m.id, m as unknown as Record<string, unknown>);
            if (m.id) {
              const mime = mimeOf(m.url || m.name || "", m.type);
              const baseUrl = m.url || (m.id === "media_narration_voice" ? defaultVoiceUrl : "");
              const ver = (m as { lastModified?: number }).lastModified;
              const targetUrl = baseUrl && ver && !baseUrl.includes("v=")
                ? `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}v=${ver}`
                : baseUrl;
              if (targetUrl) {
                mediaMap.set(m.id, { url: targetUrl, mime });
              }
            }
          }
        }

        const name = doc.project?.metadata?.name || id;
        return {
          id,
          name,
          updatedAt: Date.now(),
          data: doc,
        };
      } catch (err) {
        console.error("Failed to load project from Fluma server:", err);
        throw err;   // null 로 바꾸면 '프로젝트 없음'과 구분이 안 된다
      }
    },
    async saveProject(project: EditorProject) {
      try {
        // 직렬화 과정에서 media URL이 탈락하지 않도록 mediaMap을 참조하여 보존
        const rawData = (project.data || {}) as Record<string, unknown>;
        const rawMedia = Array.isArray(rawData.media) ? rawData.media : [];
        const enrichedMedia = rawMedia.map((m: any) => {
          const mapped = mediaMap.get(m.id);
          return {
            ...m,
            url: m.url || mapped?.url,
          };
        });

        const kept = new Set(enrichedMedia.map((m: { id?: string }) => m.id));
        for (const id of referencedMediaIds(rawData)) {
          const orig = loadedMedia.get(id);
          if (!kept.has(id) && orig) enrichedMedia.push(orig);
        }

        const docToSave = {
          ...rawData,
          media: enrichedMedia,
        };

        await api.editorSave(project.id, docToSave);
      } catch (err) {
        console.error("Failed to save project to Fluma server:", err);
        throw err;
      }
    },
    async deleteProject(_id: string) {
      // Fluma 프로젝트 삭제는 상위 화면(TopBar)에서 관리
    },
    async listProjects(): Promise<ProjectMeta[]> {
      return [{ id: projectId, name: projectId, updatedAt: Date.now() }];
    },
    async createProject(name: string) {
      return { id: projectId, name, updatedAt: Date.now(), data: null };
    },
  };
}

/** 확장자 → MIME */
export const mimeOf = (name: string, kind?: string) => {
  const e = name.split("?")[0].split(".").pop()?.toLowerCase() ?? "";
  const M: Record<string, string> = { mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime", webm: "video/webm", mkv: "video/x-matroska",
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif",
    wav: "audio/wav", mp3: "audio/mpeg", m4a: "audio/mp4", ogg: "audio/ogg", aac: "audio/aac" };
  return M[e] ?? (kind === "video" ? "video/mp4" : kind === "audio" ? "audio/wav" : kind === "image" ? "image/png" : "application/octet-stream");
};
/** 서버 upload 와 같은 파일 이름 다듬기(server.mjs safeName) */
const safeName = (n: string) => n.normalize("NFC").replace(/[^A-Za-z0-9가-힣._-]+/g, "-").replace(/^[-.]+/, "").slice(0, 80);

/** 미디어 = 서버 파일. 핸들 id → 주소는 프로젝트 문서의 media 목록(변환기 · 업로드 · Craft 효과 층이 주소를 같이 적는다)에서 찾는다.
 *  추측(파일 이름 짐작)은 하지 않는다 — 없으면 오류로 알린다. 사용자가 가져온 파일은 서버(data/public/uploads/<id>/)에 올린 뒤 그 주소를 쓴다(새로 고침 뒤에도 남게). */
export function createFlumaMediaSource(
  projectId: string,
  mediaMap: Map<string, { url: string; mime: string }>,
): MediaSourceAdapter {
  return {
    async resolveMedia(handle: MediaHandle): Promise<ResolvedMedia> {
      const m = mediaMap.get(handle.id);
      if (m) return { url: m.url, mime: m.mime };
      if (handle.id === "media_narration_voice") {
        return { url: `/api/projects/${projectId}/studio-file?p=data/public/audio/${projectId}.voice.wav`, mime: "audio/wav" };
      }
      throw new Error(`미디어를 찾지 못했습니다: ${handle.id}`);
    },
    async uploadLocalFile(file: File): Promise<MediaHandle> {
      const r = await uploadFile(projectId, file, { frames: false }) as { files?: Array<{ name: string; url: string }> };
      const want = safeName(file.name);
      const f = (r.files ?? []).find((x) => x.name === want) ?? (r.files ?? []).find((x) => x.name.startsWith(want.replace(/\.[^.]+$/, "")));
      if (!f) throw new Error(`서버에 올린 파일을 찾지 못했습니다: ${file.name}`);
      const id = `upload:${f.name}`;
      mediaMap.set(id, { url: f.url, mime: file.type || mimeOf(f.name) });
      return { id, kind: kindFromMime(file.type || mimeOf(f.name)) };
    },
  };
}

export function createFlumaExportSink(projectId: string): ExportSinkAdapter {
  return {
    async accept(artifact: ExportArtifact, options?: ExportSinkOptions): Promise<string | null> {
      const saveToDisk = options?.saveToDisk ?? true;
      const onProgress = options?.onProgress;

      onProgress?.({ destination: "disk", status: "pending" });
      onProgress?.({ destination: "library", status: "pending" });

      // 1. 서버로 업로드 (최종본 저장: data/compositions/<id>/editor/exported.mp4 및 data/out/<id>-editor.mp4)
      try {
        onProgress?.({ destination: "library", status: "uploading" });
        await uploadExportedVideo(projectId, artifact.blob);
        onProgress?.({ destination: "library", status: "success" });
        toast.success(`최종 영상을 서버에 저장했습니다 (data/out/${projectId}-editor.mp4)`);
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "서버 저장 실패";
        onProgress?.({ destination: "library", status: "error", error: errorMsg });
        toast.error("서버에 영상을 저장하지 못했습니다", { description: errorMsg });
      }

      // 2. 브라우저 디스크 다운로드
      if (saveToDisk) {
        try {
          const url = URL.createObjectURL(artifact.blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = artifact.filename || `${projectId}-final.mp4`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 60_000);
          onProgress?.({ destination: "disk", status: "success" });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : "다운로드 실패";
          onProgress?.({ destination: "disk", status: "error", error: errorMsg });
        }
      }

      return artifact.filename;
    },
  };
}

/** 효과음 = 저장소 assets/sfx (/api/sfx-list) */
let sfxCache: SoundEffect[] | null = null;
async function sfxList(): Promise<SoundEffect[]> {
  if (sfxCache) return sfxCache;
  const r = await fetch("/api/sfx-list"); const xs = r.ok ? (await r.json() as Array<{ id: number; name: string; duration: number; previewUrl: string }>) : [];
  sfxCache = xs.map((x) => ({ id: x.id, name: x.name, description: "", url: x.previewUrl, previewUrl: x.previewUrl, downloadUrl: x.previewUrl,
    duration: x.duration, filesize: 0, type: "wav", channels: 2, bitrate: 0, bitdepth: 16, samplerate: 48000, username: "fluma",
    tags: [x.name.toLowerCase()], license: "Fluma", created: "", downloads: 0, rating: 0, ratingCount: 0 }));
  return sfxCache;
}

export const flumaSoundsAdapter: SoundsAdapter = {
  async searchSounds({ query }) {
    const q = (query || "").toLowerCase().trim();
    const all = await sfxList();
    const filtered = q ? all.filter((s) => s.name.toLowerCase().includes(q)) : all;
    return { results: filtered, hasNextPage: false, totalCount: filtered.length };
  },
  async getTopSounds() { return sfxList(); },
  async loadSavedSounds() { return []; },
  async saveSound() {},
  async unsaveSound() {},
  async clearSavedSounds() {},
  async resolveAudioUrl({ soundId }) {
    const s = (await sfxList()).find((x) => x.id === soundId);
    if (!s) throw new Error("효과음을 찾지 못했습니다");
    return s.url;
  },
};

/** 지금 열린 편집기의 미디어 주소표 — Craft 효과 층처럼 편집기 밖에서 만든 미디어를 등록 · 원본 주소를 찾을 때 */
let activeMedia = new Map<string, { url: string; mime: string }>();
export const registerFlumaMedia = (id: string, url: string, mime?: string) => activeMedia.set(id, { url, mime: mime || mimeOf(url) });
export const flumaMediaUrl = (id: string) => activeMedia.get(id)?.url ?? null;

interface GalleryItem {
  id: string;
  name: string;
  kind: MediaKind;
  group: string;
  url: string;
}

/** 프로젝트 에셋 갤러리 어댑터 — 파이프라인 키프레임, 샷 테이크, 캐릭터 시트, 앵커, 오디오를 편집기 미디어함으로 바로 가져온다 */
export function createFlumaAssetGallery(
  projectId: string,
  mediaMap: Map<string, { url: string; mime: string }>,
): AssetGalleryAdapter {
  return {
    async openPicker({ kinds }): Promise<MediaPickerSelection[]> {
      const r = await fetch(`/api/projects/${encodeURIComponent(projectId)}/editor/gallery`);
      if (!r.ok) throw new Error("갤러리 목록을 불러오지 못했습니다");
      const all = (await r.json()) as GalleryItem[];
      const allowed = new Set(kinds);
      const items = all.filter((x) => allowed.has(x.kind));

      return new Promise<MediaPickerSelection[]>((resolve) => {
        const selected = new Set<string>();
        let activeGroup = "전체";
        let query = "";

        const overlay = document.createElement("div");
        overlay.style.cssText =
          "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.68);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px;font-family:Pretendard,sans-serif;color:#eee;";

        const modal = document.createElement("div");
        modal.style.cssText =
          "width:min(860px,95vw);height:min(640px,86vh);background:#16161a;border:1px solid #2b2b33;border-radius:12px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,0.65);";
        overlay.appendChild(modal);

        const close = (result: MediaPickerSelection[]) => {
          window.removeEventListener("keydown", onKey);
          overlay.remove();
          resolve(result);
        };
        const onKey = (e: KeyboardEvent) => {
          if (e.key === "Escape") close([]);
        };
        window.addEventListener("keydown", onKey);
        overlay.addEventListener("click", (e) => {
          if (e.target === overlay) close([]);
        });

        // Header
        const header = document.createElement("div");
        header.style.cssText =
          "display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #26262e;";
        const title = document.createElement("div");
        title.style.cssText = "font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px;";
        title.textContent = "프로젝트 미디어 갤러리 (키프레임 · 테이크 · 캐릭터 · 오디오)";
        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.textContent = "✕";
        closeBtn.style.cssText =
          "background:transparent;border:0;color:#999;font-size:16px;cursor:pointer;padding:4px 8px;border-radius:6px;";
        closeBtn.onclick = () => close([]);
        header.append(title, closeBtn);
        modal.appendChild(header);

        // Toolbar (Group tabs + search)
        const toolbar = document.createElement("div");
        toolbar.style.cssText =
          "display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 18px;border-bottom:1px solid #22222a;flex-wrap:wrap;";
        const tabsWrap = document.createElement("div");
        tabsWrap.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";
        const groups = ["전체", ...Array.from(new Set(items.map((i) => i.group)))];

        const searchInput = document.createElement("input");
        searchInput.type = "search";
        searchInput.placeholder = "이름 검색…";
        searchInput.style.cssText =
          "height:30px;padding:0 10px;border-radius:6px;border:1px solid #2e2e38;background:#101014;color:#eee;font-size:12.5px;outline:none;min-width:180px;";
        toolbar.append(tabsWrap, searchInput);
        modal.appendChild(toolbar);

        // Grid body
        const body = document.createElement("div");
        body.style.cssText =
          "flex:1;overflow-y:auto;padding:16px 18px;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;align-content:start;";
        modal.appendChild(body);

        // Footer
        const footer = document.createElement("div");
        footer.style.cssText =
          "display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border-top:1px solid #26262e;background:#121216;";
        const countEl = document.createElement("div");
        countEl.style.cssText = "font-size:12.5px;color:#aaa;";
        const btnWrap = document.createElement("div");
        btnWrap.style.cssText = "display:flex;gap:8px;";
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.textContent = "취소";
        cancelBtn.style.cssText =
          "height:32px;padding:0 14px;border-radius:7px;border:1px solid #333;background:#222;color:#ddd;font-size:12.5px;cursor:pointer;";
        cancelBtn.onclick = () => close([]);
        const confirmBtn = document.createElement("button");
        confirmBtn.type = "button";
        confirmBtn.style.cssText =
          "height:32px;padding:0 16px;border-radius:7px;border:0;background:#5850f8;color:#fff;font-size:12.5px;font-weight:600;cursor:pointer;";
        confirmBtn.onclick = () => {
          const picked = items.filter((i) => selected.has(i.id));
          for (const it of picked) {
            mediaMap.set(it.id, { url: it.url, mime: mimeOf(it.url, it.kind) });
          }
          close(
            picked.map((it) => ({
              handle: { id: it.id, kind: it.kind },
              name: it.name,
            })),
          );
        };
        btnWrap.append(cancelBtn, confirmBtn);
        footer.append(countEl, btnWrap);
        modal.appendChild(footer);

        const updateFooter = () => {
          countEl.textContent = selected.size
            ? `${selected.size}개 항목 선택됨`
            : "가져올 항목을 클릭해 선택하세요 (복수 선택 가능)";
          confirmBtn.textContent = selected.size ? `${selected.size}개 미디어함에 추가` : "선택 항목 추가";
          confirmBtn.disabled = selected.size === 0;
          confirmBtn.style.opacity = selected.size === 0 ? "0.5" : "1";
        };

        const renderTabs = () => {
          tabsWrap.innerHTML = "";
          for (const g of groups) {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = g;
            const active = g === activeGroup;
            b.style.cssText = `height:26px;padding:0 10px;border-radius:6px;font-size:12px;cursor:pointer;border:1px solid ${
              active ? "#5850f8" : "#2c2c35"
            };background:${active ? "rgba(88,80,248,0.2)" : "#1c1c22"};color:${active ? "#fff" : "#aaa"};`;
            b.onclick = () => {
              activeGroup = g;
              renderTabs();
              renderGrid();
            };
            tabsWrap.appendChild(b);
          }
        };

        const renderGrid = () => {
          body.innerHTML = "";
          const q = query.trim().toLowerCase();
          const filtered = items.filter(
            (i) =>
              (activeGroup === "전체" || i.group === activeGroup) &&
              (!q || i.name.toLowerCase().includes(q) || i.group.toLowerCase().includes(q)),
          );
          if (filtered.length === 0) {
            const empty = document.createElement("div");
            empty.style.cssText = "grid-column:1/-1;text-align:center;padding:48px 0;color:#777;font-size:13px;";
            empty.textContent = "표시할 프로젝트 에셋이 없습니다.";
            body.appendChild(empty);
            return;
          }
          for (const item of filtered) {
            const isSel = selected.has(item.id);
            const card = document.createElement("button");
            card.type = "button";
            card.style.cssText = `display:flex;flex-direction:column;gap:6px;padding:8px;border-radius:8px;background:#1e1e26;border:2px solid ${
              isSel ? "#5850f8" : "transparent"
            };color:#eee;text-align:left;cursor:pointer;overflow:hidden;transition:border-color 0.12s;`;

            const thumb = document.createElement("div");
            thumb.style.cssText =
              "width:100%;aspect-ratio:16/10;background:#101015;border-radius:5px;overflow:hidden;display:flex;align-items:center;justify-content:center;position:relative;";
            if (item.kind === "image") {
              const img = document.createElement("img");
              img.src = item.url;
              img.loading = "lazy";
              img.style.cssText = "width:100%;height:100%;object-fit:cover;";
              thumb.appendChild(img);
            } else if (item.kind === "video") {
              const vid = document.createElement("video");
              vid.src = item.url;
              vid.muted = true;
              vid.playsInline = true;
              vid.preload = "metadata";
              vid.style.cssText = "width:100%;height:100%;object-fit:cover;";
              vid.onmouseenter = () => void vid.play().catch(() => {});
              vid.onmouseleave = () => {
                vid.pause();
                vid.currentTime = 0;
              };
              thumb.appendChild(vid);
            } else {
              thumb.textContent = "🔊 오디오";
              thumb.style.fontSize = "12px";
              thumb.style.color = "#999";
            }

            const badge = document.createElement("span");
            badge.textContent = item.group;
            badge.style.cssText =
              "position:absolute;top:4px;left:4px;background:rgba(0,0,0,0.65);color:#ccc;font-size:10px;padding:2px 5px;border-radius:4px;";
            thumb.appendChild(badge);

            const label = document.createElement("div");
            label.textContent = item.name;
            label.title = item.name;
            label.style.cssText = "font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;";

            card.append(thumb, label);
            card.onclick = () => {
              if (selected.has(item.id)) selected.delete(item.id);
              else selected.add(item.id);
              renderGrid();
              updateFooter();
            };
            card.ondblclick = () => {
              selected.add(item.id);
              confirmBtn.click();
            };
            body.appendChild(card);
          }
        };

        searchInput.oninput = () => {
          query = searchInput.value;
          renderGrid();
        };

        renderTabs();
        renderGrid();
        updateFooter();
        document.body.appendChild(overlay);
      });
    },
  };
}

export function createFlumaAdapters(projectId: string): VideoEditorAdapters {
  const mediaMap = new Map<string, { url: string; mime: string }>();
  activeMedia = mediaMap;
  return {
    projectStorage: createFlumaProjectStorage(projectId, mediaMap),
    mediaSource: createFlumaMediaSource(projectId, mediaMap),
    authUser: anonymousAuthUser,
    exportSink: createFlumaExportSink(projectId),
    toast: flumaToast,
    soundsAdapter: flumaSoundsAdapter,
    assetGallery: createFlumaAssetGallery(projectId, mediaMap),
  };
}
