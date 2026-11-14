/* 키 프레임 구도 · 마스크 스튜디오 (ArtCraft 스타일 2D 캔버스 합성/마스크 인페인팅 & 3D 마네킹 포즈 스테이지 프리비즈).
   - 2D 마스크 인페인팅: 현재 키프레임 위에 수정할 영역(흰색 브러시)을 칠해 s<NN>_mask.png 로 저장 → keyframe.py make 가 마스크 인페인팅 레퍼런스로 전달
   - 2D 레이어 합성: 캐릭터 시트 · 업로드 사진을 캔버스에 배치/크기/회전 조절해 s<NN>_compose.png 로 저장 → 구도 레퍼런스로 전달
   - 3D 마네킹 포즈 스테이지 프리비즈: 15개 인체 관절 마네킹(포즈 프리셋 + 관절별 슬라이더)과 3D 카메라를 조절해 s<NN>_stage.png 로 저장 (Blender 5.2 3D 렌더링 선택 가능) */
import React, { useEffect, useRef, useState } from "react";
import * as RDialog from "@radix-ui/react-dialog";
import { toast } from "sonner";
import { api, errMsg, type Pipeline } from "../../lib/api";
import { t } from "../../lib/i18n";

const F = (rel: string | null | undefined) => (rel ? `/api/pipefiles/${rel}` : "");

interface Layer2D {
  id: string;
  label: string;
  url: string;
  img: HTMLImageElement;
  x: number;
  y: number;
  scale: number;
}

export interface MannequinPose {
  bodyYaw: number;
  torsoLean: number;
  headYaw: number;
  headPitch: number;
  lShoulderPitch: number;
  lShoulderRoll: number;
  lElbowBend: number;
  rShoulderPitch: number;
  rShoulderRoll: number;
  rElbowBend: number;
  lHipPitch: number;
  lKneeBend: number;
  rHipPitch: number;
  rKneeBend: number;
}

export type PosePresetKey = "stand" | "wave" | "point" | "run" | "sit" | "cheer" | "phone";

export const POSE_PRESETS: Record<PosePresetKey, { label: string; pose: MannequinPose }> = {
  stand: {
    label: "기본 서기",
    pose: { bodyYaw: 0, torsoLean: 0, headYaw: 0, headPitch: 0, lShoulderPitch: 8, lShoulderRoll: 12, lElbowBend: 15, rShoulderPitch: 8, rShoulderRoll: 12, rElbowBend: 15, lHipPitch: 0, lKneeBend: 4, rHipPitch: 0, rKneeBend: 4 },
  },
  wave: {
    label: "인사 · 손흔들기",
    pose: { bodyYaw: -10, torsoLean: -4, headYaw: 10, headPitch: -6, lShoulderPitch: 10, lShoulderRoll: 14, lElbowBend: 18, rShoulderPitch: 135, rShoulderRoll: 35, rElbowBend: 55, lHipPitch: -4, lKneeBend: 6, rHipPitch: 6, rKneeBend: 4 },
  },
  point: {
    label: "전방 가리키기",
    pose: { bodyYaw: 15, torsoLean: 8, headYaw: -12, headPitch: 0, lShoulderPitch: 15, lShoulderRoll: 15, lElbowBend: 25, rShoulderPitch: 92, rShoulderRoll: 5, rElbowBend: 8, lHipPitch: 12, lKneeBend: 8, rHipPitch: -12, rKneeBend: 10 },
  },
  run: {
    label: "달리기 · 질주",
    pose: { bodyYaw: 0, torsoLean: 24, headYaw: 0, headPitch: -10, lShoulderPitch: 65, lShoulderRoll: 15, lElbowBend: 85, rShoulderPitch: -45, rShoulderRoll: 15, rElbowBend: 75, lHipPitch: -45, lKneeBend: 65, rHipPitch: 55, rKneeBend: 25 },
  },
  sit: {
    label: "의자에 앉기",
    pose: { bodyYaw: 0, torsoLean: 10, headYaw: 0, headPitch: 5, lShoulderPitch: 28, lShoulderRoll: 12, lElbowBend: 65, rShoulderPitch: 28, rShoulderRoll: 12, rElbowBend: 65, lHipPitch: 88, lKneeBend: 88, rHipPitch: 88, rKneeBend: 88 },
  },
  cheer: {
    label: "만세 · 환호",
    pose: { bodyYaw: 0, torsoLean: -10, headYaw: 0, headPitch: -15, lShoulderPitch: 155, lShoulderRoll: 28, lElbowBend: 25, rShoulderPitch: 155, rShoulderRoll: 28, rElbowBend: 25, lHipPitch: -8, lKneeBend: 12, rHipPitch: 8, rKneeBend: 12 },
  },
  phone: {
    label: "스마트폰 보기",
    pose: { bodyYaw: -8, torsoLean: 12, headYaw: -5, headPitch: 26, lShoulderPitch: 12, lShoulderRoll: 10, lElbowBend: 20, rShoulderPitch: 58, rShoulderRoll: -15, rElbowBend: 95, lHipPitch: 0, lKneeBend: 5, rHipPitch: 0, rKneeBend: 5 },
  },
};

