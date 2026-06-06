/* sim_parity_runner.mjs — frontend/sim-engine.js 를 Node 에서 구동해 파이썬
 * 시뮬레이터와 비교 가능한 트레이스를 stdout(JSON)으로 낸다.
 *
 * stdin JSON: {stCode, timeline:[[t,{sym:bool}]], duration, step}
 * stdout JSON: {inputs, outputs, samples:[{t_ms, outputs:{...}}]}
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "frontend", "sim-engine.js"), "utf8");

const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const SimEngine = sandbox.window.SimEngine;

const input = readFileSync(0, "utf8");
const { stCode, timeline, duration, step } = JSON.parse(input);
const res = SimEngine.simulate(stCode, timeline, duration, step);
process.stdout.write(JSON.stringify(res));
