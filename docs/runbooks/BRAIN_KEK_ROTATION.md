# BRAIN_KEK Rotation Runbook

`BRAIN_KEK` wraps per-user Second Brain data-encryption keys. Rotation re-wraps only Mode-A `wrapped_dek` values; it never decrypts or rewrites user payload plaintext, public graph data, Qdrant vectors, or transcript files.

## Preconditions

Keep the current production `BRAIN_KEK` available as `BRAIN_KEK`. Stage a newly generated base64url-encoded 32-byte replacement as `BRAIN_KEK_NEXT`; the decoder accepts padded and unpadded base64url, but operational generators should use canonical padded output. Never print either value, commit either value, or place either value in shell history. Take a database backup, confirm `/api/health`, validate both keys decode to 32 bytes, and confirm the Mode-A row count is non-zero.

## Dry run

```bash
python3 scripts/ops/rotate_brain_kek.py --new-env BRAIN_KEK_NEXT
```

When running in the Railway image, the utility is available at `/app/scripts/ops/rotate_brain_kek.py`; run it through Railway SSH so the real service environment is used rather than a local dotenv overlay.

The utility unwraps each DEK with the old key, re-wraps it with the replacement, verifies the replacement unwrap, and prints only counts. It is dry-run by default.

## Apply

After a human reviews the dry-run and backup:

```bash
python3 scripts/ops/rotate_brain_kek.py --new-env BRAIN_KEK_NEXT --apply --confirm-rewrap
```

Updates use `user_id`, `wrap_mode`, and the old `wrapped_dek` as a compare-and-swap predicate. Unexpected row changes abort the operation. `rotated_at` is updated; the AES-GCM wire-format version is unchanged.

## Cutover and rollback

Only after all rows update successfully, set production `BRAIN_KEK` to the replacement and remove or clear `BRAIN_KEK_NEXT` in both service-scoped and shared-environment scopes. If variable changes were staged with deploys suppressed, explicitly redeploy backend and worker together; a variable update alone does not prove the running processes loaded the cut-over key. Verify health and an authenticated disposable Mode-A vault. If verification fails, inspect Railway logs first; restore the old key from the approved secret manager and restart both services only when a reviewed backup or pre-rotation wrapped-blob snapshot confirms the rollback path. Do not reverse-rotate without that evidence.

The utility rejects malformed/equal keys, refuses empty reads by default, requires `--apply --confirm-rewrap`, verifies replacement unwraps before updates, and never touches `user_brain_nodes`, `user_brain_edges`, public Neo4j, Qdrant corpus points, or transcript files.