interface Stage3DObject {
  id: string;
  label: string;
  kind: "character" | "prop" | "product";
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

type Vec3 = [number, number, number];

function computeMannequinJoints(obj: Stage3DObject): Record<string, Vec3> {
  const ox = obj.x;
  const oy = obj.y;
  const oz = obj.z;
  const scale = (obj.h || 1.75) / 1.75;
  const p = obj.pose ?? POSE_PRESETS[obj.posePreset ?? "stand"].pose;

  const byaw = (p.bodyYaw * Math.PI) / 180;
  const lean = (p.torsoLean * Math.PI) / 180;
  const hyaw = (p.headYaw * Math.PI) / 180;
  const hpitch = (p.headPitch * Math.PI) / 180;

  const rotY = (v: Vec3, a: number): Vec3 => {
    const c = Math.cos(a);
    const s = Math.sin(a);
    return [v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c];
  };
  const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

  const hipAvg = 0.5 * (p.lHipPitch + p.rHipPitch);
  const pelvisY = oy + (hipAvg > 60 ? 0.58 : 0.92) * scale;
  const pelvis: Vec3 = [ox, pelvisY, oz];

  const torsoLen = 0.48 * scale;
  const chest = add(pelvis, rotY([0, torsoLen * Math.cos(lean), torsoLen * Math.sin(lean)], byaw));
  const neck = add(chest, rotY([0, 0.12 * scale, 0.02 * scale * Math.sin(lean)], byaw));
  const head = add(neck, rotY([0, 0.16 * scale * Math.cos(hpitch), 0.16 * scale * Math.sin(hpitch)], byaw + hyaw));

  const shW = 0.21 * scale;
  const uArm = 0.28 * scale;
  const lArm = 0.26 * scale;

  const armChain = (side: -1 | 1, spDeg: number, srDeg: number, ebDeg: number) => {
    const sh = add(chest, rotY([side * shW, 0.04 * scale, 0], byaw));
    const sp = (spDeg * Math.PI) / 180;
    const sr = (srDeg * Math.PI) / 180;
    let ux = side * Math.sin(sr) * Math.cos(sp * 0.3);
    let uy = -Math.cos(sp) * Math.cos(sr);
    let uz = Math.sin(sp);
    const ul = Math.hypot(ux, uy, uz) || 1;
    ux /= ul;
    uy /= ul;
    uz /= ul;
    const elbow = add(sh, rotY([ux * uArm, uy * uArm, uz * uArm], byaw));
    const totP = sp + (ebDeg * Math.PI) / 180;
    let fx = side * Math.sin(sr * 0.7) * 0.6;
    let fy = -Math.cos(totP) * Math.cos(sr * 0.5);
    let fz = Math.sin(totP);
    const fl = Math.hypot(fx, fy, fz) || 1;
    fx /= fl;
    fy /= fl;
    fz /= fl;
    const hand = add(elbow, rotY([fx * lArm, fy * lArm, fz * lArm], byaw));
    return { sh, elbow, hand };
  };

  const leftArm = armChain(-1, p.lShoulderPitch, p.lShoulderRoll, p.lElbowBend);
  const rightArm = armChain(1, p.rShoulderPitch, p.rShoulderRoll, p.rElbowBend);

  const hipW = 0.11 * scale;
  const uLeg = 0.44 * scale;
  const lLeg = 0.44 * scale;

  const legChain = (side: -1 | 1, hpDeg: number, kbDeg: number) => {
    const hip = add(pelvis, rotY([side * hipW, 0, 0], byaw));
    const hp = (hpDeg * Math.PI) / 180;
    const kb = (kbDeg * Math.PI) / 180;
    const knee = add(hip, rotY([side * 0.03 * uLeg, -Math.cos(hp) * uLeg, Math.sin(hp) * uLeg], byaw));
    const ankP = hp - kb;
    const ankle = add(knee, rotY([side * 0.02 * lLeg, -Math.cos(ankP) * lLeg, Math.sin(ankP) * lLeg], byaw));
    return { hip, knee, ankle };
  };

  const leftLeg = legChain(-1, p.lHipPitch, p.lKneeBend);
  const rightLeg = legChain(1, p.rHipPitch, p.rKneeBend);

  return {
    pelvis,
    chest,
    neck,
    head,
    lShoulder: leftArm.sh,
    lElbow: leftArm.elbow,
    lHand: leftArm.hand,
    rShoulder: rightArm.sh,
    rElbow: rightArm.elbow,
    rHand: rightArm.hand,
    lHip: leftLeg.hip,
    lKnee: leftLeg.knee,
    lAnkle: leftLeg.ankle,
    rHip: rightLeg.hip,
    rKnee: rightLeg.knee,
    rAnkle: rightLeg.ankle,
  };
}

export interface KeyframeStudioModalProps {
  id: string;
  shot: number;
  pipeline: Pipeline;
  onClose: () => void;
  onUpdated: () => void;
}

export const KeyframeStudioModal: React.FC<KeyframeStudioModalProps> = ({
  id,
  shot,
  pipeline,
  onClose,
  onUpdated,
}) => {
  const kf = pipeline.keyframes.find((k) => k.shot === shot);
  const shotPlan = pipeline.plan?.shots?.find((s) => s.n === shot);
  const aspect = pipeline.plan?.aspect || "9:16";
  const CW = aspect === "16:9" ? 640 : aspect === "1:1" ? 480 : 360;
  const CH = aspect === "16:9" ? 360 : aspect === "1:1" ? 480 : 640;

  const [tab, setTab] = useState<"mask" | "compose" | "stage">(
    kf?.has_stage ? "stage" : kf?.has_compose ? "compose" : "mask",
  );
  const [note, setNote] = useState(shotPlan?.keyframe_note ?? "");
  const [saving, setSaving] = useState(false);

  // --- 1. 2D Mask state ---
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const bgImgRef = useRef<HTMLImageElement | null>(null);
  const [brushSize, setBrushSize] = useState(28);
  const [eraser, setEraser] = useState(false);
  const drawingRef = useRef(false);

  // --- 2. 2D Compose state ---
  const compCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [layers, setLayers] = useState<Layer2D[]>([]);
  const [selLayerId, setSelLayerId] = useState<string | null>(null);
  const dragLayerRef = useRef<{ id: string; ox: number; oy: number } | null>(null);

  // --- 3. 3D Mannequin Stage Previz state ---
  const stageCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [camYaw, setCamYaw] = useState(22);
  const [camPitch, setCamPitch] = useState(14);
  const [camDist, setCamDist] = useState(4.8);
  const [camFov, setCamFov] = useState(50);
  const [objs, setObjs] = useState<Stage3DObject[]>(() => {
    const chars = shotPlan?.characters?.length ? shotPlan.characters : ["Subject"];
    return chars.map((c, idx) => ({
      id: `obj-${idx + 1}`,
      label: c,
      kind: "character",
      x: (idx - (chars.length - 1) / 2) * 1.1,
      y: 0,
      z: 0,
      w: 0.85,
      h: 1.75,
      d: 0.55,
      color: idx === 0 ? "#6366f1" : idx === 1 ? "#ec4899" : "#10b981",
      posePreset: "stand",
      pose: { ...POSE_PRESETS.stand.pose },
    }));
  });
  const [selObjId, setSelObjId] = useState<string>("obj-1");
  const orbitRef = useRef<{ startX: number; startY: number; yaw: number; pitch: number } | null>(null);

  useEffect(() => {
    if (!kf?.first) {
      bgImgRef.current = null;
      return;
    }
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      bgImgRef.current = img;
    };
    img.src = F(kf.first);
  }, [kf?.first]);

