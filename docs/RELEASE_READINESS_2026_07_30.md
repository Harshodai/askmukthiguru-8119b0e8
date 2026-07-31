# Release Readiness Checklist — 2026-07-30

## Supabase leaked-password protection

> This feature requires the project to be on the **Pro plan or above**.

### Dashboard steps

1. Open `https://supabase.com/dashboard/project/<project-ref>/auth/providers?provider=Email`.
2. Ensure the project is on **Pro plan or above**.
3. Toggle **Prevent the use of leaked passwords** to **ON**.
4. Verify the behavior:
   - Attempt to sign up with the password `password123`.
   - Expect a `WeakPasswordError` with `reasons: ["leaked_password"]`.

### Verification script

Run **only after** enabling the dashboard toggle:

```bash
cd backend
python3 scripts/verify_leaked_password_protection.py
```

Expected output:

```json
{"ok": true}
```

If the toggle is not enabled, the script will output `{"ok": false}` along with the server response.
