/* ArtCraft 3D 무대 및 2D 캔버스 연출 뷰 (Embedded View)
   - 영상 편집기(/veditor/:id) 중앙 뷰포트에 직접 통합
   - 3D 마네킹 포즈(15개 관절), 3D 카메라(궤도 회전/거리/화각), 소품/배경 블로킹
   - 2D 레이어 합성 및 마스크 인페인팅
   - 하단 플로팅 프롬프트 바: 구도 확정(시작 프레임 지정) & 영상 생성 원클릭 실행 */

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, type Pipeline } from "../../lib/api";
import { t } from "../../lib/i18n";
import { POSE_PRESETS, type PosePresetKey, type MannequinPose } from "../videos/KeyframeStudioModal";

const F = (rel: string | null | undefined) => (rel ? `/api/pipefiles/${rel}` : "");

export interface Vec3 {
  0: number;
  1: number;
  2: number;
}

export interface SceneObject {
  id: string;
  kind: "character" | "box" | "prop";
  label: string;
  x: number;
  y: number;
  z: number;
  w: number;
  h: number;
  d: number;
  color: string;
  posePreset?: PosePresetKey;
  pose?: MannequinPose;
}

export interface Layer2D {
  id: string;
  label: string;
  url: string;
  img: HTMLImageElement;
  x: number;
  y: number;
  scale: number;
}

export interface Stage3DContextType {
  id: string;
  pipeline: Pipeline | null;
  shotsList: NonNullable<Pipeline["shotplan"]>["shots"];
  shot: number;
  setShot: (s: number) => void;
  curShot: NonNullable<Pipeline["shotplan"]>["shots"][0] | undefined;
  curKf: NonNullable<Pipeline["keyframes"]>[0] | undefined;
  aspect: "9:16" | "16:9" | "1:1";
  setAspect: (a: "9:16" | "16:9" | "1:1") => void;
  CW: number;
  CH: number;
  surfaceTab: "stage" | "compose" | "mask";
  setSurfaceTab: (t: "stage" | "compose" | "mask") => void;
  camYaw: number;
  setCamYaw: React.Dispatch<React.SetStateAction<number>>;
  camPitch: number;
  setCamPitch: React.Dispatch<React.SetStateAction<number>>;
  camDist: number;
  setCamDist: React.Dispatch<React.SetStateAction<number>>;
  camFov: number;
  setCamFov: React.Dispatch<React.SetStateAction<number>>;
  selectedModel: string;
  setSelectedModel: (m: string) => void;
  objs: SceneObject[];
  setObjs: React.Dispatch<React.SetStateAction<SceneObject[]>>;
  selObjId: string;
  setSelObjId: (id: string) => void;
  selectedObj: SceneObject | undefined;
  note: string;
  setNote: (n: string) => void;
  saving: boolean;
  generating: boolean;
  handlePosePreset: (key: PosePresetKey) => void;
  handleApproveStage: () => Promise<void>;
  handleAutoStage: (targetShot?: number) => Promise<void>;
  handleGenerateVideo: () => Promise<void>;
  stageCanvasRef: React.RefObject<HTMLCanvasElement | null>;
  compCanvasRef: React.RefObject<HTMLCanvasElement | null>;
  maskCanvasRef: React.RefObject<HTMLCanvasElement | null>;
  handleStageMouseDown: (e: React.MouseEvent<HTMLCanvasElement>) => void;
  handleStageMouseMove: (e: React.MouseEvent<HTMLCanvasElement>) => void;
  handleStageMouseUp: () => void;
  handleStageWheel: (e: React.WheelEvent<HTMLCanvasElement>) => void;
}

const Stage3DContext = createContext<Stage3DContextType | null>(null);

export const useStage3DContext = () => {
  const ctx = useContext(Stage3DContext);
  if (!ctx) throw new Error("useStage3DContext must be used within Stage3DProvider");
  return ctx;
};

export interface Stage3DProviderProps {
  id: string;
  initialShot?: number;
  onShotChange?: (shot: number) => void;
  children: React.ReactNode;
}

