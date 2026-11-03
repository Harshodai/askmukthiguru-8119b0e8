# Memory & Second Brain Vault Architecture

In AskMukthiGuru, a seeker's spiritual journey is treated as an unfolding continuum rather than isolated chat sessions. The **Second Brain Vault** is a private, zero-knowledge, bi-temporally versioned personal memory system designed to preserve insights, spiritual breakthroughs, personal challenges, and sadhana milestones.

The vault ensures that future guidance recognizes the seeker's evolving consciousness while enforcing an absolute architectural invariant: **zero plaintext persistence across all database rows, log lines, and vector indexes.**

---

## 1. Three-Tier Memory Architecture

The memory subsystem is structured across three complementary tiers, balancing microsecond retrieval latency with cryptographic isolation and relational ontology:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            SEEKER CHAT & PROFILE UI                              │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│       TIER 1: HOT CACHE         │             │    TIER 2: CANONICAL VAULT      │
│          Redis 7.x              │             │  PostgreSQL + Qdrant Vault      │
│        (Port 6379)              │             │    (Port 5432 / 6333)           │
├─────────────────────────────────┤             ├─────────────────────────────────┤
│ • 24h exact answer cache        │             │ • Bi-temporal memory nodes      │
│ • Key: SHA256(query + policy)   │             │   (valid_from, valid_to)        │
│ • Ephemeral session context     │             │ • Encrypted at rest (AES-GCM)   │
│ • Sub-millisecond read latency  │             │ • Zero-knowledge vector index   │
└─────────────────────────────────┘             └────────────────┬────────────────┘
                                                                 │
                                                                 ▼
                                                ┌─────────────────────────────────┐
                                                │    TIER 3: ONTOLOGY GRAPH       │
                                                │          Neo4j 5.x              │
                                                │      (Port 7474 / 7687)         │
                                                ├─────────────────────────────────┤
                                                │ • Global spiritual concepts     │
                                                │ • LightRAG entity hierarchies   │
                                                │ • 5-Node OKF transformation arcs│
                                                │ • Universal doctrine grounding  │
                                                └─────────────────────────────────┘
