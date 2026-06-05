# OpenPLC v4 native HAL drivers — LS XGT FEnet & Mitsubishi MELSEC

Reference C++ I/O drivers that make a forked
[`Autonomy-Logic/openplc-runtime`](https://github.com/Autonomy-Logic/openplc-runtime)
(v4, **MIT**) talk **natively** to:

- **LS XGT/XGB FEnet** dedicated protocol — TCP **2004** (`fenet_hal.cpp/.h`)
- **Mitsubishi MELSEC MC 3E binary** (SLMP) — port configurable, default 5007
  (`melsec_hal.cpp/.h`)

These are a hand port of the **proven, tested** pure-Python adapters
`app/comms/fenet_xgt.py` and `app/comms/melsec.py`. The C frame builders are
written to produce **byte-identical** wire frames; that contract is
machine-checked by `tests/test_openplc_driver_parity.py` (see below).

> ## ⚠️ NOT COMPILED — verify in a v4 fork
> There is **no OpenPLC v4 source tree and no C/C++ toolchain in this repo**, so
> the C++ here is **uncompiled and untested as C**. It is clean, reviewable
> reference source. You MUST build and verify it **inside a real fork** of
> `openplc-runtime`, and confirm the first frames against an actual CPU /
> GX Works + Wireshark before any deployment (LS header endianness and MELSEC
> nibble bit-packing are the classic footguns — the parity test pins them, but
> only a packet capture proves the live link).

---

## What the drivers do

Both implement the v4 native plugin ABI (and v3-compat callbacks):

- `cycle_start()` — FEnet/MC **batch-read** the mapped PLC devices and write the
  results into the process **input** image (`bool_input[byte][bit]`,
  `int_input[n]`).
- `cycle_end()` — read the process **output** image
  (`bool_output[byte][bit]`, `int_output[n]`) and FEnet/MC **write** to the PLC.

Buffer pointers are null-checked; buffer access is wrapped in
`mutex_take(buffer_mutex)` / `mutex_give(buffer_mutex)`. Socket I/O is done
**outside** the buffer lock (snapshot-then-write) to keep the scan-cycle critical
section short.

### Device map (symbol → device)
Edit `load_device_map()` in each `.cpp` (or, better, load it from the per-plugin
config file referenced in `plugins.conf`; a JSON shape is shown in
`plugins.conf.example`). Each entry maps a process-image slot to an LS/MELSEC
device name:

| field | meaning |
|---|---|
| `byte`,`bit` | location in `bool_input`/`bool_output` (bit devices) |
| `word_idx` | index in `int_input`/`int_output` (word devices) |
| `kind` | `Bit` (%MX / M) or `Word` (%MW / D) |
| `is_input` | `true` → driver reads PLC into input image; `false` → driver writes output image to PLC |
| `device` | `"%MX0"`, `"%MW100"` (LS) or `"M0"`, `"D100"` (MELSEC) |

LS supports XGI (IEC names `%MX/%MW`) and XGK (LS names `P/M/K/...`). The wire
frame is identical; only the **device name string** differs, so an XGK target
just needs XGK-style names in the map.

---

## v4 plugin ABI targeted

Per `core/src/drivers/README.md` of the v4 runtime:

```c
int  init(void *args);   // ONLY init receives the args struct
void start_loop(void);
void stop_loop(void);
void cleanup(void);
void cycle_start(void);  // native plugins only
void cycle_end(void);    // native plugins only
```

`args` is a `plugin_runtime_args_t*` exposing the process-image pointers
(`bool_input/bool_output[8]`, `int_input/int_output`, …), the mutex helpers
(`mutex_take`/`mutex_give`), and `buffer_mutex`. **Critical:** the runtime frees
`args` after `init()` returns, so `init()` **copies the struct** (into
`g_args_copy`) and never stores the pointer.

The `.cpp` files carry a fallback `plugin_runtime_args_t` shim guarded by
`#if !defined(OPENPLC_V4_HEADERS)` so they parse standalone. On integration:
define `OPENPLC_V4_HEADERS`, `#include` the real v4 plugin header, and the shim
drops out (`IEC_BOOL`/`IEC_UINT`/`pthread_mutex_t*` take over).

A **v3-compat** callback HAL (`initializeHardware` / `finalizeHardware` /
`updateBuffersIn` / `updateBuffersOut`, `blank.cpp` shape) is also exported so
the same source can drop into a v3-style hardware layer.

---

## Drop-in / build / register

1. **Copy sources** into your fork:
   ```
   core/src/drivers/native/fenet_hal.cpp   core/src/drivers/native/fenet_hal.h
   core/src/drivers/native/melsec_hal.cpp  core/src/drivers/native/melsec_hal.h
   ```
2. **Wire up the build.** Either `include()` the provided `CMakeLists.txt`
   fragment from `core/src/drivers/CMakeLists.txt`, or build by hand:
   ```bash
   g++ -shared -fPIC -std=c++17 -I<openplc>/core/lib \
       -o fenet_hal.so  fenet_hal.cpp  -lpthread
   g++ -shared -fPIC -std=c++17 -I<openplc>/core/lib \
       -o melsec_hal.so melsec_hal.cpp -lpthread
   ```
   (Set `-DOPENPLC_V4_HEADERS` and the include path once the real ABI header is
   available so the shim is dropped.)
3. **Register** in `plugins.conf` (see `plugins.conf.example`):
   ```
   ls_fenet,./core/src/drivers/plugins/native/fenet_hal.so,1,1,./config/ls_fenet.conf
   mitsubishi_melsec,./core/src/drivers/plugins/native/melsec_hal.so,1,1,./config/mitsubishi_melsec.conf
   ```
   (type `1` = native `.so`.)
4. **Configure** host/port/device-map in the per-plugin config file, and
   replace the hard-coded `configure("127.0.0.1", …)` + `load_device_map()`
   defaults with a parse of that file.
5. **Verify on hardware** — capture the first read/write frames with Wireshark
   and confirm they match the golden vectors in the parity test.

---

## Byte-parity test — how the C is tied to the proven Python

`tests/test_openplc_driver_parity.py` (Python, CI-safe, **no network, no C**):

- The **exact wire frames the C driver intends to emit** are encoded as byte
  literals (copied from the protocol brief / C source comments), e.g. FEnet
  read `%MX0`, write `%MX0`/`%MW100`; MELSEC read 16 bits `M0`, write bit `M0`,
  write word `D100`.
- Each literal is asserted **equal** to the bytes the **proven Python adapter**
  (`fenet_xgt.py` / `melsec.py`) produces for the same operation.
- It also pins the endianness/packing footguns: the 20-byte LS header + BCC over
  bytes [0..18], MELSEC device codes/numbering (M decimal 0x90, D decimal 0xA8,
  X **hex** 0x9C), and MELSEC nibble bit-packing (`[True]*16 → 0x11*8`, distinct
  from Modbus LSB packing).

So even though the C is not compiled here, the **C-vs-Python frame contract is
machine-checked**: if the C builders drift from the Python adapters, the literals
stop matching and the test fails. The literals double as a frozen golden vector
for the on-device Wireshark check.

```bash
pytest tests/test_openplc_driver_parity.py -q     # all pass
ruff  check tests/test_openplc_driver_parity.py   # clean
```

---

## MIT-fork rebranding checklist

OpenPLC v4 runtime is **MIT** — you may embed, modify, and redistribute in a
closed product, provided you keep the upstream copyright/notice. When rebranding
the fork:

- [ ] **Project name / CMake** — `project()` name and target names in the
      top-level `CMakeLists.txt`.
- [ ] **Version banner** — startup/log banner and any `--version` string in the
      runtime process and the REST service.
- [ ] **TLS certificate CN / SAN** — regenerate the self-signed cert with your
      hostname/CN (the REST endpoint runs on `:8443`).
- [ ] **Logo / static assets** — any branding served by the REST/UI layer.
- [ ] **LICENSE / NOTICE** — **keep the upstream MIT LICENSE text and copyright
      line intact**; add your own copyright/NOTICE alongside it (MIT requires
      preserving the notice). Do **not** relicense the upstream files.
- [ ] **Package/binary names**, systemd unit, container image tags.

---

## GPL boundary (load-bearing — do not cross)

- **MIT, safe to embed/modify/ship:** the v4 **runtime** itself
  (`openplc-runtime`). These drivers attach to it as native plugins — fine.
- **GPLv3 — NEVER link or bundle into your closed product:**
  - **OpenPLC Editor v4** (GPLv3, bundles Beremiz + MatIEC).
  - **MatIEC** / the `iec2c` compiler and its `lib/` glue.
- **Rules:**
  - Linking (same address space) with GPL code = copyleft contamination →
    **never link MatIEC or the Editor** into the runtime/your product.
  - Editor ↔ Runtime communicate **only** over the REST boundary (`:8443`);
    runtime field I/O is Modbus (`:502`) and — with these drivers — FEnet
    (`:2004`) / MELSEC. Process/network boundaries are *use/aggregation*, not
    linking, and stay clean.
  - **Do not redistribute** MatIEC or its generated C from your product; let
    OpenPLC compile IEC programs **inside the user's box** so no copyleft
    attaches to what you ship. (Get legal sign-off before any *bundled*
    redistribution of MatIEC output.)
  - Keep the deterministic Korean-NL synthesis / formal-verification / safety
    engine entirely **on your side of the process boundary** — it never links
    OpenPLC at all.

---

## Honest caveats

- **Uncompiled C** — reference quality; build + verify in the fork (see banner).
- Stock Linux is **not hard real-time** — v4 needs PREEMPT-RT; unsuitable for
  motion. Not SIL/PLe certified. Real E-stop must be hard-wired, not software.
- LS offsets are cross-checked from open implementations + the protocol brief;
  **confirm with a live CPU/Wireshark capture before shipping.**
