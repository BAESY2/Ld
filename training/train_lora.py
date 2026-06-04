"""LoRA fine-tuning scaffold for PLC ST-code generation.

PURPOSE
-------
Fine-tune an open-source coder model (default: Qwen/Qwen2.5-Coder-7B-Instruct)
on our verified golden examples using Parameter-Efficient Fine-Tuning (LoRA /
QLoRA) via the ``peft`` + ``trl`` libraries.

LEGAL / LICENSE
---------------
* Base model: **Qwen2.5-Coder** is released under the Apache-2.0 licence,
  which permits fine-tuning and commercial use.  Always verify the licence of
  any alternative base model before running this script.
* Training data: only samples that have passed ``verify()`` from
  ``app.verifier`` are used (enforced in ``export_dataset.py``).  No leaked
  weights, no third-party IP.

PREREQUISITES (GPU box only)
-----------------------------
Install the optional train extras::

    pip install -e .[train]

Note: the ``[train]`` extra is not yet in ``pyproject.toml`` (edit it to add):

    [project.optional-dependencies]
    train = [
      "torch>=2.3",
      "transformers>=4.43",
      "peft>=0.12",
      "trl>=0.9",
      "datasets>=2.20",
      "accelerate>=0.31",
      "bitsandbytes>=0.43",   # optional: 4-bit QLoRA
    ]

SERVING (on-prem)
-----------------
After training, merge the LoRA adapter and serve with vLLM::

    # merge adapter into base weights
    python -c "
    from peft import AutoPeftModelForCausalLM
    model = AutoPeftModelForCausalLM.from_pretrained('<output_dir>')
    model.merge_and_unload().save_pretrained('<merged_dir>')
    "

    # serve
    vllm serve <merged_dir> --port 8000 --served-model-name plc-coder

Point the app at the local endpoint::

    LLM_PROVIDER=openai_compatible
    LOCAL_BASE_URL=http://localhost:8000/v1
    LOCAL_MODEL=plc-coder

IMPORTANT: Heavy dependencies (torch, transformers, peft, trl, datasets) are
imported **only inside** the ``train()`` function.  This module can be imported
freely without those libraries installed — a lightweight ``ImportError`` message
is shown if they are missing at call time.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config dataclass — no heavy deps required
# ---------------------------------------------------------------------------


@dataclass
class LoRATrainConfig:
    """All hyper-parameters for LoRA fine-tuning.

    Defaults are tuned for Qwen2.5-Coder-7B-Instruct on a single A100/H100.
    Adjust ``per_device_train_batch_size`` + ``gradient_accumulation_steps``
    for smaller GPUs (e.g. 4090 / 3090).
    """

    # Model
    base_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    """HuggingFace model id or local path.  Must be Apache-2.0 compatible."""

    # LoRA
    lora_r: int = 16
    """LoRA rank.  Higher = more capacity, more VRAM."""

    lora_alpha: int = 32
    """LoRA scaling factor (typically 2 * lora_r)."""

    lora_dropout: float = 0.05
    """Dropout on LoRA layers."""

    target_modules: list[str] = field(
        default_factory=lambda: [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
    )
    """Attention + MLP projection layers targeted by LoRA.
    Works for Llama/Mistral/Qwen2 architectures."""

    # Training
    data_path: str = "data/sft.jsonl"
    """Path to the JSONL file produced by export_dataset.py."""

    output_dir: str = "models/plc-coder-lora"
    """Directory where adapter weights are saved."""

    num_train_epochs: int = 3
    max_seq_len: int = 2048
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    """Effective batch = per_device * gradient_accumulation."""

    learning_rate: float = 2e-4
    warmup_ratio: float = 0.05
    lr_scheduler_type: str = "cosine"

    # Precision / memory
    bf16: bool = True
    """Use bfloat16 mixed precision (requires Ampere+ GPU)."""

    gradient_checkpointing: bool = True
    """Trade compute for memory — enables larger batch sizes."""

    load_in_4bit: bool = False
    """Enable QLoRA (4-bit NF4 quantisation via bitsandbytes)."""

    # Logging
    logging_steps: int = 10
    save_strategy: str = "epoch"


# ---------------------------------------------------------------------------
# Train function — all heavy imports are deferred
# ---------------------------------------------------------------------------


def train(config: LoRATrainConfig | None = None) -> None:
    """Run LoRA / QLoRA fine-tuning.

    All heavy libraries (torch, transformers, peft, trl, datasets) are
    imported here so that this module can be safely imported without them.

    Raises:
        SystemExit: with a human-readable message if the dependencies are
            not installed.
    """
    if config is None:
        config = LoRATrainConfig()

    # ------------------------------------------------------------------
    # Deferred heavy imports
    # ------------------------------------------------------------------
    _missing: list[str] = []
    for pkg in ("torch", "transformers", "peft", "trl", "datasets"):
        try:
            __import__(pkg)
        except ImportError:
            _missing.append(pkg)

    if _missing:
        print(
            "ERROR: The following packages are required for training but not installed:\n"
            f"  {', '.join(_missing)}\n\n"
            "Install the train extras (add to pyproject.toml if not present):\n"
            "  pip install -e .[train]\n\n"
            "Or manually:\n"
            "  pip install torch transformers peft trl datasets accelerate bitsandbytes",
            file=sys.stderr,
        )
        sys.exit(1)

    # pylint: disable=import-outside-toplevel
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from trl import SFTTrainer

    # ------------------------------------------------------------------
    # Validate data file
    # ------------------------------------------------------------------
    data_path = Path(config.data_path)
    if not data_path.exists():
        print(
            f"ERROR: Training data not found: {data_path}\n"
            "Run export_dataset.py first:\n"
            "  python -m training.export_dataset --golden-dir tests/fixtures/golden "
            "--out data/sft.jsonl --kind both",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Loading data from {data_path}", flush=True)
    dataset = load_dataset("json", data_files=str(data_path), split="train")

    # ------------------------------------------------------------------
    # Quantisation config (QLoRA)
    # ------------------------------------------------------------------
    bnb_config: Any = None
    if config.load_in_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    # ------------------------------------------------------------------
    # Model + tokeniser
    # ------------------------------------------------------------------
    print(f"Loading base model: {config.base_model}", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        torch_dtype=torch.bfloat16 if config.bf16 else torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        config.base_model,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ------------------------------------------------------------------
    # LoRA config
    # ------------------------------------------------------------------
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        target_modules=config.target_modules,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    if config.gradient_checkpointing:
        model.gradient_checkpointing_enable()

    # ------------------------------------------------------------------
    # Training arguments
    # ------------------------------------------------------------------
    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_train_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        lr_scheduler_type=config.lr_scheduler_type,
        bf16=config.bf16,
        logging_steps=config.logging_steps,
        save_strategy=config.save_strategy,
        remove_unused_columns=False,
        report_to="none",
    )

    # ------------------------------------------------------------------
    # SFTTrainer
    # ------------------------------------------------------------------
    def formatting_func(example: dict[str, Any]) -> list[str]:
        """Convert chat messages list to a single formatted string."""
        parts: list[str] = []
        for msg in example["messages"]:
            role = msg["role"]
            content = msg["content"]
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n")
        return ["".join(parts)]

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        formatting_func=formatting_func,
        max_seq_length=config.max_seq_len,
        args=training_args,
    )

    print("Starting training…", flush=True)
    trainer.train()
    trainer.save_model(config.output_dir)
    print(f"LoRA adapter saved → {config.output_dir}", flush=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "LoRA fine-tune an open-source coder model on verified PLC golden data. "
            "Requires GPU and the [train] extras.  "
            "See module docstring for full instructions."
        )
    )
    parser.add_argument(
        "--data",
        default=LoRATrainConfig.data_path,
        help="Path to the SFT JSONL file (default: %(default)s)",
    )
    parser.add_argument(
        "--base-model",
        default=LoRATrainConfig.base_model,
        dest="base_model",
        help="HuggingFace model id or local path (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default=LoRATrainConfig.output_dir,
        dest="output_dir",
        help="Directory for the saved LoRA adapter (default: %(default)s)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=LoRATrainConfig.num_train_epochs,
        help="Number of training epochs (default: %(default)s)",
    )
    parser.add_argument(
        "--lora-r",
        type=int,
        default=LoRATrainConfig.lora_r,
        dest="lora_r",
        help="LoRA rank (default: %(default)s)",
    )
    parser.add_argument(
        "--bf16",
        action="store_true",
        default=LoRATrainConfig.bf16,
        help="Use bfloat16 precision (default: %(default)s)",
    )
    parser.add_argument(
        "--load-in-4bit",
        action="store_true",
        default=LoRATrainConfig.load_in_4bit,
        dest="load_in_4bit",
        help="Enable QLoRA 4-bit quantisation (default: %(default)s)",
    )
    args = parser.parse_args()

    cfg = LoRATrainConfig(
        data_path=args.data,
        base_model=args.base_model,
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        lora_r=args.lora_r,
        bf16=args.bf16,
        load_in_4bit=args.load_in_4bit,
    )
    train(cfg)


if __name__ == "__main__":
    main()
