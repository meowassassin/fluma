import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { Button, Dialog, EmptyState, IconButton, Segmented, Skeleton, cx } from "../../ui/kit";
import { t } from "../../lib/i18n";
import { useProjects } from "../../lib/queries";
import "./library.css";

type Tab = "characters" | "presets" | "voices";

export interface CharacterViewItem {
  id: string;
  name: string;
  prompt?: string;
  negativePrompt?: string;
  colorPalette?: string[];
  tags?: string[];
  hasModel3D?: boolean;
  views?: {
    front?: string;
    back?: string;
    left?: string;
    right?: string;
  };
}

export interface PresetItem {
  id: string;
  name: string;
  description?: string;
  characterId?: string;
  style?: string;
  structure?: Array<{ beat: string; duration: string; guide: string }>;
  voice?: { engine?: string; voiceId?: string; speed?: number };
}

export const LibraryPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>("characters");
  const qc = useQueryClient();
  const nav = useNavigate();

  // Queries
  const { data: charData, isLoading: loadingChars } = useQuery<any>({
    queryKey: ["library-characters"],
    queryFn: async () => {
      try {
        const res = await fetch("/api/library/characters");
        if (!res.ok) return { characters: [] };
        return res.json();
      } catch {
        return { characters: [] };
      }
    },
  });

  const { data: presetData, isLoading: loadingPresets } = useQuery<any>({
    queryKey: ["library-presets"],
    queryFn: async () => {
      try {
        const res = await fetch("/api/library/presets");
        if (!res.ok) return { presets: [] };
        return res.json();
      } catch {
        return { presets: [] };
      }
    },
  });

  // State for modals
  const [importOpen, setImportOpen] = useState(false);
  const [createPresetOpen, setCreatePresetOpen] = useState(false);
  const [selectedChar, setSelectedChar] = useState<CharacterViewItem | null>(null);

  const characters: CharacterViewItem[] = Array.isArray(charData)
    ? charData
    : (charData?.characters ?? []);
  const presets: PresetItem[] = Array.isArray(presetData)
    ? presetData
    : (presetData?.presets ?? []);

  return (
    <div className="lib-container">
      {/* 1. Header Banner */}
      <header className="lib-header">
        <div className="lib-title-area">
          <div className="lib-badge">
            <Icon n="library" s={14} />
            <span>{t("에셋 라이브러리")}</span>
          </div>
          <h1>{t("자산 및 시리즈 프리셋")}</h1>
          <p className="lib-desc">
            {t("완성된 4면 캐릭터 시트와 영상 화풍, 4박자 비트 구조를 보관하고 자동화 파이프라인에서 100% 일관성을 유지하며 재사용합니다.")}
          </p>
        </div>

        <div className="lib-header-actions">
          {tab === "characters" && (
            <Button variant="primary" icon="plus" size="md" onClick={() => setImportOpen(true)}>
              {t("프로젝트에서 캐릭터 가져오기")}
            </Button>
          )}
          {tab === "presets" && (
            <Button variant="primary" icon="plus" size="md" onClick={() => setCreatePresetOpen(true)}>
              {t("새 시리즈 프리셋 만들기")}
            </Button>
          )}
        </div>
      </header>

      {/* 2. Top Metric Statistics Cards */}
      <section className="lib-stats-grid">
        <div className="lib-stat-card" onClick={() => setTab("characters")}>
          <div className="stat-icon" style={{ background: "rgba(139, 92, 246, 0.15)", color: "#8b5cf6" }}>
            <Icon n="user" s={18} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t("등록된 캐릭터 시트")}</span>
            <div className="stat-val-row">
              <b className="stat-num mono">{characters.length}</b>
              <span className="stat-sub">{t("4면 턴어라운드 준비 완료")}</span>
            </div>
          </div>
        </div>

        <div className="lib-stat-card" onClick={() => setTab("presets")}>
          <div className="stat-icon" style={{ background: "rgba(245, 158, 11, 0.15)", color: "#f59e0b" }}>
            <Icon n="sparkle" s={18} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t("시리즈 프리셋")}</span>
            <div className="stat-val-row">
              <b className="stat-num mono">{presets.length}</b>
              <span className="stat-sub">{t("자동화 즉시 바인딩 가능")}</span>
            </div>
          </div>
        </div>

        <div className="lib-stat-card" onClick={() => setTab("voices")}>
          <div className="stat-icon" style={{ background: "rgba(56, 189, 248, 0.15)", color: "#38bdf8" }}>
            <Icon n="mic" s={18} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t("음성 및 오디오 엔진")}</span>
            <div className="stat-val-row">
              <b className="stat-num mono">3</b>
              <span className="stat-sub">ElevenLabs · Fish · Edge</span>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Navigation Tabs */}
      <div className="lib-nav-tabs">
        <Segmented
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          options={[
            { value: "characters", label: t("캐릭터 시트 ({n})", { n: characters.length }) },
            { value: "presets", label: t("시리즈 프리셋 ({n})", { n: presets.length }) },
            { value: "voices", label: t("음성 & 오디오 엔진") },
          ]}
        />
      </div>

      {/* 4. Tab Body */}
      <main className="lib-body">
        {tab === "characters" && (
          <CharactersSection
            characters={characters}
            loading={loadingChars}
            onSelect={(char) => setSelectedChar(char)}
            onImportClick={() => setImportOpen(true)}
          />
        )}

        {tab === "presets" && (
          <PresetsSection
            presets={presets}
            characters={characters}
            loading={loadingPresets}
            onCreateClick={() => setCreatePresetOpen(true)}
            onApplyToAutomation={(id) => nav(`/automation?preset=${encodeURIComponent(id)}`)}
          />
        )}

        {tab === "voices" && <VoicesSection />}
      </main>

      {/* Import Character Dialog */}
      <ImportCharacterDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={() => {
          qc.invalidateQueries({ queryKey: ["library-characters"] });
          setImportOpen(false);
        }}
      />

      {/* Create / Edit Preset Dialog */}
      <CreatePresetDialog
        open={createPresetOpen}
        characters={characters}
        onClose={() => setCreatePresetOpen(false)}
        onSuccess={() => {
          qc.invalidateQueries({ queryKey: ["library-presets"] });
          setCreatePresetOpen(false);
        }}
      />

      {/* Character Detail Dialog */}
      {selectedChar && (
        <CharacterDetailDialog
          character={selectedChar}
          onClose={() => setSelectedChar(null)}
          onStartPreset={(char) => {
            setSelectedChar(null);
            setCreatePresetOpen(true);
          }}
        />
      )}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* Characters Section                                                         */
