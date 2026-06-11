# Natural-Language → *Formally-Verified* PLC Control
### Executive Brief · Research Preview

**Korean plain text → IEC 61131-3 ladder logic, with machine-checked safety proofs.**
No LLM, no API key in the core path — 100% deterministic. Every number below reproduces
via `python scripts/capability_report.py`.

---

## The problem
Control engineers are scarce; a single wrong rung (duplicate coil, simultaneous
forward/reverse, simultaneous star–delta) means a burned motor, a phase-to-phase short,
or a machine crash. LLMs hallucinate, so "natural language → machine" is meaningless
unless correctness can be **proven**.

## The bet — *the verifier is the moat*
Generators all improve over time (templates → our Korean engine → LLMs). The defensible
asset is a fast, general **verify + repair + honest-refusal** loop that proves safety of
*whatever* is generated. As models get stronger, the value of this safety gate grows.

## What it does (one Korean line → …)
1. **Understand** — deterministic Hangul morphology (jamo arithmetic, particles, verb
   conjugation) → intent frame. No keyword matching, no LLM.
2. **Compile** — intent → verifiable state-machine spec → IEC 61131-3 Structured Text.
3. **Guarantee** — Z3 k-induction proves interlocks / one-hot mutual exclusion; broken
   programs are soundly repaired; out-of-scope requests are **refused, not faked**.
4. **Deliver** — ladder JSON, **PLCopen XML** (OpenPLC/CODESYS import), vendor **IL**,
   P&ID drawing, control-panel single-line diagram, 3D digital-twin run, precision tests.

## Proven standard circuits (each from one sentence)
| Circuit | Proven safety property |
|---|---|
| Star–Delta (Y-Δ) start | **MC-Y ⊥ MC-Δ** never simultaneously closed (no phase short) + open-transition dead-time; breaker/contactor/EOCR auto-sized (380 V IE3 table + `I=P/(√3·V·cosφ·η)`) |
| Forward/Reverse | **FWD ⊥ REV** proven (no reverse-phase short) |
| Pump duty alternation | **#1 ⊥ #2** proven, alternates each start |
| Sequencer | step outputs **one-hot** proven (≤1 active) |
| Emergency stop | every output gated `AND NOT ESTOP`; all outputs 0 while pressed (by construction + sim) |
| Conveyor cascade | **containment □(upstream→downstream) proven** (new property class; jam prevention) |
| Two-hand start | 0.5 s concurrency window, non-simultaneous lockout (5 simulated safety behaviors) |
| Interlock / hysteresis / counter | mutual-exclusion proven / chatter-free band / preset trip |

## Evidence (reproducible)
- Korean understanding (common single-intent): **84%**, **0% silent failure** (refuses instead of mis-mapping).
- Adversarial bench **110 cases** (PID/servo/comms traps): confident set all verify, double-coil 0; out-of-scope **100% refused**; **silent failure 0**.
- Verifier soundness: **false-proof 0 · miss 0**.
- Cross-backend equivalence PySim ↔ XGK IL ↔ OpenPLC twin: **100%** trace match.
- Auto-repair of faulted programs: **100%**. Regression suite: **1,320 tests, all green**.
- Vendor error-code knowledge base: **101 entries** (LS · Mitsubishi · Siemens · Omron) with cited sources.

**Headline: "Zero silent failure — refuse what you don't know, prove what you build."**

## Honest limits
Research preview, no traction yet. Scope: boolean / sequence / basic analog compare /
standard motor-start circuits. **Refuses PID, motion/servo, fieldbus comms, HMI,
large-scale DCS.** Verification centers on interlock/sequence mutual exclusion; quantitative
timing & analog dynamics are in progress. Safety certification (TÜV/SIL) and on-hardware
production are out of scope (require an organization).

## Try it now
Browser-only (the real Python engine runs in WebAssembly, no server):
`https://raw.githack.com/baesy2/ld/claude/nlang-plc-design-8oYP1/docs/web.html`

See also: [White Paper](WHITEPAPER.md) · [User Manual](MANUAL.md) ·
[Error-Code Handbook](ERRORCODES.md).
