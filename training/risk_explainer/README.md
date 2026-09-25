# AgentOps — Risk Explanation Fine-Tuning Pipeline (for Ishani)

**Owner:** Ishani (Training execution) & Jigyasu (Dataset & Training Pipeline Architecture)  
**Target Hardware:** Google Colab Free T4 GPU (15 GB VRAM)  
**Target Model:** `Qwen/Qwen2.5-1.5B-Instruct` (or `meta-llama/Llama-3.2-1B-Instruct`)  
**Method:** 4-bit QLoRA with BitsAndBytes, PEFT, and HuggingFace Transformers

---

## 1. Safety Separation Architecture

> [!IMPORTANT]
> **Safety Invariant:** The LLM is strictly advisory. It NEVER decides whether an action needs human approval.
> The hardcoded deterministic policy in `backend/app/risk/risk_rules.py` is the sole authority on `requires_approval`.
> The fine-tuned model explains *why* the rule was matched and produces a verification checklist for the human.

---

## 2. Step-by-Step Training Instructions (Google Colab)

1. Open [Google Colab](https://colab.research.google.com).
2. Set Runtime: **Runtime > Change runtime type > T4 GPU**.
3. Upload `training/risk_explainer/train_lora_colab.ipynb` or clone the repository.
4. Execute Section 1 to install dependencies:
   ```bash
   pip install torch transformers datasets peft bitsandbytes accelerate
   ```
5. Validate the dataset:
   ```bash
   python dataset/risk_explanation/validate_dataset.py
   ```
6. Start training:
   ```bash
   python training/risk_explainer/train_lora.py --model Qwen/Qwen2.5-1.5B-Instruct --epochs 3 --batch_size 4
   ```
7. Training takes approximately **8–12 minutes** on a free T4 GPU.
8. The trained LoRA adapter is saved to `outputs/agentops-risk-explainer-lora/`.

---

## 3. Integrating the LoRA Adapter with FastAPI Backend

To load the trained adapter in the AgentOps FastAPI backend:

1. Place the adapter directory in `backend/models/risk_explainer_adapter/` or upload it to Hugging Face Hub.
2. In `backend/app/risk/risk_explainer.py`, set:
   ```python
   ADAPTER_PATH = "models/risk_explainer_adapter"
   ```
3. If the adapter is absent or device memory is insufficient, the system automatically and transparently falls back to the **General LLM Router** (Groq/Gemini) and **Deterministic Template Fallback**.
