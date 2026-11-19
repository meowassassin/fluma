import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { Button, Dialog, EmptyState, IconButton, Segmented, Skeleton } from "../../ui/kit";
import { t } from "../../lib/i18n";
import "./library.css";

type Tab = "presets" | "voices";

export interface PresetItem {
  id: string;
  name: string;
  description?: string;
  style?: string;
  structure?: Array<{ beat: string; duration: string; guide: string }>;
  voice?: { engine?: string; voiceId?: string; speed?: number };
}

export const LibraryPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>("presets");
  const qc = useQueryClient();
  const nav = useNavigate();

  // Queries
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
  const [createPresetOpen, setCreatePresetOpen] = useState(false);

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
            {t("시리즈의 톤 · 스타일과 4박자 비트 구조를 보관하고 시리즈 양산에서 같은 톤으로 재사용합니다.")}
          </p>
        </div>

        <div className="lib-header-actions">
          {tab === "presets" && (
            <Button variant="primary" icon="plus" size="md" onClick={() => setCreatePresetOpen(true)}>
              {t("새 시리즈 프리셋 만들기")}
            </Button>
          )}
        </div>
      </header>

      {/* 2. Top Metric Statistics Cards */}
      <section className="lib-stats-grid">
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
          aria-label={t("라이브러리 탭")}
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          options={[
            { value: "presets", label: t("시리즈 프리셋 ({n})", { n: presets.length }) },
            { value: "voices", label: t("음성 & 오디오 엔진") },
          ]}
        />
      </div>

      {/* 4. Tab Body */}
      <main className="lib-body">
        {tab === "presets" && (
          <PresetsSection
            presets={presets}
            loading={loadingPresets}
            onCreateClick={() => setCreatePresetOpen(true)}
            onApplyToAutomation={(id) => nav(`/automation?preset=${encodeURIComponent(id)}`)}
          />
        )}

        {tab === "voices" && <VoicesSection />}
      </main>

      {/* Create / Edit Preset Dialog */}
      <CreatePresetDialog
        open={createPresetOpen}
        onClose={() => setCreatePresetOpen(false)}
        onSuccess={() => {
          qc.invalidateQueries({ queryKey: ["library-presets"] });
          setCreatePresetOpen(false);
        }}
      />

    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* Presets Section                                                            */
/* -------------------------------------------------------------------------- */
const PresetsSection: React.FC<{
  presets: PresetItem[];
  loading: boolean;
  onCreateClick: () => void;
  onApplyToAutomation: (id: string) => void;
}> = ({ presets, loading, onCreateClick, onApplyToAutomation }) => {
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
          body={t("영상 스타일과 4박자 비트를 묶어 저장하면 시리즈 양산에서 같은 톤으로 여러 편을 돌릴 수 있습니다.")}
          action={
            <Button variant="primary" icon="plus" onClick={onCreateClick}>
              {t("새 시리즈 프리셋 만들기")}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="lib-presets-list">
      {presets.map((preset) => {
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
              {/* Style Guide */}
              <div className="lib-preset-block">
                <label className="lib-block-label">
                  <Icon n="palette" s={12} />
                  <span>{t("톤 · 스타일 메모")}</span>
                </label>
                <p className="lib-block-val">{preset.style || t("스타일 메모 없음")}</p>
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
          <p>{t("시리즈 장르에 어울리는 최적의 TTS 보이스 및 사운드 효과를 선택할 수 있습니다.")}</p>
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
const CreatePresetDialog: React.FC<{
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}> = ({ open, onClose, onSuccess }) => {
  const [name, setName] = useState("");
  const [presetId, setPresetId] = useState("");
  const [description, setDescription] = useState("");
  const [style, setStyle] = useState("");
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
            placeholder="예: 1분 IT 상식"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="lib-field">
          <label>{t("시리즈 설명")}</label>
          <input
            className="lib-input"
            placeholder="예: 매일 쓰는 앱의 숨은 기능을 실제 화면으로 보여 주는 숏폼"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="lib-field">
          <label>{t("톤 · 스타일 메모")}</label>
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
