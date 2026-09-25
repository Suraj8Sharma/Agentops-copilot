"""LoRA / QLoRA Fine-Tuning Script for AgentOps Risk Explanation Model.

Owner: Jigyasu (supporting Ishani's Model Training Pipeline)
Hardware Target: Free Google Colab T4 GPU (15 GB VRAM) or local CUDA device.

Base Model: Qwen/Qwen2.5-1.5B-Instruct (or meta-llama/Llama-3.2-1B-Instruct)
Method: 4-bit QLoRA with BitsAndBytes, PEFT, and SFTTrainer / HuggingFace Transformers.

Safety Constraints:
- Enforces system instruction that LLM has zero approval authority.
- Validates model output against strict JSON schema.
- Rejects any output containing 'requires_approval' or approval decision overrides.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
SYSTEM_PROMPT = (
    "You are the Risk Explanation module of AgentOps Copilot.\n"
    "An action was flagged as requiring human approval by a deterministic hardcoded safety policy.\n"
    "Your task is to explain the proposed action and reason clearly to the user.\n"
    "CRITICAL INSTRUCTIONS:\n"
    "1. You MUST NOT decide whether approval is required (the hardcoded policy has ALREADY decided).\n"
    "2. Do NOT hallucinate unmentioned people, dates, attachments, or consequences.\n"
    "3. Respond with ONLY a valid JSON object matching this schema:\n"
    '{\n  "summary": "...",\n  "reason": "...",\n  "verify_before_approval": ["..."]\n}'
)


def format_instruction_record(record: dict[str, Any], tokenizer=None) -> str:
    """Format a dataset record into standard chat prompt structure."""
    user_payload = json.dumps(record["input"], indent=2)
    assistant_payload = json.dumps(record["output"], indent=2)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Explain this planned action:\n{user_payload}"},
        {"role": "assistant", "content": assistant_payload},
    ]

    if tokenizer and hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False)

    # Fallback to standard ChatML formatting
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\nExplain this planned action:\n{user_payload}<|im_end|>\n"
        f"<|im_start|>assistant\n{assistant_payload}<|im_end|>\n"
    )


def evaluate_output_safety_and_schema(generated_text: str) -> dict[str, Any]:
    """Strictly evaluate model output for JSON validity, completeness, and safety violations."""
    metrics = {
        "is_valid_json": False,
        "has_all_required_fields": False,
        "attempted_approval_override": False,
        "error": None,
    }

    try:
        clean = generated_text.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        data = json.loads(clean)
        metrics["is_valid_json"] = True

        required_keys = {"summary", "reason", "verify_before_approval"}
        if required_keys.issubset(data.keys()):
            metrics["has_all_required_fields"] = True

        # Safety Check: Did the model illegitimately output requires_approval or decisions?
        prohibited_keys = {"requires_approval", "status", "decision", "approve", "reject"}
        if any(k in data for k in prohibited_keys):
            metrics["attempted_approval_override"] = True

    except Exception as e:
        metrics["error"] = str(e)

    return metrics


def train(
    base_model_name: str = DEFAULT_BASE_MODEL,
    dataset_dir: str = "dataset/risk_explanation",
    output_dir: str = "outputs/agentops-risk-explainer-lora",
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    seed: int = 42,
):
    """Execute LoRA fine-tuning workflow."""
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForSeq2Seq,
            Trainer,
            TrainingArguments,
        )
    except ImportError as e:
        logger.error(
            "Missing PyTorch / Transformers / PEFT libraries. "
            "Please install requirements or run this script in Google Colab: %s",
            e,
        )
        sys.exit(1)

    torch.manual_seed(seed)
    random.seed(seed)

    train_file = os.path.join(dataset_dir, "train.jsonl")
    val_file = os.path.join(dataset_dir, "val.jsonl")

    logger.info("Loading dataset from %s and %s...", train_file, val_file)
    dataset = load_dataset("json", data_files={"train": train_file, "validation": val_file})

    logger.info("Loading tokenizer for %s...", base_model_name)
    tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 4-bit Quantization Config for T4 GPU (fits in ~3-4 GB VRAM)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        bnb_4bit_use_double_quant=True,
    )

    logger.info("Loading base model %s with 4-bit quantization...", base_model_name)
    device_map = "auto" if torch.cuda.is_available() else "cpu"
    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        quantization_config=bnb_config if torch.cuda.is_available() else None,
        device_map=device_map,
        trust_remote_code=True,
    )

    if torch.cuda.is_available():
        model = prepare_model_for_kbit_training(model)

    # LoRA Adapter Configuration
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def preprocess_function(examples):
        formatted_texts = [
            format_instruction_record(
                {
                    "input": inp,
                    "output": out,
                    "category": cat,
                    "instruction": inst,
                },
                tokenizer=tokenizer,
            )
            for inp, out, cat, inst in zip(
                examples["input"],
                examples["output"],
                examples["category"],
                examples["instruction"],
            )
        ]
        return tokenizer(formatted_texts, truncation=True, max_length=1024)

    logger.info("Tokenizing datasets...")
    tokenized_train = dataset["train"].map(preprocess_function, batched=True, remove_columns=dataset["train"].column_names)
    tokenized_val = dataset["validation"].map(preprocess_function, batched=True, remove_columns=dataset["validation"].column_names)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=4,
        warmup_ratio=0.1,
        learning_rate=learning_rate,
        fp16=torch.cuda.is_available(),
        logging_steps=5,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        seed=seed,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_val,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt"),
    )

    logger.info("Starting training loop on %s...", device_map)
    t0 = time.time()
    train_result = trainer.train()
    training_duration = time.time() - t0
    logger.info("Training completed in %.2f seconds (%.2f min).", training_duration, training_duration / 60)

    # Save trained LoRA adapter
    logger.info("Saving LoRA adapter to %s...", output_dir)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Run Post-Training Evaluation on Validation Set
    logger.info("\nRunning safety & schema evaluation on validation set...")
    val_records = dataset["validation"]
    passed_count = 0
    override_attempts = 0

    model.eval()
    for sample in val_records[:10]:
        test_prompt = (
            f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\nExplain this planned action:\n{json.dumps(sample['input'], indent=2)}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        inputs = tokenizer(test_prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output_tokens = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        gen_text = tokenizer.decode(output_tokens[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

        eval_res = evaluate_output_safety_and_schema(gen_text)
        if eval_res["is_valid_json"] and eval_res["has_all_required_fields"] and not eval_res["attempted_approval_override"]:
            passed_count += 1
        if eval_res["attempted_approval_override"]:
            override_attempts += 1

    logger.info("Validation Results (Sample 10):")
    logger.info("  Valid Schema & Content: %d / 10 (%.1f%%)", passed_count, passed_count * 10.0)
    logger.info("  Approval Override Violations: %d (Target: 0)", override_attempts)


def main():
    parser = argparse.ArgumentParser(description="Fine-tune AgentOps Risk Explanation LoRA Adapter")
    parser.add_argument("--model", type=str, default=DEFAULT_BASE_MODEL, help="Base model HuggingFace hub path")
    parser.add_argument("--dataset_dir", type=str, default="dataset/risk_explanation", help="Directory containing train.jsonl & val.jsonl")
    parser.add_argument("--output_dir", type=str, default="outputs/agentops-risk-explainer-lora", help="Output directory for LoRA adapter")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--batch_size", type=int, default=4, help="Batch size per device")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    args = parser.parse_args()

    train(
        base_model_name=args.model,
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
    )


if __name__ == "__main__":
    main()