  useEffect(() => {
    const cv = maskCanvasRef.current;
    if (!cv) return;
    cv.getContext("2d")?.clearRect(0, 0, CW, CH);
  }, [CW, CH]);

  // Render 2D compose canvas
  useEffect(() => {
    const cv = compCanvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#181820";
    ctx.fillRect(0, 0, CW, CH);
    if (bgImgRef.current) {
      ctx.globalAlpha = 0.45;
      ctx.drawImage(bgImgRef.current, 0, 0, CW, CH);
      ctx.globalAlpha = 1.0;
    }
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 3; i++) {
      ctx.beginPath();
      ctx.moveTo((CW * i) / 3, 0);
      ctx.lineTo((CW * i) / 3, CH);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, (CH * i) / 3);
      ctx.lineTo(CW, (CH * i) / 3);
      ctx.stroke();
    }
    for (const l of layers) {
      const w = l.img.width * l.scale;
      const h = l.img.height * l.scale;
      ctx.drawImage(l.img, l.x - w / 2, l.y - h / 2, w, h);
      if (l.id === selLayerId) {
        ctx.strokeStyle = "#6366f1";
        ctx.lineWidth = 2;
        ctx.strokeRect(l.x - w / 2, l.y - h / 2, w, h);
      }
    }
  }, [layers, selLayerId, CW, CH, tab]);

  // Render 3D Mannequin Stage Previz canvas
  useEffect(() => {
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
    const target: Vec3 = [0, 0.9, 0];

    const cx = target[0] + dist * Math.cos(pitch) * Math.sin(yaw);
    const cy = target[1] + dist * Math.sin(pitch);
    const cz = target[2] + dist * Math.cos(pitch) * Math.cos(yaw);

    let fx = target[0] - cx;
    let fy = target[1] - cy;
    let fz = target[2] - cz;
    const fl = Math.hypot(fx, fy, fz) || 1;
    fx /= fl;
    fy /= fl;
    fz /= fl;

    let rx = -fz;
    const ry = 0;
    let rz = fx;
    const rl = Math.hypot(rx, rz) || 1;
    rx /= rl;
    rz /= rl;

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

    ctx.fillStyle = "#14161d";
    ctx.fillRect(0, 0, W, H);

    // Floor grid
    ctx.strokeStyle = "rgba(110, 125, 160, 0.35)";
    ctx.lineWidth = 1;
    for (let g = -4; g <= 4; g++) {
      const p1 = project([g, 0, -4]);
      const p2 = project([g, 0, 4]);
      if (p1 && p2) {
        ctx.beginPath();
        ctx.moveTo(p1[0], p1[1]);
        ctx.lineTo(p2[0], p2[1]);
        ctx.stroke();
      }
      const q1 = project([-4, 0, g]);
      const q2 = project([4, 0, g]);
      if (q1 && q2) {
        ctx.beginPath();
        ctx.moveTo(q1[0], q1[1]);
        ctx.lineTo(q2[0], q2[1]);
        ctx.stroke();
      }
    }

    const hexToRgb = (hex: string): [number, number, number] => {
      const c = hex.replace("#", "");
      if (c.length !== 6) return [99, 102, 241];
      return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
    };

    const drawOps: { z: number; draw: () => void }[] = [];

    for (const obj of objs) {
      const [r, g, b] = hexToRgb(obj.color);
      const isSel = obj.id === selObjId;

      if (obj.kind === "character") {
        const joints = computeMannequinJoints(obj);
        const pj: Record<string, Vec3> = {};
        let skip = false;
        for (const [k, v] of Object.entries(joints)) {
          const pr = project(v);
          if (!pr) {
            skip = true;
            break;
          }
          pj[k] = pr;
        }
        if (skip) continue;

        const limbs: [string, string, number, number][] = [
          ["pelvis", "chest", 0.115, 1.0],
          ["chest", "neck", 0.055, 0.95],
          ["lShoulder", "rShoulder", 0.06, 0.95],
          ["lHip", "rHip", 0.06, 0.9],
          ["lShoulder", "lElbow", 0.052, 0.92],
          ["lElbow", "lHand", 0.044, 1.05],
          ["rShoulder", "rElbow", 0.052, 0.92],
          ["rElbow", "rHand", 0.044, 1.05],
          ["lHip", "lKnee", 0.064, 0.85],
          ["lKnee", "lAnkle", 0.052, 0.95],
          ["rHip", "rKnee", 0.064, 0.85],
          ["rKnee", "rAnkle", 0.052, 0.95],
        ];
        for (const [a, bk, radM, shade] of limbs) {
          const pa = pj[a];
          const pb = pj[bk];
          const avgZ = (pa[2] + pb[2]) * 0.5;
          const wPx = Math.max(4, ((radM * 2) / avgZ) * focal);
          const rr = Math.min(255, Math.round(r * shade));
          const gg = Math.min(255, Math.round(g * shade));
          const bb = Math.min(255, Math.round(b * shade));
          drawOps.push({
            z: avgZ,
            draw: () => {
              ctx.strokeStyle = `rgba(${rr},${gg},${bb},0.94)`;
              ctx.lineWidth = wPx;
              ctx.lineCap = "round";
              ctx.beginPath();
              ctx.moveTo(pa[0], pa[1]);
              ctx.lineTo(pb[0], pb[1]);
              ctx.stroke();
            },
          });
        }

        for (const [k, pt] of Object.entries(pj)) {
          const radM = k === "head" ? 0.125 : k === "chest" || k === "pelvis" ? 0.088 : 0.05;
          const rPx = Math.max(3, (radM / pt[2]) * focal);
          const isCore = k === "head" || k === "chest" || k === "pelvis";
          drawOps.push({
            z: pt[2] - 0.02,
            draw: () => {
              ctx.beginPath();
              ctx.arc(pt[0], pt[1], rPx, 0, Math.PI * 2);
              ctx.fillStyle = isCore ? `rgb(${r},${g},${b})` : "#f4f6ff";
              ctx.fill();
              ctx.strokeStyle = isSel ? "#ffffff" : `rgb(${r},${g},${b})`;
              ctx.lineWidth = isSel ? 2 : 1.2;
              ctx.stroke();
            },
          });
        }
      } else {
        const ow = obj.w * 0.5;
        const oh = obj.h;
        const od = obj.d * 0.5;
        const verts: Vec3[] = [
          [obj.x - ow, obj.y, obj.z - od],
          [obj.x + ow, obj.y, obj.z - od],
          [obj.x + ow, obj.y + oh, obj.z - od],
          [obj.x - ow, obj.y + oh, obj.z - od],
          [obj.x - ow, obj.y, obj.z + od],
          [obj.x + ow, obj.y, obj.z + od],
          [obj.x + ow, obj.y + oh, obj.z + od],
          [obj.x - ow, obj.y + oh, obj.z + od],
        ];
        const pverts = verts.map(project);
        if (pverts.some((v) => v === null)) continue;
        const pv = pverts as Vec3[];
        const quads: [number[], number][] = [
          [[4, 5, 6, 7], 1.0],
          [[0, 1, 2, 3], 0.65],
          [[0, 4, 7, 3], 0.8],
          [[1, 5, 6, 2], 0.85],
          [[3, 2, 6, 7], 1.15],
        ];
        for (const [idxs, shade] of quads) {
          const pts = idxs.map((i) => [pv[i][0], pv[i][1]] as [number, number]);
          const avgZ = idxs.reduce((acc, i) => acc + pv[i][2], 0) / 4;
          const rr = Math.min(255, Math.round(r * shade));
          const gg = Math.min(255, Math.round(g * shade));
          const bb = Math.min(255, Math.round(b * shade));
          drawOps.push({
            z: avgZ,
            draw: () => {
              ctx.beginPath();
              ctx.moveTo(pts[0][0], pts[0][1]);
              for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
              ctx.closePath();
              ctx.fillStyle = `rgba(${rr},${gg},${bb},0.84)`;
              ctx.fill();
              ctx.strokeStyle = isSel ? "#ffffff" : `rgb(${r},${g},${b})`;
              ctx.lineWidth = 1.5;
              ctx.stroke();
            },
          });
        }
      }
    }

    drawOps.sort((a, b) => b.z - a.z);
    for (const op of drawOps) op.draw();

    ctx.font = "600 12px Pretendard, sans-serif";
    ctx.textAlign = "center";
    for (const obj of objs) {
      const top = project([obj.x, obj.y + obj.h + 0.18, obj.z]);
      if (top) {
        ctx.fillStyle = "#ffffff";
        ctx.fillText(obj.label, top[0], top[1]);
      }
    }
  }, [camYaw, camPitch, camDist, camFov, objs, selObjId, CW, CH, tab]);

  const paintMaskAt = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const cv = maskCanvasRef.current;
    if (!cv) return;
    const rect = cv.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * CW;
    const y = ((e.clientY - rect.top) / rect.height) * CH;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.save();
    if (eraser) {
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,1)";
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "rgba(255, 70, 90, 0.75)";
    }
    ctx.beginPath();
    ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  };

  const addCharacterLayer = (label: string, url: string) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const scale = Math.min((CW * 0.55) / img.width, (CH * 0.55) / img.height);
      const lid = `layer-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setLayers((prev) => [...prev, { id: lid, label, url, img, x: CW / 2, y: CH / 2, scale }]);
      setSelLayerId(lid);
    };
    img.src = url;
  };

  const handleSaveAndGenerate = async (runMake: boolean) => {
    setSaving(true);
    try {
      if (tab === "mask") {
        const srcCv = maskCanvasRef.current;
        if (!srcCv) return;
        const outCv = document.createElement("canvas");
        outCv.width = CW;
        outCv.height = CH;
        const octx = outCv.getContext("2d")!;
        octx.fillStyle = "#000000";
        octx.fillRect(0, 0, CW, CH);
        const srcData = srcCv.getContext("2d")!.getImageData(0, 0, CW, CH);
        const outData = octx.getImageData(0, 0, CW, CH);
        for (let i = 0; i < srcData.data.length; i += 4) {
          if (srcData.data[i + 3] > 20) {
            outData.data[i] = 255;
            outData.data[i + 1] = 255;
            outData.data[i + 2] = 255;
            outData.data[i + 3] = 255;
          }
        }
        octx.putImageData(outData, 0, 0);
        await api.keyframeGuideSave(id, shot, {
          kind: "mask",
          dataUrl: outCv.toDataURL("image/png"),
          note,
        });
      } else if (tab === "compose") {
        const cv = compCanvasRef.current;
        if (!cv) return;
        await api.keyframeGuideSave(id, shot, {
          kind: "compose",
          dataUrl: cv.toDataURL("image/png"),
          note,
        });
      } else {
        await api.keyframeGuideSave(id, shot, {
          kind: "stage",
          spec: {
            camera: { yaw: camYaw, pitch: camPitch, dist: camDist, fov: camFov, target: [0, 0.9, 0] },
            objects: objs,
          },
          note,
        });
      }

      if (runMake) {
        await api.pipelineAct(id, "keyframe", "make", { shots: String(shot) });
        toast.success(t("가이드를 저장하고 샷 #{n} 키 프레임 생성을 시작했습니다", { n: shot }));
        onUpdated();
        onClose();
      } else {
        toast.success(t("샷 #{n} 가이드를 저장했습니다", { n: shot }));
        onUpdated();
      }
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const handleClearGuides = async () => {
    try {
      await api.keyframeGuideClear(id, shot, "all");
      toast.success(t("샷 #{n} 가이드를 지웠습니다", { n: shot }));
      onUpdated();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const selectedObj = objs.find((o) => o.id === selObjId) ?? objs[0] ?? null;
  const selectedPose = selectedObj?.pose ?? POSE_PRESETS.stand.pose;
  const selectedLayer = layers.find((l) => l.id === selLayerId) ?? null;

  const updateSelectedPose = (patch: Partial<MannequinPose>, preset?: PosePresetKey) => {
    if (!selectedObj) return;
    setObjs((prev) =>
      prev.map((o) =>
        o.id === selectedObj.id
          ? {
              ...o,
              posePreset: preset ?? o.posePreset,
              pose: { ...(o.pose ?? POSE_PRESETS.stand.pose), ...patch },
            }
          : o,
      ),
    );
  };

  return (
    <RDialog.Root open onOpenChange={(v) => !v && onClose()}>
      <RDialog.Portal>
        <RDialog.Overlay className="lb-overlay" style={{ zIndex: 1000 }} />
        <RDialog.Content
          className="pgx-studio-modal"
          style={{
            position: "fixed",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            zIndex: 1001,
            width: "min(980px, 96vw)",
            maxHeight: "92vh",
            background: "#16161d",
            border: "1px solid #2b2b36",
            borderRadius: 12,
            display: "flex",
            flexDirection: "column",
            color: "#eee",
            overflow: "hidden",
            boxShadow: "0 24px 64px rgba(0,0,0,0.7)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: "1px solid #262630" }}>
            <RDialog.Title style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>
              {t("샷 #{n} 구도 · 마네킹 포즈 · 마스크 스튜디오", { n: shot })}
            </RDialog.Title>
            <span style={{ fontSize: 12, color: "#999" }}>{shotPlan?.purpose}</span>
            <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
              {([
                ["mask", "2D 마스크 인페인팅"],
                ["compose", "2D 레이어 배치"],
                ["stage", "3D 마네킹 포즈 · 카메라"],
              ] as const).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setTab(k)}
                  className={`pgx-btn is-xs ${tab === k ? "is-primary" : ""}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <button type="button" className="pgx-x" onClick={onClose} aria-label={t("닫기")}>✕</button>
          </div>

          <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "auto", padding: 16, gap: 18, flexWrap: "wrap" }}>
            {/* Left Viewport */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              {tab === "mask" && (
                <div
                  style={{
                    position: "relative",
                    width: CW,
                    height: CH,
                    borderRadius: 8,
                    overflow: "hidden",
                    border: "1px solid #30303c",
                    background: "#101016",
                  }}
                >
                  {kf?.first && (
                    <img
                      src={F(kf.first)}
                      alt=""
                      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", pointerEvents: "none" }}
                    />
                  )}
                  <canvas
                    ref={maskCanvasRef}
                    width={CW}
                    height={CH}
                    style={{ position: "relative", width: CW, height: CH, cursor: "crosshair" }}
                    onMouseDown={(e) => {
                      drawingRef.current = true;
                      paintMaskAt(e);
                    }}
                    onMouseMove={(e) => {
                      if (drawingRef.current) paintMaskAt(e);
                    }}
                    onMouseUp={() => {
                      drawingRef.current = false;
                    }}
                    onMouseLeave={() => {
                      drawingRef.current = false;
                    }}
                  />
                </div>
              )}

              {tab === "compose" && (
                <canvas
                  ref={compCanvasRef}
                  width={CW}
                  height={CH}
                  style={{ width: CW, height: CH, borderRadius: 8, border: "1px solid #30303c", cursor: "move" }}
                  onMouseDown={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const mx = ((e.clientX - rect.left) / rect.width) * CW;
                    const my = ((e.clientY - rect.top) / rect.height) * CH;
                    for (let i = layers.length - 1; i >= 0; i--) {
                      const l = layers[i];
                      const w = l.img.width * l.scale;
                      const h = l.img.height * l.scale;
                      if (mx >= l.x - w / 2 && mx <= l.x + w / 2 && my >= l.y - h / 2 && my <= l.y + h / 2) {
                        setSelLayerId(l.id);
                        dragLayerRef.current = { id: l.id, ox: mx - l.x, oy: my - l.y };
                        return;
                      }
                    }
                  }}
                  onMouseMove={(e) => {
                    const dr = dragLayerRef.current;
                    if (!dr) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    const mx = ((e.clientX - rect.left) / rect.width) * CW;
                    const my = ((e.clientY - rect.top) / rect.height) * CH;
                    setLayers((prev) =>
                      prev.map((l) => (l.id === dr.id ? { ...l, x: mx - dr.ox, y: my - dr.oy } : l)),
                    );
                  }}
                  onMouseUp={() => {
                    dragLayerRef.current = null;
                  }}
                />
              )}

              {tab === "stage" && (
                <canvas
                  ref={stageCanvasRef}
                  width={CW}
                  height={CH}
                  style={{ width: CW, height: CH, borderRadius: 8, border: "1px solid #30303c", cursor: "grab" }}
                  onMouseDown={(e) => {
                    orbitRef.current = { startX: e.clientX, startY: e.clientY, yaw: camYaw, pitch: camPitch };
                  }}
                  onMouseMove={(e) => {
                    const ob = orbitRef.current;
                    if (!ob) return;
                    const dx = e.clientX - ob.startX;
                    const dy = e.clientY - ob.startY;
                    setCamYaw(Math.round(ob.yaw - dx * 0.45));
                    setCamPitch(Math.max(-15, Math.min(75, Math.round(ob.pitch + dy * 0.35))));
                  }}
                  onMouseUp={() => {
                    orbitRef.current = null;
                  }}
                  onWheel={(e) => {
                    e.preventDefault();
                    setCamDist((d) => Math.max(2.0, Math.min(14, Number((d + e.deltaY * 0.005).toFixed(2)))));
                  }}
                />
              )}
            </div>

            {/* Right Controls */}
            <div style={{ flex: 1, minWidth: 300, display: "flex", flexDirection: "column", gap: 11 }}>
              {tab === "mask" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <p style={{ margin: 0, fontSize: 12.5, color: "#aaa" }}>
                    키 프레임에서 바꿀 영역을 브러시로 칠한 뒤 고칠 내용을 적으면, 칠하지 않은 부분은 그대로 유지하고 칠한 영역만 재생성합니다.
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button type="button" className={`pgx-btn is-xs ${!eraser ? "is-primary" : ""}`} onClick={() => setEraser(false)}>
                      칠하기 (수정 영역)
                    </button>
                    <button type="button" className={`pgx-btn is-xs ${eraser ? "is-primary" : ""}`} onClick={() => setEraser(true)}>
                      지우개
                    </button>
                    <button
                      type="button"
                      className="pgx-btn is-xs"
                      onClick={() => {
                        const cv = maskCanvasRef.current;
                        cv?.getContext("2d")?.clearRect(0, 0, CW, CH);
                      }}
                    >
                      전체 지우기
                    </button>
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                    <span>브러시 크기 ({brushSize}px)</span>
                    <input type="range" min={8} max={80} value={brushSize} onChange={(e) => setBrushSize(Number(e.target.value))} />
                  </label>
                </div>
              )}

              {tab === "compose" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <p style={{ margin: 0, fontSize: 12.5, color: "#aaa" }}>
                    승인된 캐릭터 시트를 캔버스에 올려 원하는 위치 · 크기로 배치하면 그 구도 그대로 키 프레임을 생성합니다.
                  </p>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {pipeline.characters.map((c) =>
                      Object.entries(c.files || {}).map(([view, fileRel]) => (
                        <button
                          key={`${c.name}-${view}`}
                          type="button"
                          className="pgx-btn is-xs"
                          onClick={() => addCharacterLayer(`${c.name}(${view})`, F(fileRel))}
                        >
                          + {c.name} ({view})
                        </button>
                      )),
                    )}
                  </div>
                  {selectedLayer && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                      <span>선택 레이어 크기 ({Math.round(selectedLayer.scale * 100)}%)</span>
                      <input
                        type="range"
                        min={15}
                        max={200}
                        value={Math.round(selectedLayer.scale * 100)}
                        onChange={(e) => {
                          const s = Number(e.target.value) / 100;
                          setLayers((prev) => prev.map((l) => (l.id === selectedLayer.id ? { ...l, scale: s } : l)));
                        }}
                      />
                      <button
                        type="button"
                        className="pgx-btn is-xs"
                        onClick={() => setLayers((prev) => prev.filter((l) => l.id !== selectedLayer.id))}
                      >
                        삭제
                      </button>
                    </div>
                  )}
                </div>
              )}

              {tab === "stage" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 12, color: "#aaa" }}>
                      뷰포트를 드래그해 카메라 회전, 아래에서 마네킹 포즈와 관절 각도를 조절하세요.
                    </span>
                  </div>

                  {/* Camera Sliders */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11.5, background: "#1b1b24", padding: 8, borderRadius: 6 }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>카메라 회전 Yaw ({camYaw}°)</span>
                      <input type="range" min={-180} max={180} value={camYaw} onChange={(e) => setCamYaw(Number(e.target.value))} />
                    </label>
                    <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>카메라 앵글 Pitch ({camPitch}°)</span>
                      <input type="range" min={-15} max={75} value={camPitch} onChange={(e) => setCamPitch(Number(e.target.value))} />
                    </label>
                    <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>카메라 거리 ({camDist}m)</span>
                      <input type="range" min={2.0} max={12} step={0.2} value={camDist} onChange={(e) => setCamDist(Number(e.target.value))} />
                    </label>
                    <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>렌즈 화각 FOV ({camFov}°)</span>
                      <input type="range" min={25} max={90} value={camFov} onChange={(e) => setCamFov(Number(e.target.value))} />
                    </label>
                  </div>

                  {/* Object Selector */}
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
                    {objs.map((o) => (
                      <button
                        key={o.id}
                        type="button"
                        className={`pgx-btn is-xs ${o.id === selObjId ? "is-primary" : ""}`}
                        onClick={() => setSelObjId(o.id)}
                      >
                        {o.kind === "character" ? `🧍 ${o.label}` : `📦 ${o.label}`}
                      </button>
                    ))}
                    <button
                      type="button"
                      className="pgx-btn is-xs"
                      onClick={() => {
                        const nid = `obj-${objs.length + 1}`;
                        setObjs((prev) => [
                          ...prev,
                          {
                            id: nid,
                            label: `Mannequin${objs.length + 1}`,
                            kind: "character",
                            x: 0.9,
                            y: 0,
                            z: -0.3,
                            w: 0.85,
                            h: 1.75,
                            d: 0.55,
                            color: "#ec4899",
                            posePreset: "stand",
                            pose: { ...POSE_PRESETS.stand.pose },
                          },
                        ]);
                        setSelObjId(nid);
                      }}
                    >
                      + 마네킹 추가
                    </button>
                    <button
                      type="button"
                      className="pgx-btn is-xs"
                      onClick={() => {
                        const nid = `obj-${objs.length + 1}`;
                        setObjs((prev) => [
                          ...prev,
                          { id: nid, label: `Prop${objs.length + 1}`, kind: "prop", x: 0.7, y: 0, z: 0.5, w: 0.7, h: 0.8, d: 0.7, color: "#f59e0b" },
                        ]);
                        setSelObjId(nid);
                      }}
                    >
                      + 소품 블록
                    </button>
                  </div>

                  {/* Selected Object Position */}
                  {selectedObj && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: 11.5, background: "#1b1b24", padding: 8, borderRadius: 6 }}>
                      <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span>위치 X ({selectedObj.x}m)</span>
                        <input
                          type="range"
                          min={-2.5}
                          max={2.5}
                          step={0.1}
                          value={selectedObj.x}
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            setObjs((prev) => prev.map((o) => (o.id === selectedObj.id ? { ...o, x: v } : o)));
                          }}
                        />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span>높이 Y ({selectedObj.y}m)</span>
                        <input
                          type="range"
                          min={0}
                          max={2}
                          step={0.1}
                          value={selectedObj.y}
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            setObjs((prev) => prev.map((o) => (o.id === selectedObj.id ? { ...o, y: v } : o)));
                          }}
                        />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span>깊이 Z ({selectedObj.z}m)</span>
                        <input
                          type="range"
                          min={-2.5}
                          max={2.5}
                          step={0.1}
                          value={selectedObj.z}
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            setObjs((prev) => prev.map((o) => (o.id === selectedObj.id ? { ...o, z: v } : o)));
                          }}
                        />
                      </label>
                    </div>
                  )}

                  {/* Mannequin Pose Presets & Joint Articulation Sliders */}
                  {selectedObj?.kind === "character" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, background: "#1e1e29", padding: 10, borderRadius: 8, border: "1px solid #2d2d3d" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <b style={{ fontSize: 12 }}>마네킹 포즈 프리셋 ({selectedObj.label})</b>
                      </div>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {(Object.entries(POSE_PRESETS) as [PosePresetKey, { label: string; pose: MannequinPose }][]).map(([key, pr]) => (
                          <button
                            key={key}
                            type="button"
                            className={`pgx-btn is-xs ${selectedObj.posePreset === key ? "is-primary" : ""}`}
                            onClick={() => updateSelectedPose({ ...pr.pose }, key)}
                          >
                            {pr.label}
                          </button>
                        ))}
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>몸통 회전 ({selectedPose.bodyYaw}°)</span>
                          <input type="range" min={-180} max={180} value={selectedPose.bodyYaw} onChange={(e) => updateSelectedPose({ bodyYaw: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>상체 숙이기 ({selectedPose.torsoLean}°)</span>
                          <input type="range" min={-35} max={55} value={selectedPose.torsoLean} onChange={(e) => updateSelectedPose({ torsoLean: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>고개 좌우 ({selectedPose.headYaw}°)</span>
                          <input type="range" min={-65} max={65} value={selectedPose.headYaw} onChange={(e) => updateSelectedPose({ headYaw: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>고개 상하 ({selectedPose.headPitch}°)</span>
                          <input type="range" min={-40} max={45} value={selectedPose.headPitch} onChange={(e) => updateSelectedPose({ headPitch: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>오른팔 들기 ({selectedPose.rShoulderPitch}°)</span>
                          <input type="range" min={-60} max={175} value={selectedPose.rShoulderPitch} onChange={(e) => updateSelectedPose({ rShoulderPitch: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>오른팔꿈치 굽힘 ({selectedPose.rElbowBend}°)</span>
                          <input type="range" min={0} max={140} value={selectedPose.rElbowBend} onChange={(e) => updateSelectedPose({ rElbowBend: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>왼팔 들기 ({selectedPose.lShoulderPitch}°)</span>
                          <input type="range" min={-60} max={175} value={selectedPose.lShoulderPitch} onChange={(e) => updateSelectedPose({ lShoulderPitch: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>왼팔꿈치 굽힘 ({selectedPose.lElbowBend}°)</span>
                          <input type="range" min={0} max={140} value={selectedPose.lElbowBend} onChange={(e) => updateSelectedPose({ lElbowBend: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>오른다리 앞뒤 ({selectedPose.rHipPitch}°)</span>
                          <input type="range" min={-60} max={110} value={selectedPose.rHipPitch} onChange={(e) => updateSelectedPose({ rHipPitch: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>오른무릎 굽힘 ({selectedPose.rKneeBend}°)</span>
                          <input type="range" min={0} max={130} value={selectedPose.rKneeBend} onChange={(e) => updateSelectedPose({ rKneeBend: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>왼다리 앞뒤 ({selectedPose.lHipPitch}°)</span>
                          <input type="range" min={-60} max={110} value={selectedPose.lHipPitch} onChange={(e) => updateSelectedPose({ lHipPitch: Number(e.target.value) })} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                          <span>왼무릎 굽힘 ({selectedPose.lKneeBend}°)</span>
                          <input type="range" min={0} max={130} value={selectedPose.lKneeBend} onChange={(e) => updateSelectedPose({ lKneeBend: Number(e.target.value) })} />
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, marginTop: "auto" }}>
                <span>구도 · 수정 지시 노트 (영문 권장, keyframe_note 로 반영)</span>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="예: Follow the 3D mannequin pose strictly; right hand waving toward the camera"
                  style={{
                    height: 30,
                    padding: "0 10px",
                    borderRadius: 6,
                    border: "1px solid #323240",
                    background: "#101016",
                    color: "#eee",
                    fontSize: 12.5,
                  }}
                />
              </label>

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 6, borderTop: "1px solid #262630" }}>
                {(kf?.has_mask || kf?.has_compose || kf?.has_stage) && (
                  <button type="button" className="pgx-btn" disabled={saving} onClick={handleClearGuides}>
                    기존 가이드 지우기
                  </button>
                )}
                <button type="button" className="pgx-btn" disabled={saving} onClick={() => handleSaveAndGenerate(false)}>
                  가이드만 저장
                </button>
                <button type="button" className="pgx-btn is-primary" disabled={saving} onClick={() => handleSaveAndGenerate(true)}>
                  {saving ? "저장 중…" : "가이드 저장 및 이 샷 재생성"}
                </button>
              </div>
            </div>
          </div>
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
};
