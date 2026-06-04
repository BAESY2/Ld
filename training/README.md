# PLC Coder LoRA Fine-Tuning Pipeline

This directory contains tooling for fine-tuning an open-source code model on
**our own verified PLC-ST golden data**, to reduce cloud-API dependency for
on-premises / industrial deployments.

---

## Pipeline Overview

```
tests/fixtures/golden/          (golden JSON cases — built by the data agent)
        │
        ▼
training/export_dataset.py      → data/sft.jsonl
        │  [VERIFY GATE — only error-free cases pass]
        ▼
training/train_lora.py          → models/plc-coder-lora/   (GPU box)
        │
        ▼
vllm serve <merged-model>       → http://localhost:8000/v1
        │
        ▼
app (LLM_PROVIDER=openai_compatible + LOCAL_BASE_URL)
```

---

## Step 1 — Build the Golden Dataset

Golden cases live in `tests/fixtures/golden/*.json`.  Each file must contain:

```json
{
  "name":      "...",
  "request":   "<natural-language description>",
  "spec":      { /* StateMachineSpec JSON */ },
  "golden_st": "<verified IEC 61131-3 ST code>",
  "expect":    { "double_coils": 0, "interlock_errors": 0, "min_rungs": 1 }
}
```

The golden directory is built by a separate data-curation agent; it may not
exist yet when this README is first read.

---

## Step 2 — Export to JSONL (no GPU needed)

```bash
python -m training.export_dataset \
    --golden-dir tests/fixtures/golden \
    --out        data/architect_sft.jsonl \
    --kind       architect        # or 'analyst' or 'both'
```

**`--kind` options:**

| Value | Content |
|-------|---------|
| `architect` | system=ST_ARCHITECT_SYSTEM, user=spec+device-map, assistant=ST code |
| `analyst`   | system=REQUIREMENTS_ANALYST_SYSTEM, user=NL request, assistant=spec JSON |
| `both`      | all of the above concatenated |

### Verify Gate (critical safety property)

`export_dataset.py` calls `app.verifier.verify(spec, golden_st)` on every
case before including it.  **Any case with an `error`-severity issue is
silently dropped.**  This guarantees:

- No double-coil examples enter training data.
- No interlock violations enter training data (when Z3 is available).
- No spec-less cases enter training data.

This is intentional: we never want the model to learn incorrect PLC logic.

---

## Step 3 — Train (GPU box)

### Install extras

Add to `pyproject.toml` if not already present:

```toml
[project.optional-dependencies]
train = [
  "torch>=2.3",
  "transformers>=4.43",
  "peft>=0.12",
  "trl>=0.9",
  "datasets>=2.20",
  "accelerate>=0.31",
  "bitsandbytes>=0.43",
]
```

Then:

```bash
pip install -e .[train]
```

### Run training

```bash
python -m training.train_lora \
    --data         data/architect_sft.jsonl \
    --base-model   Qwen/Qwen2.5-Coder-7B-Instruct \
    --output-dir   models/plc-coder-lora \
    --epochs       3 \
    --bf16
```

For QLoRA on a 24 GB GPU (e.g. RTX 4090 / 3090):

```bash
python -m training.train_lora \
    --data         data/architect_sft.jsonl \
    --base-model   Qwen/Qwen2.5-Coder-7B-Instruct \
    --output-dir   models/plc-coder-lora \
    --epochs       3 \
    --load-in-4bit \
    --bf16
```

Default LoRA config: r=16, alpha=32, dropout=0.05, targeting all attention
and MLP projection layers (`q_proj k_proj v_proj o_proj gate_proj up_proj
down_proj`).

---

## Step 4 — Merge Adapter and Serve with vLLM

### Merge LoRA adapter into base weights

```bash
python - <<'EOF'
from peft import AutoPeftModelForCausalLM
model = AutoPeftModelForCausalLM.from_pretrained("models/plc-coder-lora")
merged = model.merge_and_unload()
merged.save_pretrained("models/plc-coder-merged")

from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-7B-Instruct")
tok.save_pretrained("models/plc-coder-merged")
EOF
```

### Serve

```bash
pip install vllm

vllm serve models/plc-coder-merged \
    --port 8000 \
    --served-model-name plc-coder \
    --gpu-memory-utilization 0.90
```

---

## Step 5 — Point the App at the Local Model

Set environment variables (`.env` or export):

```bash
LLM_PROVIDER=openai_compatible
LOCAL_BASE_URL=http://localhost:8000/v1
LOCAL_MODEL=plc-coder
```

The app's LLM client will use the OpenAI-compatible API exposed by vLLM,
dropping the need for an Anthropic/OpenAI API key for inference.

---

## Legal Notes

- **Base model licence**: Qwen2.5-Coder is released under **Apache-2.0**, which
  permits fine-tuning and commercial deployment.  Always verify the licence of
  any alternative base model before training.
- **Training data**: exclusively our own clean golden cases, all of which have
  passed the `verify()` gate.  No third-party weights, no leaked proprietary
  data, no copyright-encumbered examples.
- **Weight distribution**: the merged model inherits the Apache-2.0 licence.
  If you redistribute it, include the original licence and a notice that it
  is a derivative work.