```

### 1.1 Architectural Comparison of Tiers

| Tier | Engine / Storage | Primary Artifacts | Lifecycle & Persistence | Privacy & Encryption |
|---|---|---|---|---|
| **Tier 1: L1 Hot Cache** | Redis 7.x (`redis:6379`) | Exact prompt hashes, pipeline cache, rate limit buckets | 24-hour TTL; invalidated on schema/collection drift | In-memory key-value; ephemeral data only |
| **Tier 2: L2 Canonical Vault** | PostgreSQL (`user_brain_nodes`) + Qdrant | Bi-temporal seeker memories, personal reflections | Durable; immutable append-only with superseding | AES-256-GCM envelope encryption (Zero plaintext) |
| **Tier 3: L3 Concept Graph** | Neo4j (`neo4j:7687`) | Authentic spiritual doctrine, OKF transformation arcs | Curated; versioned across release cycles | Global public domain; zero seeker PII |

---

## 2. Second Brain Vault UI Experience (`/profile?tab=memory`)

Seekers interact with their personal memory repository via the **Memory** tab within `/profile` or through the standalone `/second-brain` dashboard:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SECOND BRAIN VAULT DASHBOARD                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🔒 Vault Status: Unlocked (Session Key Active)           [ Lock Vault ] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ ┌──────────────────────────────────────┐ ┌────────────────────────────────┐ │
│ │           PERSONAL REFLECTIONS       │ │     SPIRITUAL CONCEPT MAP      │ │
│ │                                      │ │                                │ │
│ │ ✦ "Experiencing deep peace during    │ │        [Soul Sync]             │ │
│ │    Soul Sync practice."              │ │             │                  │ │
│ │    Type: reflection • Active         │ │        [Meditation]            │ │
│ │    Provenance: Chat Turn #14         │ │         /        \             │ │
│ │                                      │ │    [Peace]    [Stillness]      │ │
│ │ ✦ "Observed anxiety around career    │ │                                │ │
│ │    transitions and family."          │ │  Interactive Concept Explorer  │ │
│ │    Type: journal • Active            │ │  Click nodes to inspect related│ │
│ │    Provenance: Video Clip #ehkqJ     │ │  teachings from Sri Preethaji  │ │
│ └──────────────────────────────────────┘ └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Core Vault Features
* **Memory Manager (`MemoryManager.tsx`)**: Displays categorized cards representing reflections, journals, spiritual insights, and sadhana milestones.
* **Reflections & Notes Dock (`NotesPanel.tsx`)**: Allows seekers to capture spontaneous realizations directly during contemplative practice or chat turns.
* **Interactive Knowledge Graph Explorer (`KGConceptMap.tsx`)**: An interactive canvas visualizing the seeker’s active reflections connected to core spiritual doctrines (e.g. *Beautiful State*, *Ekam Oneness*, *Inner Stillness*).

---

## 3. Bi-Temporal Invalidation & Superseding Rules

Spiritual growth is characterized by deep psychological transformation. An insight held six months ago (e.g., *"I feel trapped in chronic fear and isolation"*) may be transformed through sadhana into a new realization (e.g., *"I experience the world as interconnected and friendly"*).

Standard databases overwrite or delete old records, destroying historical context. AskMukthiGuru implements **Bi-Temporal Invalidation** (`backend/services/second_brain/second_brain_service.py`), ensuring that personal history is **never deleted**, but rather bi-temporally superseded:

```
              INITIAL STATE:
       ┌───────────────────────────┐
       │     Old Memory (Node A)   │
       │ "Suffering from grief"    │
       │ valid_from: 2026-01-10    │
       │ valid_to: NULL (Active)   │
       │ is_superseded: False      │
       │ decay: 1.0                │
       └───────────────────────────┘
                     │
                     │  Seeker experiences transformation via Soul Sync
                     │  invalidate_and_supersede(user_id, old_id, new_id)
                     ▼
              SUPERSEDED STATE:
       ┌───────────────────────────┐         [:SUPERSEDED_BY {weight: 0.05}]
       │     Old Memory (Node A)   ├─────────────────────────────────────────┐
       │ valid_to: 2026-04-15      │                                         │
       │ is_superseded: True       │                                         ▼
       │ decay: 0.05               │                          ┌───────────────────────────┐
       │ superseded_by: Node B     │                          │     New Memory (Node B)   │
       └───────────────────────────┘                          │ "Deep peace in Soul Sync" │
                                                              │ valid_from: 2026-04-15    │
                                                              │ valid_to: NULL (Active)   │
                                                              │ is_superseded: False      │
                                                              │ decay: 1.0                │
                                                              └───────────────────────────┘
