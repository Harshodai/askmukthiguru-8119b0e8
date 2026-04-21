# 🧠 LLM Model Comparison for Mukthi Guru

## Your Requirements

| Requirement | Priority |
|---|---|
| Indian language support (22 languages) | **Critical** |
| High accuracy for spiritual/sensitive content | **Critical** |
| Safety & guardrails compatibility | **Critical** |
| Cost-efficient (runs on consumer GPU) | **High** |
| Ollama compatible (local inference) | **High** |
| RAG-friendly (instruction following, grounding) | **High** |

---

## 🏆 Top Recommendations

### ⭐ #1 PICK: Qwen3-30B-A3B (Best Bang for Buck)

| Spec | Detail |
|------|--------|
| **Architecture** | MoE — 30.5B total, **3.3B active per token** |
| **Languages** | 119 languages (Hindi, Telugu, Tamil, Kannada, Bengali, etc.) |
| **VRAM (Q4)** | **~18 GB** (fits on RTX 4090) |
| **Ollama** | ✅ `ollama pull qwen3:30b-a3b` |
| **Thinking mode** | ✅ Built-in chain-of-thought reasoning |
| **Context window** | 128K tokens |

**Why this is #1:**
- MoE with only 3.3B active = **faster than Sarvam 30B** (2.4B active) but with more total capacity
- **119 languages** vs Sarvam's 22 — covers ALL Indian languages plus more
- Built-in **thinking/reasoning mode** excellent for RAG (can reason about retrieved context)
- Same VRAM budget as Sarvam 30B — direct drop-in replacement
- Trained on 36T tokens, massive training corpus
- Strong instruction following for guardrails compliance

```bash
# Try it now
ollama pull qwen3:30b-a3b
```

---

### ⭐ #2 PICK: Qwen3-14B (Best for Tight Budget)

| Spec | Detail |
|------|--------|
| **Architecture** | Dense — 14B parameters |
| **Languages** | 119 languages |
| **VRAM (Q4)** | **~10-12 GB** (fits on RTX 3060/4060 Ti) |
| **Ollama** | ✅ `ollama pull qwen3:14b` |
| **Thinking mode** | ✅ Built-in |
| **Context window** | 128K tokens |
| **MMLU** | 81.05 |

**Why:**
- Fits on **12 GB GPU** — much cheaper hardware than Sarvam 30B
- Still excellent multilingual performance across Indian languages
- Dense model = more predictable memory usage
- Great for classification AND generation (could replace both your 3B + 30B with a single model)

```bash
ollama pull qwen3:14b
```

---

### ⭐ #3 PICK: Gemma-2-9B-Indic (Ultra-Lightweight)

| Spec | Detail |
|------|--------|
| **Architecture** | Dense — 9B parameters, Indic fine-tuned |
| **Languages** | Hindi, Kannada, Tamil + English (tuned specifically) |
| **VRAM (Q4)** | **~6 GB** (fits on RTX 3060/4060) |
| **Ollama** | ✅ (via GGUF import) |
| **Context window** | 8K tokens |

**Why:**
- **Specifically fine-tuned for Indian languages** by AI Planet
- Runs on budget GPUs (even 8GB cards)
- Google's Gemma architecture — well-tested, stable
- Perfect as a **classification model** replacement for llama3.2:3b

> [!WARNING]
> Limited to fewer Indian languages (Hindi, Kannada, Tamil) — may not cover all 22.
> Shorter context window (8K) vs others.

---

### #4: Krutrim-2 (India-Native)

| Spec | Detail |
|------|--------|
| **Architecture** | Dense — 12B parameters |
| **Languages** | 22 official Indian languages (trained natively) |
| **VRAM (Q4)** | **~8-10 GB** |
| **Ollama** | ⚠️ Not on Ollama yet, available on HuggingFace |

**Why consider:**
- Built BY Indians FOR Indians — understands cultural nuances
- Comprehends ALL 22 constitutionally recognized languages
- Trained on hundreds of billions of Indic tokens
- Good for your sensitive spiritual content — cultural awareness

> [!NOTE]
> Main limitation: Not yet on Ollama. Would require GGUF conversion + custom import.

---

### #5: Navarasa 2.0 (Telugu Specialist)

