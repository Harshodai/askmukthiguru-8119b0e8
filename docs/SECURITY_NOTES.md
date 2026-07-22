# Security Notes — Backend Repo Tracking

The Lovable security scanner surfaces several findings that originate in the **Python FastAPI backend** repository, not in this Lovable project. They cannot be fixed by changes in this repo; they are tracked here so they aren't lost.

## Must-fix in backend repo

### 1. Hardcoded Sarvam API key (RESOLVED)
**Files:** `backend/scratch_test_sarvam_m.py`, `backend/scratch_test_sarvam_reasoning.py`, `backend/test_chunk_extraction.py`
- **Status:** Resolved. Hardcoded keys have been removed and replaced with dynamic environment variable loading via `os.environ.get("SARVAM_API_KEY")` or `settings.sarvam_api_key`.

### 2. Open Gradio `/ui` route
**File:** `backend/app/main.py`

```python
if settings.enable_gradio_ui:  # default False in prod
    gr.mount_gradio_app(app, create_demo(), path="/ui")
```

### 3. STT / TTS endpoints missing auth
**File:** `backend/app/main.py`

Add `user: Dict = Depends(get_current_user_from_supabase)` to both
`speech_to_text_endpoint` and `text_to_speech_endpoint`. Add `@limiter.limit("10/minute")`.

### 4. TestAuthStrategy production backdoor
**File:** `backend/services/auth_service.py`

```python
strategies = [LocalAuthStrategy(), SupabaseAuthStrategy()]
if settings.enable_test_auth:  # default False
    strategies.insert(0, TestAuthStrategy())
assert not (settings.environment == "production" and settings.enable_test_auth)
```

### 5. Hardcoded admin email / default password in seed script
**File:** `backend/scripts/seed_admin.py`

```python
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
```

### 6. Raw exception messages in 500 responses
**Files:** `backend/app/main.py` (`/api/speech/tts`), `backend/routers/admin.py` (`/api/admin/ask`)

```python
except Exception as e:
    logger.error(f"TTS error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Speech synthesis failed. Please try again.")
```

---

## Already fixed in this Lovable project
- `src/hooks/useRequireAuth.ts` — JWT no longer logged to console.
- All four edge functions (`sarvam-stt`, `sarvam-tts`, `delete-my-account`, `export-my-data`) return generic 500 messages.
- `has_role`, `whoami_diagnostics`, `ensure_profile_and_role` — `EXECUTE` revoked from `anon` / `public`.
