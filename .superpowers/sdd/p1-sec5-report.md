# P1-SEC-5 — Frontend nginx runs as non-root

**Status**: FIXED + Docker-verified (2026-08-07)

## Finding

`frontend.Dockerfile` (repo root) ran nginx as **root**: no `USER` directive,
so the nginx master process (PID 1) ran as root. A container escape would
yield root on the host. `backend/Dockerfile` and `Dockerfile` (Railway) both
already drop to a non-root user (`appuser`).

## T1 — frontend.Dockerfile: non-root nginx

Added before the final `CMD` (pattern matches `Dockerfile.railway`'s
`USER`-before-`CMD` convention):

```dockerfile
# (comment block — rationale + path analysis)
RUN chown -R nginx:nginx /var/cache/nginx /run /var/log/nginx

USER nginx
```

`nginx:alpine` ships a system user `nginx` (uid 101) — no useradd needed.

### Writable-path analysis (nginx.conf at repo root → `/etc/nginx/conf.d/default.conf`)

- `nginx.conf` is a **server block only** — no `pid`, `error_log`,
  `access_log`, `proxy_temp_path`, or `client_body_temp_path` directives,
  so the image defaults apply:
  - **pid**: `/var/run/nginx.pid` → symlink `/var/run -> ../run`, real path `/run/nginx.pid`
  - **logs**: `/var/log/nginx/{error,access}.log`
  - **temp/cache**: `/var/cache/nginx/{client_temp,proxy_temp,…}` — required
    because `/api` proxies with `proxy_buffering on`
- `/usr/share/nginx/html/app` static assets: root-owned read-only is fine
  (nginx only reads).

### Gotcha caught by runtime testing (busybox chown symlink)

First attempt used the hint form `chown -R nginx:nginx /var/cache/nginx
/var/run /var/log/nginx`. Runtime test showed nginx exiting with
`[emerg] open() "/run/nginx.pid" failed (13: Permission denied)` — busybox
`chown` **lchowns a command-line symlink operand** (`/var/run`), leaving the
real target `/run` root-owned. Fix: chown the real directory `/run` instead
of the `/var/run` symlink. Verified working (pid file created by uid 101).

## T2 — k8s manifest (SKIPPED, documented)

`k8s/frontend-deployment.yaml` does **not** exist. Directory contains only
`backend-deployment.yaml`, `helm/`, `minikube/`, `nginx/`, `skaffold.yaml`,
`README.md`. Frontend deployment is covered by the Helm chart template
`k8s/helm/mukthiguru/templates/frontend.yaml` (no `securityContext`
`runAsNonRoot` set there — suggested follow-up: add
`securityContext: {runAsNonRoot: true, runAsUser: 101}` to that template in
a separate change; not done here per YAGNI / scope). No new manifest created.

## T3 — Local verification (docker RAN)

Docker daemon was available (`29.6.2`). Built `frontend.Dockerfile`
(stage-1 layers cache-hit; build args from `.env.production`). Runtime
verification on the built image:

| Check | Result |
|---|---|
| `docker run --entrypoint whoami` | `nginx` ✅ |
| `ps aux` in container | master + 10 workers all `nginx` (PID 1 = nginx, not root) ✅ |
| `/run` ownership / `/run/nginx.pid` | owned by `nginx`, pid file created ✅ |
| `GET /health` (container up) | 200 `healthy` ✅ |
| `GET /api/health` (proxy path w/ buffering) | 502 (temp-file write OK; upstream `backend` refused — expected standalone, resolves in compose) ✅ |
| `10-listen-on-ipv6-by-default.sh` info msg | harmless (script can't rm root-owned conf as non-root; config unaffected) |

Test image tag removed after verification. The container runtime test caught
one real bug (symlink chown) that static review alone would have missed —
recommend the controller keep the `docker run --entrypoint whoami` check in
CI or the release checklist.

## Files changed

- `frontend.Dockerfile` (chown + `USER nginx`)
- `.superpowers/sdd/p1-sec5-report.md` (this report)

Suggested lessons.md entry (author: controller, not agent): "busybox chown
lchowns symlink operands — chown the real dir (`/run`), not `/var/run`, when
hardening nginx:alpine images."