/* -------------------------------------------------------------------------- */
const CharactersSection: React.FC<{
  characters: CharacterViewItem[];
  loading: boolean;
  onSelect: (char: CharacterViewItem) => void;
  onImportClick: () => void;
}> = ({ characters, loading, onSelect, onImportClick }) => {
  if (loading) {
    return (
      <div className="lib-grid">
        {[1, 2, 3].map((i) => (
          <div key={i} className="lib-card-skel">
            <Skeleton h={220} r={12} />
            <Skeleton h={20} w="60%" r={6} />
            <Skeleton h={14} w="90%" r={6} />
          </div>
        ))}
      </div>
    );
  }

  if (characters.length === 0) {
    return (
      <div className="lib-empty-box">
        <EmptyState
          icon="user"
          title={t("등록된 캐릭터가 없습니다")}
          body={t("기존 프로젝트에서 작업하여 승인된 4면 캐릭터 시트를 가져오거나 새로 추가해 보세요.")}
          action={
            <Button variant="primary" icon="plus" onClick={onImportClick}>
              {t("프로젝트에서 가져오기")}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="lib-grid">
      {characters.map((char) => (
        <div key={char.id} className="lib-char-card" onClick={() => onSelect(char)}>
          {/* Turnaround Viewport */}
          <div className="lib-char-previews">
            <div className="lib-char-thumb main-view">
              {char.views?.front ? (
                <img src={char.views.front} alt={`${char.name} 정면`} loading="lazy" />
              ) : (
                <div className="lib-no-img"><Icon n="image" s={24} /></div>
              )}
              <span className="view-tag">{t("정면 (Front)")}</span>
            </div>
            <div className="lib-char-subviews">
              <div className="lib-char-thumb sub-view">
                {char.views?.left ? <img src={char.views.left} alt="좌측" /> : <div className="lib-sub-placeholder" />}
                <span className="view-sub-tag">{t("좌")}</span>
              </div>
              <div className="lib-char-thumb sub-view">
                {char.views?.right ? <img src={char.views.right} alt="우측" /> : <div className="lib-sub-placeholder" />}
                <span className="view-sub-tag">{t("우")}</span>
              </div>
              <div className="lib-char-thumb sub-view">
                {char.views?.back ? <img src={char.views.back} alt="후면" /> : <div className="lib-sub-placeholder" />}
                <span className="view-sub-tag">{t("후")}</span>
              </div>
            </div>
          </div>

          {/* Meta Info */}
          <div className="lib-char-meta">
            <div className="lib-char-header">
              <h3 className="lib-char-title">{char.name}</h3>
              <span className="lib-id-tag mono">{char.id}</span>
            </div>
            {char.prompt && <p className="lib-char-desc line-clamp-2">{char.prompt}</p>}

            <div className="lib-char-badges">
              <span className="lib-badge-pill green">
                <Icon n="check" s={12} />
                <span>{t("4면 턴어라운드 준비됨")}</span>
              </span>
              {char.hasModel3D && (
                <span className="lib-badge-pill purple">
                  <Icon n="sparkle" s={12} />
                  <span>3D Mesh</span>
                </span>
              )}
            </div>

            {char.tags && char.tags.length > 0 && (
              <div className="lib-tag-list">
                {char.tags.map((tg, idx) => (
                  <span key={idx} className="lib-tag">#{tg}</span>
                ))}
              </div>
            )}

            <div className="lib-char-footer">
              <span className="click-hint">
                <Icon n="eye" s={12} />
                {t("상세 시트 보기")}
              </span>
              <IconButton
                icon="copy"
                label={t("ID 복사")}
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  navigator.clipboard.writeText(char.id);
                  toast.success(t("캐릭터 ID를 클립보드에 복사했습니다."));
                }}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* Presets Section                                                            */
/* -------------------------------------------------------------------------- */
const PresetsSection: React.FC<{
  presets: PresetItem[];
  characters: CharacterViewItem[];
  loading: boolean;
  onCreateClick: () => void;
  onApplyToAutomation: (id: string) => void;
}> = ({ presets, characters, loading, onCreateClick, onApplyToAutomation }) => {
  const qc = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/library/presets/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("프리셋 삭제에 실패했습니다.");
      return res.json();
    },
    onSuccess: () => {
      toast.success(t("프리셋을 삭제했습니다."));
      qc.invalidateQueries({ queryKey: ["library-presets"] });
    },
    onError: (err: any) => {
      toast.error(err.message || "삭제 실패");
    },
  });

  if (loading) {
    return (
      <div className="lib-presets-list">
        {[1, 2].map((i) => (
          <div key={i} className="lib-card-skel">
            <Skeleton h={160} r={12} />
          </div>
        ))}
      </div>
    );
  }

  if (presets.length === 0) {
    return (
      <div className="lib-empty-box">
        <EmptyState
          icon="sparkle"
          title={t("등록된 시리즈 프리셋이 없습니다")}
          body={t("캐릭터 시트와 영상 스타일, 4박자 비트를 묶어 저장하면 n8n 자동화 파이프라인에서 원클릭으로 일괄 제작할 수 있습니다.")}
          action={
            <Button variant="primary" icon="plus" onClick={onCreateClick}>
              {t("새 시리즈 프리셋 만들기")}
            </Button>
          }
        />
      </div>
    );
  }

  const charMap = new Map(characters.map((c) => [c.id, c]));

  return (
    <div className="lib-presets-list">
      {presets.map((preset) => {
        const boundChar = preset.characterId ? charMap.get(preset.characterId) : null;
        return (
          <div key={preset.id} className="lib-preset-card">
            <div className="lib-preset-header">
              <div className="lib-preset-title-wrap">
                <div className="lib-preset-icon">
                  <Icon n="sparkle" s={22} />
                </div>
                <div>
                  <div className="lib-preset-title-row">
                    <h3>{preset.name}</h3>
                    <span className="mono lib-id-tag">{preset.id}</span>
                  </div>
                  {preset.description && <p className="lib-preset-desc">{preset.description}</p>}
                </div>
              </div>

              <div className="lib-preset-actions">
                <Button
                  variant="primary"
                  icon="zap"
                  size="sm"
                  onClick={() => onApplyToAutomation(preset.id)}
                >
                  {t("자동화에 적용")}
                </Button>
                <IconButton
                  icon="trash"
                  label={t("프리셋 삭제")}
                  size="sm"
                  tone="danger"
                  onClick={() => {
                    if (confirm(t("“{name}” 프리셋을 삭제하시겠습니까?", { name: preset.name }))) {
                      deleteMutation.mutate(preset.id);
                    }
                  }}
                />
              </div>
            </div>

            <div className="lib-preset-content">
              {/* Character Binding */}
              <div className="lib-preset-block">
                <label className="lib-block-label">
                  <Icon n="user" s={12} />
                  <span>{t("바인딩된 캐릭터")}</span>
                </label>
                {boundChar ? (
                  <div className="lib-bound-char">
                    <img
                      src={boundChar.views?.front || "/api/library/characters/Pin/front.png"}
                      alt={boundChar.name}
                      className="lib-bound-avatar"
                    />
                    <div>
                      <b className="lib-bound-name">{boundChar.name}</b>
                      <span className="lib-bound-badge">
                        <Icon n="check" s={10} />
                        {t("4면 턴어라운드 일관성")}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="lib-bound-none">{t("지정된 캐릭터 없음 (자유 생성)")}</div>
                )}
              </div>

              {/* Style Guide */}
              <div className="lib-preset-block">
                <label className="lib-block-label">
                  <Icon n="palette" s={12} />
                  <span>{t("스타일 & 렌더 가이드")}</span>
                </label>
                <p className="lib-block-val">{preset.style || t("스타일 프롬프트 미지정")}</p>
              </div>

              {/* 4-Beat Structure Timeline */}
              {preset.structure && preset.structure.length > 0 && (
                <div className="lib-preset-block full-width">
                  <label className="lib-block-label">
                    <Icon n="film" s={12} />
                    <span>{t("영상 구조 비트 (4-Beat Structure Timeline)")}</span>
                  </label>
                  <div className="lib-structure-pills">
                    {preset.structure.map((st, sidx) => (
                      <div key={sidx} className="lib-struct-pill">
                        <span className="struct-num">{sidx + 1}</span>
                        <div className="struct-text">
                          <span className="struct-beat">
                            {st.beat} <em className="mono faint">({st.duration})</em>
                          </span>
                          <span className="struct-guide">{st.guide}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* Voices Section                                                             */
/* -------------------------------------------------------------------------- */
const VoicesSection: React.FC = () => {
  return (
    <div className="lib-voices-wrap">
      <div className="lib-notice-card">
        <Icon n="info" s={18} />
        <div>
          <h4>{t("음성 및 오디오 엔진 프리셋")}</h4>
          <p>{t("캐릭터의 성격과 시리즈 장르에 어울리는 최적의 TTS 보이스 및 사운드 효과를 선택할 수 있습니다.")}</p>
        </div>
      </div>

      <div className="lib-voice-grid">
        <div className="lib-voice-card">
          <div className="lib-voice-head">
            <span className="lib-voice-tag">ElevenLabs</span>
            <b>Rachel (Calm & Clear)</b>
          </div>
          <p className="lib-voice-sub">{t("호기심 탐구, 다큐멘터리, 정보 전달 숏폼에 최적화")}</p>
          <div className="lib-voice-preview">
            <audio controls src="/api/media/preview-rachel.mp3" preload="none" />
          </div>
        </div>

        <div className="lib-voice-card">
          <div className="lib-voice-head">
            <span className="lib-voice-tag">Fish Audio</span>
            <b>Bright Mascot / Child</b>
          </div>
          <p className="lib-voice-sub">{t("귀여운 마스코트(핀 등), 밝은 톤의 애니메이션 숏폼용")}</p>
          <div className="lib-voice-preview">
            <audio controls src="/api/media/preview-child.mp3" preload="none" />
          </div>
        </div>

        <div className="lib-voice-card">
          <div className="lib-voice-head">
            <span className="lib-voice-tag">Edge TTS</span>
            <b>ko-KR-SunHiNeural</b>
          </div>
          <p className="lib-voice-sub">{t("무료 고품질 한국어 자연어 음성, 지식/뉴스 쇼츠에 추천")}</p>
          <div className="lib-voice-preview">
            <audio controls src="/api/media/preview-sunhi.mp3" preload="none" />
          </div>
        </div>
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* Dialogs                                                                    */
/* -------------------------------------------------------------------------- */
const ImportCharacterDialog: React.FC<{
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}> = ({ open, onClose, onSuccess }) => {
  const { data: projects = [] } = useProjects();
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [charId, setCharId] = useState("");
  const [charName, setCharName] = useState("");
  const [loading, setLoading] = useState(false);

  const handleImport = async () => {
    if (!selectedProjectId || !charId.trim() || !charName.trim()) {
      toast.error(t("프로젝트, 캐릭터 ID, 이름을 모두 입력해주세요."));
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/library/characters/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: selectedProjectId,
          characterId: charId.trim(),
          name: charName.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "가져오기 실패");
      toast.success(t("캐릭터를 라이브러리로 가져왔습니다!"));
      onSuccess();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()} title={t("프로젝트에서 캐릭터 가져오기")} width={480}>
      <div className="lib-form">
        <p className="lib-form-desc">
          {t("기존 프로젝트에서 생성되어 승인된 4면 캐릭터 시트를 전역 라이브러리로 등록하여 다른 모든 영상에서 재사용할 수 있게 만듭니다.")}
        </p>

        <div className="lib-field">
          <label>{t("대상 프로젝트")}</label>
          <select
            className="lib-select"
            value={selectedProjectId}
            onChange={(e) => {
              setSelectedProjectId(e.target.value);
              const p = projects.find((x) => x.id === e.target.value);
              if (p && !charName) setCharName(p.title || "");
            }}
          >
            <option value="">{t("프로젝트 선택...")}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title || p.id} ({p.id})
              </option>
            ))}
          </select>
        </div>

        <div className="lib-field">
          <label>{t("캐릭터 고유 ID (영문/숫자/하이픈)")}</label>
          <input
            className="lib-input mono"
            placeholder="예: cute-pin, robot-charlie"
            value={charId}
            onChange={(e) => setCharId(e.target.value)}
          />
        </div>

        <div className="lib-field">
          <label>{t("캐릭터 표시 이름")}</label>
          <input
            className="lib-input"
            placeholder="예: 핀 (호기심 많은 펭귄)"
            value={charName}
            onChange={(e) => setCharName(e.target.value)}
          />
        </div>

        <div className="lib-dialog-actions">
          <Button variant="ghost" onClick={onClose} disabled={loading}>{t("취소")}</Button>
          <Button variant="primary" loading={loading} onClick={handleImport}>{t("가져오기 및 등록")}</Button>
        </div>
      </div>
    </Dialog>
  );
};

const CreatePresetDialog: React.FC<{
  open: boolean;
  characters: CharacterViewItem[];
  onClose: () => void;
  onSuccess: () => void;
}> = ({ open, characters, onClose, onSuccess }) => {
  const [name, setName] = useState("");
  const [presetId, setPresetId] = useState("");
  const [description, setDescription] = useState("");
  const [charId, setCharId] = useState("");
  const [style, setStyle] = useState("Vibrant 3D Pixar animated style, soft volumetric lighting, 8k render");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim() || !presetId.trim()) {
      toast.error(t("프리셋 이름과 ID를 입력해주세요."));
      return;
    }

    setLoading(true);
    try {
      const presetObj: PresetItem = {
        id: presetId.trim().toLowerCase().replace(/\s+/g, "-"),
        name: name.trim(),
        description: description.trim(),
        characterId: charId || undefined,
        style: style.trim(),
        structure: [
          { beat: "훅 (Hook)", duration: "0-3s", guide: "주의를 사로잡는 강력한 시각/음성 질문" },
          { beat: "질문 심화 (Conflict)", duration: "3-15s", guide: "주제의 핵심 궁금증과 왜 그런지 의문 제기" },
          { beat: "핵심 원리 (Insight)", duration: "15-45s", guide: "시각적 비유를 통한 쉽고 빠른 해결책 설명" },
          { beat: "아하! 반전 & 아웃트로", duration: "45-59s", guide: "반전 포인트 요약 및 채널 구독/댓글 유도" },
        ],
        voice: { engine: "elevenlabs", speed: 1.05 },
      };

      const res = await fetch("/api/library/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset: presetObj }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "프리셋 저장 실패");
      toast.success(t("시리즈 프리셋을 생성했습니다!"));
      onSuccess();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()} title={t("새 시리즈 프리셋 만들기")} width={540}>
      <div className="lib-form">
        <div className="lib-field">
          <label>{t("프리셋 고유 ID (영문)")}</label>
          <input
            className="lib-input mono"
            placeholder="예: pin-science-shorts"
            value={presetId}
            onChange={(e) => setPresetId(e.target.value)}
          />
        </div>

        <div className="lib-field">
          <label>{t("시리즈 프리셋 이름")}</label>
          <input
            className="lib-input"
            placeholder="예: 핀의 1분 과학 호기심"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="lib-field">
          <label>{t("시리즈 설명")}</label>
          <input
            className="lib-input"
            placeholder="예: 일상 속 흥미진진한 과학 상식을 핀과 함께 탐구하는 숏폼"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="lib-field">
          <label>{t("연동할 캐릭터 (선택)")}</label>
          <select className="lib-select" value={charId} onChange={(e) => setCharId(e.target.value)}>
            <option value="">{t("캐릭터 없음 (자유 생성)")}</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.id})
              </option>
            ))}
          </select>
        </div>

        <div className="lib-field">
          <label>{t("시각 화풍 프롬프트 (Visual Style)")}</label>
          <textarea
            className="lib-textarea"
            rows={3}
            value={style}
            onChange={(e) => setStyle(e.target.value)}
          />
        </div>

        <div className="lib-dialog-actions">
          <Button variant="ghost" onClick={onClose} disabled={loading}>{t("취소")}</Button>
          <Button variant="primary" loading={loading} onClick={handleSubmit}>{t("프리셋 저장")}</Button>
        </div>
      </div>
    </Dialog>
  );
};

const CharacterDetailDialog: React.FC<{
  character: CharacterViewItem;
  onClose: () => void;
  onStartPreset: (char: CharacterViewItem) => void;
}> = ({ character, onClose, onStartPreset }) => {
  return (
    <Dialog open={true} onOpenChange={(v) => !v && onClose()} title={character.name} width={640}>
      <div className="lib-detail-wrap">
        <div className="lib-detail-sheets">
          <h4>{t("4면 턴어라운드 시트 (Turnaround Sheets)")}</h4>
          <div className="lib-detail-views-grid">
            <div className="sheet-view-item">
              <span className="view-lbl">{t("정면 (Front)")}</span>
              <img src={character.views?.front || ""} alt="정면" />
            </div>
            <div className="sheet-view-item">
              <span className="view-lbl">{t("좌측 (Left)")}</span>
              <img src={character.views?.left || ""} alt="좌측" />
            </div>
            <div className="sheet-view-item">
              <span className="view-lbl">{t("우측 (Right)")}</span>
              <img src={character.views?.right || ""} alt="우측" />
            </div>
            <div className="sheet-view-item">
              <span className="view-lbl">{t("후면 (Back)")}</span>
              <img src={character.views?.back || ""} alt="후면" />
            </div>
          </div>
        </div>

        <div className="lib-detail-info">
          {character.prompt && (
            <div className="lib-detail-sec">
              <h5>{t("캐릭터 디자인 프롬프트")}</h5>
              <p className="lib-mono-box">{character.prompt}</p>
            </div>
          )}

          {character.negativePrompt && (
            <div className="lib-detail-sec">
              <h5>{t("네거티브 프롬프트")}</h5>
              <p className="lib-mono-box">{character.negativePrompt}</p>
            </div>
          )}
        </div>

        <div className="lib-dialog-actions">
          <Button variant="secondary" onClick={onClose}>{t("닫기")}</Button>
          <Button variant="primary" icon="sparkle" onClick={() => onStartPreset(character)}>
            {t("이 캐릭터로 시리즈 프리셋 만들기")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
};
