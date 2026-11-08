// Craft 앱 붙이기 — ArtCraft 의 오픈소스 Photoshop · Illustrator · After Effects 류 앱(engine/craft/apps/<이름>/craft.json).
//  - 설치는 engine/craft/crafts.py(릴리스 받기 · SHA256 확인 · tools/crafts/<이름>/ 에 풀기)
//  - 설치된 앱 중 '에이전트' 가 켜진 것은 에이전트 실행 때 MCP 서버로 붙는다: 읽기는 저장소, 쓰기는 data/compositions/ 만
//  - 켜고 끄기는 data/workspace/settings.json 의 crafts: { 이름: true/false } (비밀이 아니므로 설정 파일에)
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";

export function createCrafts(ROOT) {
  const REG = path.join(ROOT, "engine", "craft", "apps");
  const DEST = path.join(ROOT, "tools", "crafts");
  const settings = () => { try { return JSON.parse(readFileSync(path.join(ROOT, "data", "workspace", "settings.json"), "utf8")); } catch { return {}; } };
  const readJson = (f) => { try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; } };

  function list() {
    const on = settings().crafts ?? {};
    const names = existsSync(REG) ? readdirSync(REG).filter((n) => /^[a-z0-9-]+$/.test(n) && existsSync(path.join(REG, n, "craft.json"))) : [];
    return names.map((n) => {
      const c = readJson(path.join(REG, n, "craft.json")) ?? { name: n };
      const inst = readJson(path.join(DEST, n, "installed.json"));
      return { ...c, name: n, installed: inst ? { version: inst.version, cli: !!inst.cli, bin: !!inst.bin, web: !!inst.web } : null, agentOn: on[n] ?? !!c.agent };
    }).sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
  }
  const get = (name) => list().find((c) => c.name === name) ?? null;
  const installed = (name) => readJson(path.join(DEST, name, "installed.json"));
  const abs = (rel) => (rel ? path.join(ROOT, rel) : null);

  /** 에이전트용 MCP 서버 항목 — 설치됐고 켜진 앱만 */
  function mcpServers() {
    const out = {};
    for (const c of list()) {
      if (!c.agentOn || !c.installed?.cli) continue;
      const cli = abs(installed(c.name)?.cli); if (!cli || !existsSync(cli)) continue;
      const args = (c.mcp ?? ["mcp", "--automation-read-root", "$ROOT", "--automation-write-root", "$WRITE"])
        .map((a) => a.replace("$ROOT", ROOT).replace("$WRITE", path.join(ROOT, "data", "compositions")));
      out[c.name] = { type: "stdio", command: cli, args };
    }
    return out;
  }
  /** 데스크톱 앱 실행 파일 · 브라우저 빌드 폴더 */
  const desktop = (name) => abs(installed(name)?.bin);
  const webDir = (name) => abs(installed(name)?.web);
  return { list, get, mcpServers, desktop, webDir };
}