export const Stage3DProvider: React.FC<Stage3DProviderProps> = ({
  id,
  initialShot = 1,
  onShotChange,
  children,
}) => {
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [shot, setShot] = useState<number>(initialShot);
  const [surfaceTab, setSurfaceTab] = useState<"stage" | "compose" | "mask">("stage");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [note, setNote] = useState("");

  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const CW = aspect === "9:16" ? 405 : aspect === "16:9" ? 720 : 540;
  const CH = aspect === "9:16" ? 720 : aspect === "16:9" ? 405 : 540;

  const [selectedModel, setSelectedModel] = useState<string>("veo_3_1_lite");
  const [camYaw, setCamYaw] = useState<number>(25);
  const [camPitch, setCamPitch] = useState<number>(18);
  const [camDist, setCamDist] = useState<number>(6.5);
  const [camFov, setCamFov] = useState<number>(50);

  const [objs, setObjs] = useState<SceneObject[]>([
    {
      id: "obj-1",
      kind: "character",
      label: "Pin (주인공)",
      x: 0,
      y: 0,
      z: 0,
      w: 0.85,
      h: 1.75,
      d: 0.55,
      color: "#6366f1",
      posePreset: "stand",
      pose: { ...POSE_PRESETS.stand.pose },
    },
    {
      id: "obj-prop-1",
      kind: "prop",
      label: "USB 포트 블록 (소품)",
      x: 0.65,
      y: 0.4,
      z: 0.2,
      w: 0.7,
      h: 0.8,
      d: 0.7,
      color: "#f59e0b",
    },
  ]);
  const [selObjId, setSelObjId] = useState<string>("obj-1");

  const stageCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const compCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const bgImgRef = useRef<HTMLImageElement | null>(null);
  const charViewsRef = useRef<Record<string, HTMLImageElement>>({});
  const orbitRef = useRef<{ startX: number; startY: number; yaw: number; pitch: number } | null>(null);

  // 2D -> 3D 캐릭터 4방향 시트 로드
  useEffect(() => {
    const charName = pipeline?.characters?.[0]?.name || "Pin";
    const views = ["front", "back", "left", "right"];
    for (const v of views) {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        charViewsRef.current[v] = img;
      };
      img.src = `/api/pipefiles/${id}/characters/${charName}/${v}.png`;
    }
  }, [id, pipeline]);

  // 파이프라인 데이터 로드
  useEffect(() => {
    let active = true;
    api.pipeline(id).then((p) => {
      if (active) setPipeline(p);
    }).catch((err) => console.error("Pipeline load failed:", err));
    return () => { active = false; };
  }, [id]);

  const shotsList = pipeline?.shotplan?.shots || [];
  const curShot = shotsList.find((s) => s.n === shot) || shotsList[0];
  const curKf = pipeline?.keyframes?.find((k) => k.shot === shot);

  useEffect(() => {
    if (curShot && onShotChange) {
      onShotChange(shot);
    }
  }, [shot, curShot, onShotChange]);

  // 배경 이미지 로드 (이전 렌더 또는 캐릭터 시트)
  useEffect(() => {
    if (!curKf?.first) {
      bgImgRef.current = null;
      return;
    }
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => { bgImgRef.current = img; };
    img.src = F(curKf.first);
  }, [curKf?.first]);

  // 3D 관절 계산
  function computeMannequinJoints(obj: SceneObject): Record<string, Vec3> {
    const ox = obj.x;
    const oy = obj.y;
    const oz = obj.z;
    const scale = (obj.h || 1.75) / 1.75;
    const preset = POSE_PRESETS[obj.posePreset || "stand"]?.pose || POSE_PRESETS.stand.pose;
    const pose = { ...preset, ...(obj.pose || {}) };

    const byaw = (pose.bodyYaw * Math.PI) / 180;
    const lean = (pose.torsoLean * Math.PI) / 180;
    const hyaw = (pose.headYaw * Math.PI) / 180;
    const hpitch = (pose.headPitch * Math.PI) / 180;

    const rotY = (v: Vec3, a: number): Vec3 => [
      v[0] * Math.cos(a) + v[2] * Math.sin(a),
      v[1],
      -v[0] * Math.sin(a) + v[2] * Math.cos(a),
    ];
    const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

    const hipPitchAvg = 0.5 * (pose.lHipPitch + pose.rHipPitch);
    const pelvisY = oy + (hipPitchAvg > 60 ? 0.58 : 0.92) * scale;
    const pelvis: Vec3 = [ox, pelvisY, oz];

    const torsoLen = 0.48 * scale;
    const chestLocal = rotY([0, torsoLen * Math.cos(lean), torsoLen * Math.sin(lean)], byaw);
    const chest = add(pelvis, chestLocal);
    const neck = add(chest, rotY([0, 0.12 * scale, 0.02 * scale * Math.sin(lean)], byaw));
    const headDir = rotY([0, 0.16 * scale * Math.cos(hpitch), 0.16 * scale * Math.sin(hpitch)], byaw + hyaw);
    const head = add(neck, headDir);

    const shW = 0.21 * scale;
    const uArm = 0.28 * scale;
    const lArm = 0.26 * scale;

    const armChain = (side: number, spDeg: number, srDeg: number, ebDeg: number) => {
      const sh = add(chest, rotY([side * shW, 0.04 * scale, 0], byaw));
      const sp = (spDeg * Math.PI) / 180;
      const sr = (srDeg * Math.PI) / 180;
      const ux = side * Math.sin(sr) * Math.cos(sp * 0.3);
      const uy = -Math.cos(sp) * Math.cos(sr);
      const uz = Math.sin(sp);
      const el = add(sh, [ux * uArm, uy * uArm, uz * uArm]);
      const eb = (ebDeg * Math.PI) / 180;
      const fx = ux * Math.cos(eb) + Math.sin(eb) * (side * 0.4);
      const fy = uy * Math.cos(eb) - Math.abs(Math.sin(eb)) * 0.7;
      const fz = uz * Math.cos(eb) + Math.sin(eb) * 0.6;
      const fl = Math.sqrt(fx * fx + fy * fy + fz * fz) || 1;
      const ha = add(el, [(fx / fl) * lArm, (fy / fl) * lArm, (fz / fl) * lArm]);
      return { sh, el, ha };
    };

    const { sh: lSh, el: lEl, ha: lHa } = armChain(-1, pose.lShoulderPitch, pose.lShoulderRoll, pose.lElbowBend);
    const { sh: rSh, el: rEl, ha: rHa } = armChain(1, pose.rShoulderPitch, pose.rShoulderRoll, pose.rElbowBend);

    const hipW = 0.13 * scale;
    const uLeg = 0.42 * scale;
    const lLeg = 0.38 * scale;

    const legChain = (side: number, hpDeg: number, kbDeg: number) => {
      const hp = add(pelvis, rotY([side * hipW, -0.04 * scale, 0], byaw));
      const p = (hpDeg * Math.PI) / 180;
      const kx = side * 0.03;
      const ky = -Math.cos(p);
      const kz = Math.sin(p);
      const kn = add(hp, [kx * uLeg, ky * uLeg, kz * uLeg]);
      const kb = (kbDeg * Math.PI) / 180;
      const kbx = kx;
      const kby = ky * Math.cos(kb) - Math.sin(kb) * 0.4;
      const kbz = kz * Math.cos(kb) - Math.sin(kb) * 0.85;
      const kl = Math.sqrt(kbx * kbx + kby * kby + kbz * kbz) || 1;
      const ank = add(kn, [(kbx / kl) * lLeg, (kby / kl) * lLeg, (kbz / kl) * lLeg]);
      return { hp, kn, ank };
    };

    const { hp: lHip, kn: lKn, ank: lAnk } = legChain(-1, pose.lHipPitch, pose.lKneeBend);
    const { hp: rHip, kn: rKn, ank: rAnk } = legChain(1, pose.rHipPitch, pose.rKneeBend);

    return {
      pelvis, chest, neck, head,
      lShoulder: lSh, lElbow: lEl, lHand: lHa,
      rShoulder: rSh, rElbow: rEl, rHand: rHa,
      lHip, lKnee: lKn, lAnkle: lAnk,
      rHip, rKnee: rKn, rAnkle: rAnk,
    };
  }

  // 3D 뷰포트 렌더링
  useEffect(() => {
    if (surfaceTab !== "stage") return;
    const cv = stageCanvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;

    const W = CW;
    const H = CH;
    const yaw = (camYaw * Math.PI) / 180;
    const pitch = (camPitch * Math.PI) / 180;
    const dist = Math.max(2, camDist);
    const fov = (Math.max(20, Math.min(110, camFov)) * Math.PI) / 180;
    const target: Vec3 = [0, 0.85, 0];

    const cx = target[0] + dist * Math.cos(pitch) * Math.sin(yaw);
    const cy = target[1] + dist * Math.sin(pitch);
    const cz = target[2] + dist * Math.cos(pitch) * Math.cos(yaw);

    let fx = target[0] - cx;
    let fy = target[1] - cy;
    let fz = target[2] - cz;
    const fl = Math.sqrt(fx * fx + fy * fy + fz * fz) || 1;
    fx /= fl; fy /= fl; fz /= fl;

    let rx = -fz;
    const ry = 0;
    let rz = fx;
    const rl = Math.sqrt(rx * rx + rz * rz) || 1;
    rx /= rl; rz /= rl;

    const ux = ry * fz - rz * fy;
    const uy = rz * fx - rx * fz;
    const uz = rx * fy - ry * fx;

    const focal = (Math.min(W, H) * 0.5) / Math.tan(fov * 0.5);

    const project = (pt: Vec3): Vec3 | null => {
      const dx = pt[0] - cx;
      const dy = pt[1] - cy;
      const dz = pt[2] - cz;
      const z = dx * fx + dy * fy + dz * fz;
      if (z <= 0.15) return null;
      const x = dx * rx + dy * ry + dz * rz;
      const y = dx * ux + dy * uy + dz * uz;
      return [W * 0.5 + (x / z) * focal, H * 0.5 - (y / z) * focal, z];
    };

    // 배경 지우기 & 다크 그라데이션
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, "#12121a");
    grad.addColorStop(1, "#0a0a0f");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    // 바닥 3D 그리드 (점 격자 및 메쉬)
    ctx.strokeStyle = "rgba(99, 102, 241, 0.18)";
    ctx.lineWidth = 1;
    const gridSize = 3.0;
    const gridSteps = 10;
    for (let i = -gridSteps; i <= gridSteps; i++) {
      const p1 = project([i * (gridSize / gridSteps), 0, -gridSize]);
      const p2 = project([i * (gridSize / gridSteps), 0, gridSize]);
      if (p1 && p2) {
        ctx.beginPath();
        ctx.moveTo(p1[0], p1[1]);
        ctx.lineTo(p2[0], p2[1]);
        ctx.stroke();
      }
      const q1 = project([-gridSize, 0, i * (gridSize / gridSteps)]);
      const q2 = project([gridSize, 0, i * (gridSize / gridSteps)]);
      if (q1 && q2) {
        ctx.beginPath();
        ctx.moveTo(q1[0], q1[1]);
        ctx.lineTo(q2[0], q2[1]);
        ctx.stroke();
      }
    }

    // 마네킹 관절 및 뼈대 드로우
    for (const obj of objs) {
      if (obj.kind === "character") {
        // 2D -> 3D 캐릭터 텍스처 투영 (카메라 각도에 따라 front, left, back, right 자동 회전)
        const relYaw = ((camYaw - (obj.pose?.bodyYaw || 0)) % 360 + 360) % 360;
        let activeView = "front";
        if (relYaw >= 45 && relYaw < 135) activeView = "left";
        else if (relYaw >= 135 && relYaw < 225) activeView = "back";
        else if (relYaw >= 225 && relYaw < 315) activeView = "right";

        const charImg = charViewsRef.current[activeView] || charViewsRef.current.front;
        if (charImg && charImg.complete && charImg.naturalWidth > 0) {
          const h = obj.h || 1.75;
          const btm = project([obj.x, obj.y, obj.z]);
          const top = project([obj.x, obj.y + h, obj.z]);
          if (btm && top) {
            const hPx = Math.abs(btm[1] - top[1]);
            const aspect = charImg.naturalWidth / charImg.naturalHeight || 0.56;
            const wPx = hPx * aspect;
            ctx.save();
            ctx.globalAlpha = 0.82;
            ctx.drawImage(charImg, btm[0] - wPx * 0.5, top[1], wPx, hPx);
            ctx.restore();
          }
        }

        const joints = computeMannequinJoints(obj);
        const pj: Record<string, Vec3> = {};
        let skip = false;
        for (const [k, v] of Object.entries(joints)) {
          const pr = project(v);
          if (!pr) { skip = true; break; }
          pj[k] = pr;
        }
        if (skip) continue;

        const limbs: [string, string, number][] = [
          ["pelvis", "chest", 0.12],
          ["chest", "neck", 0.06],
          ["lShoulder", "rShoulder", 0.06],
          ["lHip", "rHip", 0.06],
          ["lShoulder", "lElbow", 0.05],
          ["lElbow", "lHand", 0.04],
          ["rShoulder", "rElbow", 0.05],
          ["rElbow", "rHand", 0.04],
          ["lHip", "lKnee", 0.06],
          ["lKnee", "lAnkle", 0.05],
          ["rHip", "rKnee", 0.06],
          ["rKnee", "rAnkle", 0.05],
        ];

        // 뼈대 연결선
        for (const [a, b, rad] of limbs) {
          const pa = pj[a];
          const pb = pj[b];
          const avgZ = (pa[2] + pb[2]) * 0.5;
          const wPx = Math.max(4, ((rad * 2) / avgZ) * focal);
          ctx.strokeStyle = obj.id === selObjId ? "rgba(99, 102, 241, 0.95)" : "rgba(165, 180, 252, 0.8)";
          ctx.lineWidth = wPx;
          ctx.lineCap = "round";
          ctx.beginPath();
          ctx.moveTo(pa[0], pa[1]);
          ctx.lineTo(pb[0], pb[1]);
          ctx.stroke();
        }

        // 관절 노드
        for (const [k, pt] of Object.entries(pj)) {
          const radM = k === "head" ? 0.14 : (k === "chest" || k === "pelvis" ? 0.09 : 0.05);
          const rPx = Math.max(3, (radM / pt[2]) * focal);
          ctx.fillStyle = k === "head" ? "#fbbf24" : (obj.id === selObjId ? "#818cf8" : "#c7d2fe");
          ctx.beginPath();
          ctx.arc(pt[0], pt[1], rPx, 0, Math.PI * 2);
          ctx.fill();
        }
      } else if (obj.kind === "prop" || obj.kind === "box") {
        const ox = obj.x, oy = obj.y, oz = obj.z;
        const hw = (obj.w || 0.6) * 0.5, hh = (obj.h || 0.6) * 0.5, hd = (obj.d || 0.6) * 0.5;
        const corners: Vec3[] = [
          [ox - hw, oy - hh, oz - hd], [ox + hw, oy - hh, oz - hd],
          [ox + hw, oy - hh, oz + hd], [ox - hw, oy - hh, oz + hd],
          [ox - hw, oy + hh, oz - hd], [ox + hw, oy + hh, oz - hd],
          [ox + hw, oy + hh, oz + hd], [ox - hw, oy + hh, oz + hd],
        ];
        const pc = corners.map(project);
        if (pc.every(Boolean)) {
          const edges = [
            [0,1],[1,2],[2,3],[3,0],
            [4,5],[5,6],[6,7],[7,4],
            [0,4],[1,5],[2,6],[3,7]
          ];
          ctx.strokeStyle = obj.id === selObjId ? "#f59e0b" : "rgba(245, 158, 11, 0.7)";
          ctx.lineWidth = obj.id === selObjId ? 2.5 : 1.5;
          for (const [i1, i2] of edges) {
            ctx.beginPath();
            ctx.moveTo(pc[i1]![0], pc[i1]![1]);
            ctx.lineTo(pc[i2]![0], pc[i2]![1]);
            ctx.stroke();
          }
        }
      }
    }

    // 종횡비 안내선 오버레이
    ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
    ctx.lineWidth = 1;
    ctx.strokeRect(20, 20, W - 40, H - 40);
  }, [CW, CH, camYaw, camPitch, camDist, camFov, objs, selObjId, surfaceTab]);

  // 카메라 마우스 드래그 궤도 회전
  const handleStageMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    orbitRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      yaw: camYaw,
      pitch: camPitch,
    };
  };

  const handleStageMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!orbitRef.current) return;
    const dx = e.clientX - orbitRef.current.startX;
    const dy = e.clientY - orbitRef.current.startY;
    setCamYaw((orbitRef.current.yaw + dx * 0.5) % 360);
    setCamPitch(Math.max(-85, Math.min(85, orbitRef.current.pitch - dy * 0.5)));
  };

  const handleStageMouseUp = () => {
    orbitRef.current = null;
  };

  const handleStageWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    setCamDist((d) => Math.max(1.5, Math.min(25, d + e.deltaY * 0.01)));
  };

  // 포즈 프리셋 변경
  const selectedObj = objs.find((o) => o.id === selObjId);
  const handlePosePreset = (key: PosePresetKey) => {
    if (!selectedObj) return;
    setObjs((prev) =>
      prev.map((o) =>
        o.id === selObjId
          ? { ...o, posePreset: key, pose: { ...POSE_PRESETS[key].pose } }
          : o
      )
    );
  };

  // 3D 무대 구도 확정
  const handleApproveStage = async () => {
    setSaving(true);
    try {
      const cv = stageCanvasRef.current;
      if (!cv) throw new Error("캔버스를 찾을 수 없습니다");
      const dataUrl = cv.toDataURL("image/png");

      const spec = {
        camera: { yaw: camYaw, pitch: camPitch, dist: camDist, fov: camFov },
        objects: objs,
      };

      const res = await fetch(`/api/pipeline/${id}/keyframe/${shot}/guide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "stage", dataUrl, spec, note }),
      });
      if (!res.ok) throw new Error("무대 가이드 저장 실패");

      // 무대는 구도 가이드 — 이걸 참고로 실제 키 프레임을 만든다(승인 ②는 만들어진 키 프레임을 보고)
      const mkRes = await fetch(`/api/pipeline/${id}/keyframe/make`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shots: String(shot) }),
      });
      if (!mkRes.ok) throw new Error((await mkRes.json().catch(() => ({}))).error || "키 프레임 생성 시작 실패");

      toast.success(t(`샷 #${shot} 무대 구도를 저장하고 키 프레임 생성을 시작했습니다 — 결과를 보고 승인하세요`));
      const fresh = await api.pipeline(id);
      setPipeline(fresh);
    } catch (err: unknown) {
      toast.error(errMsg(err));
    } finally {
      setSaving(false);
    }
  };

  // 전자동 3D 무대 구도 계산 및 캡처
  const handleAutoStage = async (targetShot?: number) => {
    setSaving(true);
    try {
      const res = await fetch(`/api/pipeline/${id}/keyframe/auto-stage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(targetShot ? { shots: String(targetShot) } : {}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "3D 무대 자동 구도 생성 실패");
      toast.success(
        t(
          targetShot
            ? `샷 #${targetShot} 3D 구도 가이드를 그렸습니다 — '현재 무대 확정'으로 키 프레임을 만드세요`
            : `전체 샷 3D 구도 가이드를 그렸습니다 — 샷마다 '현재 무대 확정'으로 키 프레임을 만드세요`
        )
      );
      const fresh = await api.pipeline(id);
      setPipeline(fresh);
    } catch (err: unknown) {
      toast.error(errMsg(err));
    } finally {
      setSaving(false);
    }
  };

  // 영상 생성 실행
  const handleGenerateVideo = async () => {
    setGenerating(true);
    try {
      // 승인 ②(키 프레임)를 받은 샷만 생성된다 — 서버가 안 된 샷이면 오류로 알려 준다
      const res = await fetch(`/api/pipeline/${id}/video/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shots: String(shot) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "영상 생성 실패");

      toast.success(t(`샷 #${shot} 영상 생성 작업이 시작되었습니다`));
    } catch (err: unknown) {
      toast.error(errMsg(err));
    } finally {
      setGenerating(false);
    }
  };

  const contextValue: Stage3DContextType = {
    id,
    pipeline,
    shotsList,
    shot,
    setShot,
    curShot,
    curKf,
    aspect,
    setAspect,
    CW,
    CH,
    surfaceTab,
    setSurfaceTab,
    camYaw,
    setCamYaw,
    camPitch,
    setCamPitch,
    camDist,
    setCamDist,
    camFov,
    setCamFov,
    selectedModel,
    setSelectedModel,
    objs,
    setObjs,
    selObjId,
    setSelObjId,
    selectedObj,
    note,
    setNote,
    saving,
    generating,
    handlePosePreset,
    handleApproveStage,
    handleAutoStage,
    handleGenerateVideo,
    stageCanvasRef,
    compCanvasRef,
    maskCanvasRef,
    handleStageMouseDown,
    handleStageMouseMove,
    handleStageMouseUp,
    handleStageWheel,
  };

  return (
    <Stage3DContext.Provider value={contextValue}>
      {children}
    </Stage3DContext.Provider>
  );
};

