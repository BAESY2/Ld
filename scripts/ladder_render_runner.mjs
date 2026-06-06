/* ladder_render_runner.mjs — frontend/ladder-render.js 를 Node 에서 구동해
 * svg(ladder[, state]) 결과 문자열을 stdout 으로 낸다(파워플로우 색 회귀검사용).
 * stdin JSON: {ladder, state?} → stdout: SVG 문자열.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "frontend", "ladder-render.js"), "utf8");
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

const { ladder, state } = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(sandbox.window.LadderRender.svg(ladder, state));
