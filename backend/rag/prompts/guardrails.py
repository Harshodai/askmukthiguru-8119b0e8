"""Mukthi Guru — Prompt Templates

Design Patterns:
  - Template Method: Each prompt is a reusable template
  - Single Responsibility: One prompt per capability
  - Defensive Design: Every prompt embeds anti-hallucination constraints

These prompts are the key guardrail layer within the LLM itself.
Every prompt explicitly constrains the LLM to:
1. Only use provided context
2. Say "I don't know" rather than guess
3. Cite sources
4. Stay in character (Mukthi Guru)
"""

# === INTENT CLASSIFICATION PROMPT ===
# Few-shot examples are drawn from counseling dialogue best practices
# (ref: Mental-LLM / neuhai, sonia-health/llm-mental-health-risk-detection benchmark).
# MEDITATION examples explicitly cover voluntary Serene Mind trigger phrases so the
# LLM agent correctly routes user requests to the non-gated meditation flow.
INTENT_CLASSIFICATION_PROMPT = """Classify the user's message into exactly one of these categories:
 
DISTRESS - The user is expressing emotional pain, stress, anxiety, sadness, anger, fear, loneliness, hopelessness, or seeks emotional comfort.
FACTUAL - The user is asking a specific question about spiritual teachings, concepts, biographies, or educational questions about meditation (e.g., "How do I start meditating") that requires direct knowledge retrieval.
RELATIONAL - The user is asking about the connection, relationship, or differences between multiple concepts, or asking a broad structural question.
FOLLOW_UP - The user is asking a question that refers to previous parts of the conversation (using pronouns like 'that', 'it', 'him') or continues a thread.
MEDITATION - The user is requesting a meditation practice to begin right now (this is an action intent to start/do a session, not learn about it). Also classify here when the user explicitly asks to open, start, or do Serene Mind, do breathwork, or mentions breathing exercises right now.
CASUAL - The user is making small talk, greeting, or a general non-spiritual comment.
ADVERSARIAL - The user is asking provocative, comparative, critical, or mocking questions. Examples include asking if Ekam/Oneness is "just repackaged Buddhism," comparing it to "Reiki" or "Pranic healing," questioning financial charges/costs of retreats, or demanding supernatural promises (e.g. bringing back the dead, solving world poverty).
SAFETY_VIOLATION - The user is seeking clinical medical advice, psychiatric medications/prescriptions (e.g. lithium, bipolar treatment), disease diagnosis, or demanding guaranteed financial/business/wealth returns from spiritual practices (e.g., promising to manifest 1 million dollars or become a Fortune 500 company).

CRITICAL DISTINCTION:
- FACTUAL is for educational questions about meditation (e.g., learning how it works).
- MEDITATION is for requests to start practicing meditation right now (action intent).

Examples:
User: "I feel completely hopeless and don't know how to go on." → DISTRESS
User: "Can you open Serene Mind for me?" → MEDITATION
User: "Do Serene Mind now." → MEDITATION
User: "I need to breathe. Can you guide me?" → MEDITATION
User: "Let's do a meditation session." → MEDITATION
User: "Start the breathing exercise." → MEDITATION
User: "I want to try Serene Mind." → MEDITATION
User: "Guide me through a meditation" → MEDITATION
User: "Let's do a meditation session" → MEDITATION
User: "Is Oneness just repackaged Buddhism?" → ADVERSARIAL
User: "Why do spiritual retreats charge so much money?" → ADVERSARIAL
User: "Can meditation cure my clinical bipolar disorder or can I take lithium?" → SAFETY_VIOLATION
User: "How do I manifest exactly 1 million dollars?" → SAFETY_VIOLATION
User: "You said don't force meditation but practice daily. Which is it?" → FOLLOW_UP
User: "Is meditation really necessary?" → FACTUAL
User: "How do I start a meditation practice" → FACTUAL
User: "Why does Soul Sync have six steps?" → FACTUAL
User: "What is the Beautiful State according to Sri Preethaji?" → FACTUAL
User: "How does suffering relate to consciousness in the teachings?" → RELATIONAL
User: "Can you say more about what you just told me?" → FOLLOW_UP
User: "Hi, how are you today?" → CASUAL
User: "I'm feeling so anxious about everything lately." → DISTRESS
User: "What did Krishnaji say about karma?" → FACTUAL

RESPOND WITH ONLY ONE WORD: DISTRESS, FACTUAL, RELATIONAL, FOLLOW_UP, MEDITATION, ADVERSARIAL, SAFETY_VIOLATION, or CASUAL"""



# === COMBINED INTENT + COMPLEXITY PROMPT (Phase-1 Optimization) ===
# Single fast-model call replaces two sequential calls (classify_intent + is_complex_query).
# Empirical impact: intent_router latency drops from 14-30s to ~0.5s on llama3.2:3b.
INTENT_AND_COMPLEXITY_PROMPT = """Classify the user's message on TWO axes in a single response.

AXIS 1 — INTENT (pick exactly one):
DISTRESS  - emotional pain, anxiety, sadness, hopelessness, asking for comfort
FACTUAL   - direct spiritual/biographical knowledge question, including educational questions about meditation
RELATIONAL- asks about relationships/differences between multiple concepts
FOLLOW_UP - refers to previous conversation (it, that, him, "you just said")
MEDITATION- asking to start practicing meditation or do breathwork RIGHT NOW (action intent)
CASUAL    - greeting, small talk, non-spiritual chit-chat
ADVERSARIAL    - provocative/comparative/mocking ("is X just repackaged Y?")
SAFETY_VIOLATION - clinical medical advice, psychiatric drug Rx, guaranteed money returns

AXIS 2 — COMPLEXITY (pick exactly one):
simple   - single concept, can be answered directly
complex  - compares concepts, multiple unrelated parts, uses 'and/vs/compare/difference'

CRITICAL DISTINCTION:
- FACTUAL is for educational queries (e.g. learning how to meditate, "How do I start a meditation practice").
- MEDITATION is for requests to start practicing meditation right now (action intent).

OUTPUT FORMAT — exactly two lines, no prose, no markdown:
INTENT: <one of the labels above>
COMPLEXITY: <simple|complex>

Examples:
User: "What is the Beautiful State?"
INTENT: FACTUAL
COMPLEXITY: simple

User: "How do I start a meditation practice"
INTENT: FACTUAL
COMPLEXITY: simple

User: "Compare Soul Sync and Serene Mind meditations"
INTENT: RELATIONAL
COMPLEXITY: complex

User: "I feel hopeless and lost."
INTENT: DISTRESS
COMPLEXITY: simple

User: "Can you start Serene Mind for me?"
INTENT: MEDITATION
COMPLEXITY: simple

User: "Guide me through a meditation now"
INTENT: MEDITATION
COMPLEXITY: simple

User: "Let's meditate together"
INTENT: MEDITATION
COMPLEXITY: simple
"""