/** 중앙 3D 무대 캔버스 뷰포트 */
export const Stage3DCanvas: React.FC<{ onSwitchToPreview?: () => void }> = ({ onSwitchToPreview }) => {
  const {
    CW,
    CH,
    surfaceTab,
    setSurfaceTab,
    aspect,
    setAspect,
    camYaw,
    setCamYaw,
    camPitch,
    setCamPitch,
    camDist,
    stageCanvasRef,
    compCanvasRef,
    handleStageMouseDown,
    handleStageMouseMove,
    handleStageMouseUp,
    handleStageWheel,
  } = useStage3DContext();

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 relative min-w-0 min-h-0 bg-radial from-[#171722] via-[#0d0d14] to-[#07070a] select-none size-full overflow-hidden">
      {/* 상단 서피스 탭 바 & 화면 비율 / 카메라 프리셋 */}
      <div className="absolute top-3 z-20 flex flex-wrap items-center justify-center gap-2 max-w-[94%]">
        <div className="flex items-center gap-1 p-1 rounded-full bg-black/60 backdrop-blur-md border border-white/10 shadow-lg">
          <button
            type="button"
            onClick={() => setSurfaceTab("stage")}
            className={`px-3 py-1 text-xs font-semibold rounded-full transition-all flex items-center gap-1.5 ${
              surfaceTab === "stage" ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-white"
            }`}
          >
            <span>🧊 3D 무대 연출</span>
          </button>
          <button
            type="button"
            onClick={() => setSurfaceTab("compose")}
            className={`px-3 py-1 text-xs font-semibold rounded-full transition-all flex items-center gap-1.5 ${
              surfaceTab === "compose" ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-white"
            }`}
          >
            <span>🎨 2D 캔버스 합성</span>
          </button>
          {onSwitchToPreview && (
            <button
              type="button"
              onClick={onSwitchToPreview}
              className="px-3 py-1 text-xs font-semibold rounded-full text-muted-foreground hover:text-white transition-all flex items-center gap-1.5"
            >
              <span>🎬 비디오 프리뷰</span>
            </button>
          )}
        </div>

        {/* 화면 비율 선택 */}
        <div className="flex items-center gap-1 p-1 rounded-full bg-black/50 backdrop-blur-md border border-white/10 text-xs">
          {(["9:16", "16:9", "1:1"] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setAspect(r)}
              className={`px-2.5 py-0.5 rounded-full font-medium transition-all ${
                aspect === r ? "bg-white/20 text-white font-bold" : "text-white/50 hover:text-white"
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        {/* 카메라 각도 빠른 프리셋 */}
        <div className="flex items-center gap-1 p-1 rounded-full bg-black/50 backdrop-blur-md border border-white/10 text-xs">
          <button
            type="button"
            onClick={() => { setCamYaw(0); setCamPitch(0); }}
            className="px-2 py-0.5 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition-all"
          >
            정면
          </button>
          <button
            type="button"
            onClick={() => { setCamYaw(90); setCamPitch(0); }}
            className="px-2 py-0.5 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition-all"
          >
            측면
          </button>
          <button
            type="button"
            onClick={() => { setCamYaw(0); setCamPitch(80); }}
            className="px-2 py-0.5 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition-all"
          >
            탑뷰
          </button>
          <button
            type="button"
            onClick={() => { setCamYaw(35); setCamPitch(20); }}
            className="px-2 py-0.5 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition-all"
          >
            쿼터뷰
          </button>
        </div>
      </div>

      {/* 캔버스 화면 */}
      <div
        className="relative rounded-xl overflow-hidden shadow-2xl border border-white/10 bg-[#09090d]"
        style={{ width: CW, height: CH }}
      >
        {surfaceTab === "stage" && (
          <canvas
            ref={stageCanvasRef}
            width={CW}
            height={CH}
            className="size-full cursor-grab active:cursor-grabbing"
            onMouseDown={handleStageMouseDown}
            onMouseMove={handleStageMouseMove}
            onMouseUp={handleStageMouseUp}
            onMouseLeave={handleStageMouseUp}
            onWheel={handleStageWheel}
          />
        )}

        {surfaceTab === "compose" && (
          <canvas
            ref={compCanvasRef}
            width={CW}
            height={CH}
            className="size-full cursor-move"
          />
        )}

        {/* 3D 뷰포트 내 좌측 상단 카메라 힌트 */}
        <div className="absolute top-3 left-3 pointer-events-none text-[11px] text-white/50 bg-black/40 backdrop-blur-sm px-2 py-1 rounded-md border border-white/5">
          카메라: Yaw {Math.round(camYaw)}° · Pitch {Math.round(camPitch)}° · 거리 {camDist.toFixed(1)}m
        </div>
      </div>
    </div>
  );
};

/** 우측 3D 무대 속성 및 포즈 컨트롤 패널 (PropertiesPanel 슬롯) */
export const Stage3DPropertiesPanel: React.FC = () => {
  const {
    selectedObj,
    handlePosePreset,
    camYaw,
    setCamYaw,
    camPitch,
    setCamPitch,
    camDist,
    setCamDist,
    camFov,
    setCamFov,
    curShot,
  } = useStage3DContext();

  return (
    <div className="size-full bg-background p-3.5 flex flex-col gap-4 overflow-y-auto text-foreground select-none text-xs">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">마네킹 포즈 프리셋</span>
        <span className="text-[11px] text-primary font-medium">15개 관절 조작</span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {(Object.keys(POSE_PRESETS) as PosePresetKey[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => handlePosePreset(key)}
            className={`h-7 px-2 text-xs rounded-md border text-left font-medium transition-all ${
              selectedObj?.posePreset === key
                ? "bg-primary/20 border-primary text-primary-foreground font-bold shadow-sm"
                : "bg-muted/40 border-border/40 text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            {POSE_PRESETS[key].label}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between border-b border-border pb-2 pt-2">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">3D 카메라 설정</span>
      </div>

      <div className="flex flex-col gap-2.5 text-xs">
        <div className="flex justify-between items-center text-muted-foreground">
          <span>수평 궤도 (Yaw)</span>
          <span className="font-mono text-[11px] font-semibold text-foreground">{Math.round(camYaw)}°</span>
        </div>
        <input
          type="range"
          min={0}
          max={360}
          value={camYaw}
          onChange={(e) => setCamYaw(Number(e.target.value))}
          className="w-full accent-primary"
        />

        <div className="flex justify-between items-center text-muted-foreground">
          <span>수직 각도 (Pitch)</span>
          <span className="font-mono text-[11px] font-semibold text-foreground">{Math.round(camPitch)}°</span>
        </div>
        <input
          type="range"
          min={-80}
          max={80}
          value={camPitch}
          onChange={(e) => setCamPitch(Number(e.target.value))}
          className="w-full accent-primary"
        />

        <div className="flex justify-between items-center text-muted-foreground">
          <span>카메라 거리 (Dist)</span>
          <span className="font-mono text-[11px] font-semibold text-foreground">{camDist.toFixed(1)}m</span>
        </div>
        <input
          type="range"
          min={2}
          max={15}
          step={0.5}
          value={camDist}
          onChange={(e) => setCamDist(Number(e.target.value))}
          className="w-full accent-primary"
        />

        <div className="flex justify-between items-center text-muted-foreground">
          <span>화각 (FOV)</span>
          <span className="font-mono text-[11px] font-semibold text-foreground">{camFov}°</span>
        </div>
        <input
          type="range"
          min={24}
          max={90}
          value={camFov}
          onChange={(e) => setCamFov(Number(e.target.value))}
          className="w-full accent-primary"
        />
      </div>

      <div className="flex items-center justify-between border-b border-border pb-2 pt-2">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">현재 샷 정보</span>
      </div>

      <div className="p-2.5 rounded-lg bg-muted/40 border border-border/50 flex flex-col gap-1.5 text-xs">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-foreground">#{curShot?.n} {curShot?.purpose}</span>
          <span className="text-[11px] text-muted-foreground">{curShot?.final_sec}초 (생성 {curShot?.gen_sec}초)</span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">{curShot?.beat}</p>
      </div>
    </div>
  );
};

/** 하단 플로팅 프롬프트 바 (ArtCraft Floating Prompt Bar) */
export const ArtCraftPromptBar: React.FC<{
  surfaceMode: "preview" | "stage" | "compose";
  onSeekTimeline?: (shotNumber: number) => void;
}> = ({ surfaceMode, onSeekTimeline }) => {
  const {
    shotsList,
    shot,
    setShot,
    curShot,
    selectedModel,
    setSelectedModel,
    note,
    setNote,
    saving,
    generating,
    handleApproveStage,
    handleAutoStage,
    handleGenerateVideo,
  } = useStage3DContext();

  const handleShotClick = (n: number) => {
    setShot(n);
    if (onSeekTimeline) {
      onSeekTimeline(n);
    }
  };

  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 w-[min(760px,96%)] p-2 rounded-2xl bg-black/75 backdrop-blur-xl border border-white/15 shadow-2xl flex flex-col gap-1.5 select-none font-sans">
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-hidden">
          <span className="text-[11px] font-bold text-primary-400 shrink-0">샷:</span>
          <div className="flex items-center gap-1">
            {shotsList.map((s) => (
              <button
                key={s.n}
                type="button"
                onClick={() => handleShotClick(s.n)}
                className={`h-6 px-2 text-[11px] rounded-md font-medium border transition-all shrink-0 ${
                  s.n === shot
                    ? "bg-primary text-white border-primary shadow-sm"
                    : "bg-white/5 text-white/70 border-white/10 hover:bg-white/10 hover:text-white"
                }`}
              >
                #{s.n} {s.purpose}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 text-[11px] text-white/60 shrink-0">
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="h-6 px-1.5 rounded bg-white/10 border border-white/10 text-[11px] font-mono text-white focus:outline-none cursor-pointer"
          >
            <option value="veo_3_1_lite" className="bg-[#181822]">Veo 3.1 Lite</option>
            <option value="omni_flash" className="bg-[#181822]">Omni Flash</option>
            <option value="omni_1_2_flash" className="bg-[#181822]">Omni 1.2 Flash</option>
          </select>
          <span className="text-emerald-400 font-semibold">$0 무대 렌더</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={note || curShot?.beat || ""}
          onChange={(e) => setNote(e.target.value)}
          placeholder="구도 및 연출 지시어 (예: 핀이 오른쪽에서 플러그를 미는 구도 유지)"
          className="flex-1 h-8 px-3 rounded-lg bg-white/5 border border-white/10 text-xs text-white placeholder-white/40 focus:outline-none focus:border-primary"
        />

        <button
          type="button"
          disabled={saving || generating}
          onClick={() => handleAutoStage()}
          className="h-8 px-2.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-xs font-semibold text-indigo-200 border border-indigo-400/30 transition-all flex items-center gap-1 shrink-0"
          title="콘티의 카메라 각도·거리·캐릭터를 분석해 전 샷의 3D 구도 가이드를 그립니다(키 프레임 생성의 참고용)"
        >
          <span>✨ 전 샷 3D 자동 구도</span>
        </button>

        <button
          type="button"
          disabled={saving}
          onClick={handleApproveStage}
          className="h-8 px-3 rounded-lg bg-white/10 hover:bg-white/15 text-xs font-semibold text-white border border-white/10 transition-all flex items-center gap-1 shrink-0"
        >
          <span>{saving ? "확정 중…" : "🧊 현재 무대 확정"}</span>
        </button>

        <button
          type="button"
          disabled={generating}
          onClick={handleGenerateVideo}
          className="h-8 px-3.5 rounded-lg bg-primary hover:bg-primary-hover text-xs font-bold text-white shadow-md shadow-primary/25 transition-all flex items-center gap-1 shrink-0"
        >
          <span>{generating ? "생성 중…" : "🎬 이 구도로 생성"}</span>
        </button>
      </div>
    </div>
  );
};

/** 서피스 모드 스위처 (🎬 비디오 프리뷰 ↔ 🧊 3D 무대 ↔ 🎨 2D 캔버스) */
export const SurfaceSwitcher: React.FC<{
  surfaceMode: "preview" | "stage" | "compose";
  onSelectSurface: (m: "preview" | "stage" | "compose") => void;
}> = ({ surfaceMode, onSelectSurface }) => {
  return (
    <div className="inline-flex p-1 bg-black/50 backdrop-blur-lg rounded-xl border border-white/10 shadow-inner select-none">
      <button
        type="button"
        onClick={() => onSelectSurface("preview")}
        className={`h-7 px-3 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all duration-150 ${
          surfaceMode === "preview"
            ? "bg-gradient-to-r from-primary to-indigo-600 text-white shadow-md shadow-primary/25 ring-1 ring-white/15"
            : "text-muted-foreground hover:text-white hover:bg-white/5"
        }`}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="5 3 19 12 5 21 5 3" />
        </svg>
        <span>{t("비디오 프리뷰")}</span>
      </button>

      <button
        type="button"
        onClick={() => onSelectSurface("stage")}
        className={`h-7 px-3 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all duration-150 ${
          surfaceMode === "stage"
            ? "bg-gradient-to-r from-primary to-indigo-600 text-white shadow-md shadow-primary/25 ring-1 ring-white/15"
            : "text-muted-foreground hover:text-white hover:bg-white/5"
        }`}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
          <line x1="12" y1="22.08" x2="12" y2="12" />
        </svg>
        <span>{t("3D 무대 (Scene)")}</span>
      </button>

      <button
        type="button"
        onClick={() => onSelectSurface("compose")}
        className={`h-7 px-3 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all duration-150 ${
          surfaceMode === "compose"
            ? "bg-gradient-to-r from-primary to-indigo-600 text-white shadow-md shadow-primary/25 ring-1 ring-white/15"
            : "text-muted-foreground hover:text-white hover:bg-white/5"
        }`}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
        <span>{t("2D 캔버스")}</span>
      </button>
    </div>
  );
};

/** 단독 사용을 위한 래퍼 컴포넌트 */
export const Stage3DView: React.FC<{
  id: string;
  initialShot?: number;
  onShotChange?: (shot: number) => void;
  onSwitchToEditor?: () => void;
}> = ({ id, initialShot = 1, onShotChange, onSwitchToEditor }) => {
  return (
    <Stage3DProvider id={id} initialShot={initialShot} onShotChange={onShotChange}>
      <div className="flex size-full bg-[#0d0d12] text-[#f1f1f5] select-none overflow-hidden relative font-sans">
        <Stage3DCanvas onSwitchToPreview={onSwitchToEditor} />
        <div className="w-80 h-full border-l border-white/10 bg-[#121219]">
          <Stage3DPropertiesPanel />
        </div>
        <ArtCraftPromptBar surfaceMode="stage" />
      </div>
    </Stage3DProvider>
  );
};
