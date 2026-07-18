# Mukthi Vault — the owner-blind Second Brain

The architecture and operating manual for the per-user, encrypted knowledge
graph in this folder. This is the feature your repo was missing and the one
that makes MukthiGuru a category of one.

---

## 1. What it is

Every user gets a private knowledge graph — reflections, entities,
preferences, relationships, journal entries, and the edges between them —
that the app uses to personalize guidance. It is:

- **Per-user** — hard isolation; no user can ever read another's graph.
- **Encrypted at rest** — AES-256-GCM; payloads stored as ciphertext, while
  blind indexes and required row metadata remain visible. Equality leakage
  from blind indexing is explicitly acknowledged: the HMAC of a term allows
  deduplication but leaks which records share the same term value.
- **Owner-blind (optional, Mode B)** — with `session_unlock`, passive
  operators without request and runtime access cannot read a user's graph.
  Operators with full production access (env, runtime, logs) may reconstruct
  the unlock secret if `X-Brain-Unlock` is captured. This header **must** be
  redacted from ingress, access, and trace logs.
- **Graph-structured** — entities and typed relations, not a flat list
  (Tony Seale's "memory is a graph, not a bag of facts").
- **Portable & erasable** — full export (GDPR) and irreversible
  crypto-shredding.

## 2. Threat model (honest)

| Adversary | Mode A (server-wrapped) | Mode B (session-unlock) |
|---|---|---|
| Stolen DB backup / read replica | ✅ ciphertext only | ✅ ciphertext only |
| DB admin browsing tables | ✅ ciphertext only | ✅ ciphertext only |
| Operator with app **env** (holds KEK) | ⚠️ can decrypt | ✅ **cannot** (no KEK) |
| Operator with env + KMS access | ⚠️ can decrypt | ✅ **cannot** |
| Phished user session | ❌ (attacker has the session) | ❌ (same) |
| Forgotten passphrase | n/a | data unrecoverable (by design) |

Mode A protects against the most common real-world breach (data at rest,
backups, replicas, curious DB access). Mode B additionally protects against
the *operator* — which is your stated requirement ("even I should not see
their knowledge graph"). Offer Mode B as "Private Mode" in settings.

## 3. Key hierarchy

```
User passphrase ──(Argon2id, Mode B)──┐
                                      ├─→ KEK ──wraps──> DEK ──AES-256-GCM──> ciphertext
BRAIN_KEK env/KMS ──(Mode A)─────────┘      (per user)        (per artifact)
```

- **DEK** (Data-Encryption-Key): 32 random bytes, one per user. Encrypts all
  of that user's artifacts. Stored only *wrapped* by the KEK.
- **KEK** (Key-Encryption-Key): wraps/unwraps the DEK. Mode A: server-held
  (env/KMS). Mode B: derived from the user's passphrase via Argon2id.
- **AAD**: every ciphertext is bound to `user_id:kind:item_id` so a row
  can't be cut-and-pasted into another user's scope undetected.
- **Blind index**: HMAC of a term lets the DB dedupe entities without
  storing the term in plaintext.

## 4. Client protocol (Mode B)

1. Client prompts for the passphrase (never stored, never sent raw).
2. Client derives an unlock secret (WebCrypto PBKDF2 — see
   `SecondBrainPage.tsx`), sends it per-request in the `X-Brain-Unlock`
   header over TLS.
3. Server derives the Argon2 KEK from that secret + stored salt, unwraps the
   DEK **in memory for that request only**, decrypts, zeroizes.
4. Server never logs, caches, or persists the DEK or passphrase.
   `X-Brain-Unlock` **must** be redacted from ingress, access, and trace
   logs to prevent operator-side reconstruction of the unlock secret.

Trade-off to surface in UI: if the user forgets the passphrase, the brain is
unrecoverable. That *is* the privacy guarantee.

## 5. Files

| File | Role |
|---|---|---|
| `backend/services/second_brain/crypto.py` | envelope encryption (DEK/KEK, AES-GCM, Argon2id, blind index, zeroize). Self-test included. |
| `backend/services/second_brain/service.py` | provisioning, extraction, encrypted storage/recall, erasure, export. |
| `backend/app/api/second_brain.py` | FastAPI router; per-request vault unlock; **no admin read endpoint by design**. |
| `supabase/migrations/20260717191006_second_brain_vault.sql` | schema + RLS; no admin read policy. |
| `k8s/helm/mukthiguru/templates/externalsecret.yaml` | ExternalSecret that provisions the brain-vault KEK from cluster secret store. |
| `backend/tests/test_second_brain.py` | 6 tests — round-trip, extraction, Mode-B lock, isolation, shredding, zeroize. **All pass.** |

## 6. Integration (3 seams)

1. **App startup** (`app/main.py`): build `SecondBrainService` with the
   existing Supabase client, `EmbeddingService`, Qdrant, and your LLM
   gateway; stash on `app.state.second_brain`.
2. **Context injection** (`rag/nodes/generation.py`): where you currently
   pull `MemoryService` context, also pull
   `second_brain.personal_context(user_id, query, vault)` and merge into the
   KNOWLEDGE block (bounded, so context stays tight — Seale's "context rot").
3. **Post-response write** (chat pipeline hook): call
   `second_brain.extract_and_write(...)` after each turn, exactly where
   `MemoryService.extract_and_write` runs today. Failures must never break
   the chat path (the service already swallows them).

## 7. Why this beats every competitor

- **Spiritual AI apps** (Hallow, Sri Mandir, Gita GPT): no private per-user
  memory at all, let alone encrypted.
- **Second-brain apps** (Mem, Notion, Reflect): Reflect has E2EE but is a
  notes app, not a doctrine-grounded guide.
- **Big platforms** (ChatGPT/Gemini memory): not owner-blind, not spiritual.

You are the only product combining **doctrine-grounded guidance** + a
**graph-structured** + **owner-blind-encrypted** personal memory. That's the
headline.

## 8. Ops notes

- Generate the Mode-A KEK: `openssl rand -base64 32` → `BRAIN_KEK` env (or
  better, a KMS — see `code/k8s/production-pack.yaml` ExternalSecret).
- Rotating the Mode-A KEK orphans previously-wrapped DEKs — plan a re-wrap
  migration job before rotating.
- The audit log (`_audit`) records unlock/export/shred events with no
  plaintext — ship it to your tamper-evident sink.