```

### 3.1 Five Inviolable Invalidation Rules (`tests/test_second_brain.py`)

1. **Immutability (Never Deleted)**:
   Old rows in `user_brain_nodes` are never dropped or deleted. When superseded, `valid_to` is populated with `datetime.utcnow()`, `is_superseded` is set to `True`, and `decay` is adjusted to `0.05`.
2. **Encrypted Directed Edge**:
   An explicit relationship record is inserted into `user_brain_edges`:
   $$\text{Edge} = (\text{old\_id}) \xrightarrow{\text{SUPERSEDED\_BY}} (\text{new\_id}) \quad [\text{weight} = 0.05]$$
3. **Default Filtering Excludes Superseded Facts**:
   When the RAG pipeline retrieves personal context for live chat (`personal_context`), it executes with `include_superseded=False`. The SQL query filters on `is_superseded = False`, returning only active truths.
4. **Decayed Historical Recall**:
   When longitudinal spiritual growth analysis is requested (`include_superseded=True`), superseded facts are included in candidate retrieval but penalized with a $0.05$ ranking decay multiplier, ensuring current consciousness dominates guidance.
5. **Anti-Crowding Query Guarantee**:
   Superseded filtering occurs **strictly at the SQL query level**, not in application memory. A sequence of historical superseded entries cannot fill the query `LIMIT` window and crowd out active memories.

### 3.2 Security & Isolation Constraints
* **Rejection of Foreign & Cross-User IDs**:
  A user cannot supersede or link a memory belonging to another user. The service verifies tenant ownership before modifying state, raising `KeyError` on foreign ID injection attempts.
* **Self-Supersession Guard**:
  Attempting to supersede a node with its own ID ($A \rightarrow A$) raises `ValueError` immediately, preventing infinite cyclical pointer loops.

---

## 4. Cryptographic Architecture: Envelope Encryption & Zero Plaintext

Seeker confessions and personal reflections contain deeply private inner disclosures. AskMukthiGuru enforces a strict zero-knowledge envelope encryption model:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ENVELOPE ENCRYPTION TOPOLOGY                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Master Key (Env):                                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ BRAIN_KEK (32-byte Key Encryption Key)                                │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ Encrypts / Decrypts                  │
│                                      ▼                                      │
│  Per-User Vault Key:                                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ DEK (User Data Encryption Key)                                        │  │
│  │ Mode A: Master Key derivation   •   Mode B: Seeker Passphrase (Argon2)│  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ AES-256-GCM Authenticated Encryption │
│                                      ▼                                      │
│  Data Plane Storage:                                                        │
│  ┌─────────────────────────────────┐     ┌────────────────────────────────┐ │
│  │  PostgreSQL (user_brain_nodes)  │     │   Qdrant (user_brain_vault)    │ │
│  │  • ciphertext (Base64)          │     │   • user_id (UUID)             │ │
│  │  • iv (Initialization Vector)   │     │   • kind (reflection/journal)  │ │
│  │  • auth_tag (Authentication Tag)│     │   • dense_vector (1024d)       │ │
│  │  [NO PLAINTEXT COLUMN]          │     │   [NO PLAINTEXT PAYLOAD]       │ │
│  └─────────────────────────────────┘     └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Zero Plaintext Persistence Invariant
* **PostgreSQL Storage**:
  `user_brain_nodes` contains `id`, `user_id`, `ciphertext`, `iv`, `auth_tag`, `kind`, `is_superseded`, `valid_from`, `valid_to`, `superseded_by`, and `decay`. Plaintext reflection strings **never enter the relational database**.
* **Vector Store Isolation**:
  The Qdrant `user_brain_vault` index receives high-dimensional vector embeddings generated in volatile memory during an unlocked session. The payload stored alongside points contains strictly metadata:
  ```json
  {
    "user_id": "018d9b1a-...",
    "kind": "reflection",
    "item_id": "a984f1-...",
    "created_at": 1729555200
  }
  ```
  The vector payload **never contains text, summaries, or keywords**, eliminating the risk of vector inversion attacks reconstructing user private disclosures.

---

## 5. Source Provenance Linking

Every memory card created in the Second Brain Vault preserves its lineage and origin evidence, enabling seekers to review exactly what triggered a realization:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROVENANCE LINKAGE TYPES                            │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│    CHAT TURN LINK    │    DISCOURSE CLIP    │      EXPLICIT JOURNAL         │
│  (Session Ingress)   │  (Authentic Video)   │       (Seeker Input)          │
├──────────────────────┼──────────────────────┼───────────────────────────────┤
│ • session_id         │ • video_id           │ • direct_entry: true          │
│ • turn_index         │ • guru_id            │ • tagged_practice             │
│ • extracted_claim    │ • start_ms, end_ms   │ • reflection_category         │
│ • LLM extractor id   │ • transcript_span_id │ • client_timestamp            │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

* **Video Discourse Linking**: When a reflection arises during study of a specific teaching, the memory row stores the canonical video coordinate (`video_id`, `start_ms`, `end_ms`, `guru_id`). Clicking the provenance badge launches playback at the exact second Sri Preethaji or Sri Krishnaji delivered the discourse.
* **Full Audit Trail**: Preserves the intellectual and spiritual provenance of every realization, preventing false memory attribution.

---

## 6. Related Wiki Documentation

* [System Architecture Overview](Architecture-Overview) — Multi-tier database topology and container bindings.
* [12-Layer RAG Pipeline](Architecture-RAG-Pipeline) — Memory context injection during Layer 7.5 context engineering.
* [Frontend Architecture & Seeker Experience](Frontend-UI-and-Seeker-Experience) — Memory Manager UI, Sadhana Heatmap, and Notes Dock.
* [REST & Streaming API Reference](API-Reference) — Second Brain Vault API specifications and schemas.