| Spec | Detail |
|------|--------|
| **Architecture** | Gemma 7B fine-tuned with LoRA |
| **Languages** | 15 Indian languages (strong Telugu focus) |
| **VRAM (Q4)** | **~5-6 GB** |
| **Ollama** | ✅ (via GGUF on HuggingFace) |

**Why consider:**
- If your primary audience speaks Telugu/South Indian languages
- Very lightweight
- Based on proven Gemma architecture

---

### #6: Sarvam 105B (Premium, If Budget Allows)

| Spec | Detail |
|------|--------|
| **Architecture** | MoE — 105B total, **~10B active** |
| **Languages** | 22 Indian languages (trained natively) |
| **VRAM (Q4)** | **~58 GB** (needs A100 80GB or 3x RTX 4090) |
| **Ollama** | ✅ |
| **Context window** | 128K tokens |

**Why:**
- Most powerful Indian-language model available
- Same maker as your current Sarvam 30B — architecture compatible

> [!CAUTION]
> Requires $1.19+/hr GPU (A100 80GB). Monthly cost: $860+.
> Only for when accuracy is paramount and budget is flexible.

---

## 📊 Head-to-Head Comparison

| Model | Active Params | Languages | VRAM (Q4) | GPU Cost | Ollama | Guardrails | Best For |
|-------|--------|-----------|-----------|----------|--------|------------|----------|
| **Qwen3-30B-A3B** | 3.3B | 119 | 18 GB | $0.28/hr | ✅ | ✅ Strong | **Best overall** |
| **Qwen3-14B** | 14B | 119 | 10 GB | $0.15/hr | ✅ | ✅ Strong | Budget production |
| Sarvam 30B (current) | 2.4B | 22 | 18 GB | $0.28/hr | ✅ | ✅ Good | Indian-native context |
| Gemma-2-9B-Indic | 9B | 3+ | 6 GB | $0.10/hr | ✅ | ✅ Google | Ultra-lightweight |
| Krutrim-2 | 12B | 22 | 8 GB | $0.15/hr | ⚠️ | ✅ Good | Cultural awareness |
| Navarasa 2.0 | 7B | 15 | 5 GB | $0.10/hr | ✅ | ⚠️ Basic | Telugu focus |
| Sarvam 105B | ~10B | 22 | 58 GB | $1.19/hr | ✅ | ✅ Strong | Premium accuracy |

---

## 🎯 My Recommendation for Your Use Case

Given that Mukthi Guru is a **sensitive spiritual project** requiring:

### Best Strategy: **Dual-Model with Qwen3**

```
Classification (intent, grading, faithfulness):  Qwen3-14B   (~10 GB)
Generation (answers, verification):              Qwen3-30B-A3B (~18 GB)
```

**Or the ultimate budget setup:**

```
Both classification AND generation:              Qwen3-14B   (~10 GB total!)
```

### Why Qwen3 over Sarvam 30B:

1. **119 vs 22 languages** — covers every Indian language AND diaspora users
2. **Built-in thinking mode** — the model can reason step-by-step before answering (critical for RAG accuracy)
3. **Stronger instruction following** — better at following guardrail instructions ("don't fabricate", "cite sources")
4. **Same or lower VRAM** — no hardware change needed
5. **Massive training data** — 36T tokens vs Sarvam's undisclosed training set
6. **Active development** — Qwen3.5 already out with 201 languages

### When to keep Sarvam 30B:

- If your users are primarily monolingual Indian-language speakers and you value **cultural nuance** in responses
- If you want an **India-made model** for ideological/branding reasons
- It's already working — "if it ain't broke, don't fix it"

### A/B Test Approach:

The easiest way to decide? **Run both** and compare:

```bash
# Download both presets
cd backend/models
./download_models.sh all       # Downloads Qwen + Sarvam GGUF
# Windows: .\download_models.ps1 all

# In your .env, switch between them:
MODEL_PRESET=qwen    # Qwen3-30B-A3B (gen) + Qwen3-14B (classify)
# MODEL_PRESET=sarvam   # Sarvam 30B (gen) + llama3.2:3b (classify)
```

No code changes needed — just swap `MODEL_PRESET` in `.env` and restart the backend.
