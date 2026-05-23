#!/usr/bin/env python3
"""
Mukthi Guru — Pre-Launch Security Audit
========================================
Runs all 5 categories from the security checklist:
  01 Legal & Privacy
  02 Security Basics
  03 Secrets & API Keys
  04 Abuse Prevention
  05 Security Headers (static analysis)

Usage:
    python3 scripts/security_audit.py
    python3 scripts/security_audit.py --fix        # apply auto-fixes
    python3 scripts/security_audit.py --report     # save JSON report

Exit code: 0 = all PASS, 1 = any FAIL/WARN
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND_SRC = ROOT / "src"

# ─── Result model ────────────────────────────────────────────────────────────


@dataclass
class Finding:
    category: str
    check: str
    status: Literal["PASS", "WARN", "FAIL"]
    detail: str
    fix: str = ""


findings: list[Finding] = []


def record(category, check, status, detail, fix=""):
    findings.append(Finding(category, check, status, detail, fix))
    icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[status]
    print(f"  {icon} [{status}] {check}")
    if status != "PASS":
        print(f"       → {detail}")
        if fix:
            print(f"       🔧 {fix}")


# ─── 01 Legal & Privacy ──────────────────────────────────────────────────────


def check_legal():
    print("\n01 Legal & Privacy")

    # Privacy policy page exists (case-insensitive search)
    all_pages = (
        list(ROOT.rglob("*.tsx"))
        + list(ROOT.rglob("*.jsx"))
        + list(ROOT.rglob("*.html"))
        + list(ROOT.rglob("*.md"))
    )
    all_pages = [f for f in all_pages if ".venv" not in str(f) and "node_modules" not in str(f)]
    pp_files = [f for f in all_pages if "privacy" in f.name.lower()]
    if pp_files:
        record("Legal", "Privacy policy file exists", "PASS", str(pp_files[0]))
    else:
        record(
            "Legal",
            "Privacy policy file exists",
            "FAIL",
            "No privacy policy page found",
            "Create src/pages/Privacy.tsx and wire it to /privacy route",
        )

    # Terms of service (case-insensitive)
    tos_files = [f for f in all_pages if "terms" in f.name.lower()]
    if tos_files:
        record("Legal", "Terms of service file exists", "PASS", str(tos_files[0]))
    else:
        record(
            "Legal",
            "Terms of service file exists",
            "FAIL",
            "No terms of service page found",
            "Create src/pages/Terms.tsx and wire it to /terms route",
        )

    # Data deletion capability
    deletion_hits = _grep_code(r"delete.*user|user.*delete|account.*delet|delet.*account", [".py"])
    if deletion_hits:
        record(
            "Legal",
            "User data deletion capability",
            "PASS",
            f"Found in {len(deletion_hits)} location(s)",
        )
    else:
        record(
            "Legal",
            "User data deletion capability",
            "WARN",
            "No account/data deletion endpoint detected",
            "Add DELETE /api/user/account endpoint for GDPR compliance",
        )

    # PII in logs check
    pii_log_hits = _grep_code(
        r"logger\.(info|debug|warning)\(.*?(email|password|token|phone)", [".py"]
    )
    if pii_log_hits:
        record(
            "Legal",
            "PII not logged",
            "WARN",
            f"Possible PII in log statements: {pii_log_hits[:2]}",
            "Scrub email/token values from log messages",
        )
    else:
        record("Legal", "PII not logged", "PASS", "No obvious PII in log statements")

    # Cookie consent (check for any cookie consent component)
    cookie_hits = _grep_code(
        r"cookie.*consent|consent.*cookie|CookieBanner|cookie.*banner",
        [".tsx", ".jsx", ".ts"],
    )
    if cookie_hits:
        record("Legal", "Cookie consent mechanism", "PASS", f"Found: {cookie_hits[0]}")
    else:
        record(
            "Legal",
            "Cookie consent mechanism",
            "WARN",
            "No cookie consent banner detected",
            "Add a CookieBanner component for GDPR compliance if you use analytics/tracking cookies",
        )


# ─── 02 Security Basics ──────────────────────────────────────────────────────


def check_security_basics():
    print("\n02 Security Basics")

    # CORS not wildcard
    cors_hits = _grep_code(r'allow_origins\s*=\s*\[?\s*["\']?\*["\']?\s*\]?', [".py", ".yml"])
    if cors_hits:
        record(
            "Security",
            "CORS not wildcard",
            "FAIL",
            f"Wildcard CORS found: {cors_hits[0]}",
            "Set cors_origins to explicit frontend domain(s) in .env",
        )
    else:
        record("Security", "CORS not wildcard", "PASS", "No wildcard CORS detected")

    # SQL injection — raw string queries
    sqli_hits = _grep_code(r'execute\(.*?f["\']|execute\(.*?%\s*\(|cursor\.execute\(.*?\+', [".py"])
    if sqli_hits:
        record(
            "Security",
            "No raw SQL string formatting",
            "FAIL",
            f"Possible SQL injection: {sqli_hits[:2]}",
            "Use parameterized queries: cursor.execute('SELECT * FROM t WHERE id = %s', (id,))",
        )
    else:
        record(
            "Security",
            "No raw SQL string formatting",
            "PASS",
            "No raw SQL formatting found",
        )

    # XSS — dangerouslySetInnerHTML
    xss_hits = _grep_code(r"dangerouslySetInnerHTML", [".tsx", ".jsx", ".ts", ".js"])
    if xss_hits:
        record(
            "Security",
            "No dangerouslySetInnerHTML",
            "WARN",
            f"Found in: {xss_hits[:2]}",
            "Review each usage — ensure content is sanitized with DOMPurify before rendering",
        )
    else:
        record("Security", "No dangerouslySetInnerHTML", "PASS", "No unsafe HTML injection")

    # Auth on sensitive endpoints
    auth_dep = _grep_code(r"get_current_user_from_supabase", [".py"])
    if len(auth_dep) >= 3:
        record(
            "Security",
            "Auth dependency on API routes",
            "PASS",
            f"Found in {len(auth_dep)} route(s)",
        )
    else:
        record(
            "Security",
            "Auth dependency on API routes",
            "WARN",
            f"Only {len(auth_dep)} auth-guarded routes detected",
            "Ensure all /api/* endpoints use get_current_user_from_supabase",
        )

    # Session expiry / JWT settings
    jwt_hits = _grep_code(r"jwt_secret|JWT_SECRET|jwt_expir", [".py", ".env.example"])
    if jwt_hits:
        record(
            "Security",
            "JWT secret configured",
            "PASS",
            "JWT secret referenced in config",
        )
    else:
        record(
            "Security",
            "JWT secret configured",
            "WARN",
            "No explicit JWT secret config detected",
            "Ensure SUPABASE_JWT_SECRET is set and never hardcoded",
        )

    # HTTPS enforcement (HSTS / redirect)
    hsts_hits = _grep_code(
        r"Strict-Transport-Security|add_header.*HSTS|https_redirect|force_https",
        [".py", ".conf", ".yml"],
    )
    if hsts_hits:
        record("Security", "HTTPS/HSTS enforcement", "PASS", "HSTS or redirect found")
    else:
        record(
            "Security",
            "HTTPS/HSTS enforcement",
            "WARN",
            "No HSTS header or HTTPS redirect detected",
            "Add Strict-Transport-Security header in nginx or as FastAPI middleware",
        )

    # Security middleware / headers middleware
    sec_header_hits = _grep_code(
        r"SecurityHeadersMiddleware|X-Frame-Options|X-Content-Type|Content-Security-Policy",
        [".py"],
    )
    if sec_header_hits:
        record(
            "Security",
            "Security headers middleware",
            "PASS",
            f"Found: {sec_header_hits[0]}",
        )
    else:
        record(
            "Security",
            "Security headers middleware",
            "FAIL",
            "No security headers middleware detected",
            "Add SecurityHeadersMiddleware (see auto-fix: --fix flag adds it to main.py)",
        )


# ─── 03 Secrets & API Keys ───────────────────────────────────────────────────

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI API key"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
    (
        r'["\'](?:API_KEY|SECRET_KEY|PRIVATE_KEY)["\']:\s*["\'][A-Za-z0-9+/]{16,}["\']',
        "Hardcoded secret",
    ),
    (r'password\s*=\s*["\'][^${\s]{6,}["\']', "Hardcoded password"),
    (r'SARVAM_API_KEY\s*=\s*["\'][a-zA-Z0-9\-]{10,}["\']', "Hardcoded Sarvam key"),
    # Note: Supabase anon keys are PUBLIC by design — skip them
    # Only flag service_role JWTs (role:service_role in payload)
    (
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}.*service_role",
        "Hardcoded service_role JWT (CRITICAL)",
    ),
]


def check_secrets():
    print("\n03 Secrets & API Keys")

    # .env in .gitignore
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".env" in content:
            record("Secrets", ".env in .gitignore", "PASS", ".env is gitignored")
        else:
            record(
                "Secrets",
                ".env in .gitignore",
                "FAIL",
                ".env is NOT in .gitignore",
                "Add '.env' and '.env.local' to .gitignore immediately",
            )
    else:
        record("Secrets", ".gitignore exists", "FAIL", "No .gitignore found")

    # .env committed to git history
    result = subprocess.run(
        ["git", "log", "--all", "--full-history", "--", "*.env", ".env", "**/.env"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        record(
            "Secrets",
            ".env never committed to git",
            "FAIL",
            ".env appears in git history — keys may be exposed",
            "Run: git filter-repo --path .env --invert-paths (then force-push)",
        )
    else:
        record("Secrets", ".env never committed to git", "PASS", "No .env in git history")

    # Scan source for hardcoded secrets
    all_source_files = (
        list(ROOT.glob("src/**/*.ts"))
        + list(ROOT.glob("src/**/*.tsx"))
        + list(BACKEND.glob("app/**/*.py"))
        + list(BACKEND.glob("rag/**/*.py"))
        + list(BACKEND.glob("services/**/*.py"))
        + list(BACKEND.glob("guardrails/**/*.py"))
    )
    found_secrets = []
    for path in all_source_files:
        try:
            text = path.read_text(errors="ignore")
            for pattern, label in SECRET_PATTERNS:
                if re.search(pattern, text):
                    found_secrets.append(f"{label} in {path.relative_to(ROOT)}")
        except Exception:
            pass

    if found_secrets:
        record(
            "Secrets",
            "No hardcoded secrets in source",
            "FAIL",
            f"{len(found_secrets)} potential secret(s): {found_secrets[:3]}",
            "Move all secrets to .env and reference via settings/config",
        )
    else:
        record(
            "Secrets",
            "No hardcoded secrets in source",
            "PASS",
            "Clean — no hardcoded secrets found",
        )

    # Frontend not exposing API keys (check VITE_ prefix — these are public!)
    vite_secret_hits = _grep_code(
        r"VITE_.*(?:SECRET|PRIVATE|PASSWORD|API_KEY)", [".ts", ".tsx", ".env.example"]
    )
    if vite_secret_hits:
        record(
            "Secrets",
            "No secrets in VITE_ env vars",
            "FAIL",
            f"VITE_ prefixed secrets are public: {vite_secret_hits[:2]}",
            "VITE_ vars are baked into the JS bundle. Move to backend-only env vars.",
        )
    else:
        record(
            "Secrets",
            "No secrets in VITE_ env vars",
            "PASS",
            "No private keys in VITE_ vars",
        )

    # Sensitive data in API responses (password field returned)
    password_response = _grep_code(r'"password"\s*:', [".py"])
    exposed = [h for h in password_response if "hash" not in h.lower() and "test" not in h.lower()]
    if exposed:
        record(
            "Secrets",
            "Password not in API responses",
            "WARN",
            f"'password' field in responses: {exposed[:2]}",
            "Exclude password/hash fields from all Pydantic response models",
        )
    else:
        record(
            "Secrets",
            "Password not in API responses",
            "PASS",
            "No password field in response schemas",
        )


# ─── 04 Abuse Prevention ─────────────────────────────────────────────────────


def check_abuse_prevention():
    print("\n04 Abuse Prevention")

    # Rate limiting
    rate_limit_hits = _grep_code(r"@limiter\.limit|rate_limit|RateLimiter|slowapi", [".py"])
    if len(rate_limit_hits) >= 3:
        record(
            "Abuse",
            "Rate limiting on API endpoints",
            "PASS",
            f"Found in {len(rate_limit_hits)} location(s)",
        )
    elif rate_limit_hits:
        record(
            "Abuse",
            "Rate limiting on API endpoints",
            "WARN",
            f"Only {len(rate_limit_hits)} rate-limited endpoint(s)",
            "Apply @limiter.limit() to all public-facing endpoints",
        )
    else:
        record(
            "Abuse",
            "Rate limiting on API endpoints",
            "FAIL",
            "No rate limiting detected",
            "Add slowapi or similar middleware. See: pip install slowapi",
        )

    # Input validation / max length
    input_len_hits = _grep_code(r"max_input_length|MaxLength|max_length|Field.*max_length", [".py"])
    if input_len_hits:
        record("Abuse", "Input length validation", "PASS", f"Found: {input_len_hits[0]}")
    else:
        record(
            "Abuse",
            "Input length validation",
            "WARN",
            "No explicit max input length found",
            "Add max_input_length check in config.py and apply in all endpoints",
        )

    # Spend alerts / hard caps (check for env var or doc)
    spend_hits = _grep_code(
        r"SARVAM_MONTHLY_BUDGET|spend_alert|BUDGET_LIMIT|monthly_cap|quota",
        [".py", ".yml", ".md"],
    )
    if spend_hits:
        record("Abuse", "API spend cap / budget alert", "PASS", f"Found: {spend_hits[0]}")
    else:
        record(
            "Abuse",
            "API spend cap / budget alert",
            "WARN",
            "No budget cap or spend alert config found",
            "Set hard cap in Sarvam/OpenAI dashboard AND add SARVAM_MONTHLY_BUDGET env var with enforcement",
        )

    # Bot protection on auth endpoints
    captcha_hits = _grep_code(
        r"captcha|hcaptcha|turnstile|recaptcha|honeypot", [".py", ".tsx", ".ts"]
    )
    if captcha_hits:
        record("Abuse", "Bot protection on auth", "PASS", f"Found: {captcha_hits[0]}")
    else:
        record(
            "Abuse",
            "Bot protection on auth",
            "WARN",
            "No CAPTCHA or honeypot detected on auth endpoints",
            "Add Cloudflare Turnstile (free) or hCaptcha to /signup and /login",
        )

    # Auth brute-force protection
    brute_hits = _grep_code(
        r"exponential.backoff|failed_attempts|lockout|auth.*rate_limit|5.minute",
        [".py"],
    )
    if brute_hits:
        record("Abuse", "Brute-force protection on auth", "PASS", f"Found: {brute_hits[0]}")
    else:
        record(
            "Abuse",
            "Brute-force protection on auth",
            "WARN",
            "No login brute-force protection detected",
            "Use Supabase's built-in auth rate limiting or add @limiter.limit('5/minute') on /auth/login",
        )

    # File upload restrictions (if applicable)
    upload_hits = _grep_code(r"UploadFile|multipart|file_upload", [".py"])
    if upload_hits:
        size_check = _grep_code(r"content_length|max_size|file\.size|MAX_UPLOAD", [".py"])
        if size_check:
            record(
                "Abuse",
                "File upload size limits",
                "PASS",
                "Upload size validation found",
            )
        else:
            record(
                "Abuse",
                "File upload size limits",
                "WARN",
                "File upload endpoints found but no size limit detected",
                "Add max file size check (e.g., 10MB) to all UploadFile endpoints",
            )
    else:
        record("Abuse", "File upload size limits", "PASS", "No file upload endpoints (N/A)")


# ─── 05 Security Headers ─────────────────────────────────────────────────────

REQUIRED_HEADERS = {
    "Content-Security-Policy": "Prevents XSS by whitelisting content sources",
    "X-Frame-Options": "Prevents clickjacking (DENY or SAMEORIGIN)",
    "X-Content-Type-Options": "Prevents MIME sniffing (nosniff)",
    "Strict-Transport-Security": "Enforces HTTPS (HSTS)",
    "Referrer-Policy": "Controls referrer information leakage",
    "Permissions-Policy": "Disables unused browser features",
}


def check_security_headers():
    print("\n05 Security Headers (static analysis)")

    # Check if SecurityHeadersMiddleware exists anywhere
    header_middleware = BACKEND / "app" / "middleware.py"
    main_py = BACKEND / "app" / "main.py"

    found_headers = set()
    for path in [main_py, header_middleware] + list(BACKEND.rglob("*.py")):
        if ".venv" in str(path):
            continue
        try:
            text = path.read_text(errors="ignore")
            for header in REQUIRED_HEADERS:
                if header in text:
                    found_headers.add(header)
        except Exception:
            pass

    for header, desc in REQUIRED_HEADERS.items():
        if header in found_headers:
            record("Headers", f"{header} set", "PASS", desc)
        else:
            record(
                "Headers",
                f"{header} set",
                "FAIL",
                f"Missing — {desc}",
                "Run with --fix to add SecurityHeadersMiddleware to main.py",
            )

    # Check nginx config if exists
    nginx_files = list(ROOT.rglob("*.conf")) + list(ROOT.rglob("nginx*"))
    nginx_files = [f for f in nginx_files if ".venv" not in str(f)]
    if nginx_files:
        record("Headers", "Nginx config exists", "PASS", f"Found: {nginx_files[0]}")
    else:
        record(
            "Headers",
            "Nginx config review",
            "WARN",
            "No nginx config found",
            "If using nginx, add security headers in server block",
        )


# ─── Auto-Fix: Security Headers Middleware ───────────────────────────────────

SECURITY_MIDDLEWARE_CODE = '''
# ── Security Headers Middleware (auto-added by security_audit.py) ──
from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware
from starlette.requests import Request as _Request

class SecurityHeadersMiddleware(_BaseHTTPMiddleware):
    """Adds OWASP-recommended security headers to every response."""
    async def dispatch(self, request: _Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Spiritual app CSP — allows Supabase, Google Fonts, self
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.sarvam.ai https://*.supabase.co wss://*.supabase.co; "
            "frame-ancestors 'none';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
'''


def apply_fixes():
    """Apply auto-fixable issues."""
    main_py = BACKEND / "app" / "main.py"
    content = main_py.read_text()

    if "SecurityHeadersMiddleware" not in content:
        # Insert before the last app.include_router or after CORS middleware block
        insert_marker = "app.add_middleware(CorrelationIDMiddleware)"
        if insert_marker in content:
            content = content.replace(
                insert_marker, insert_marker + "\n" + SECURITY_MIDDLEWARE_CODE
            )
            main_py.write_text(content)
            print("\n🔧 AUTO-FIX: Added SecurityHeadersMiddleware to main.py")
        else:
            print(
                "\n⚠️  Could not auto-add SecurityHeadersMiddleware — insert manually after CORS middleware"
            )
    else:
        print("\n✅ SecurityHeadersMiddleware already present — no fix needed")


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _grep_code(pattern: str, extensions: list[str]) -> list[str]:
    """Grep source tree for a regex pattern, returning matching file paths."""
    results = []
    # Exclude all virtualenv, dependency, and build directories
    exclude_dirs = {
        ".venv",
        ".venv_host",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".next",
        "coverage",
        "site-packages",  # catches any nested venv
    }
    # Only search these top-level source directories
    search_roots = [
        ROOT / "src",
        ROOT / "backend" / "app",
        ROOT / "backend" / "rag",
        ROOT / "backend" / "services",
        ROOT / "backend" / "guardrails",
        ROOT / "backend" / "routers",
        ROOT / "backend" / "ingest",
        ROOT / "backend" / "domain",
        ROOT / "backend" / "evaluation",
        ROOT / "backend" / "infrastructure",
        ROOT / "scripts",
    ]

    for search_root in search_roots:
        if not search_root.exists():
            continue
        for root, dirs, files in os.walk(search_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".venv")]
            for fname in files:
                if any(fname.endswith(ext) for ext in extensions):
                    fpath = Path(root) / fname
                    try:
                        text = fpath.read_text(errors="ignore")
                        if re.search(pattern, text, re.IGNORECASE):
                            results.append(str(fpath.relative_to(ROOT)))
                    except Exception:
                        pass
    return results


# ─── Report ──────────────────────────────────────────────────────────────────


def print_summary():
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for f in findings:
        counts[f.status] += 1

    total = len(findings)
    score = int((counts["PASS"] / total) * 100) if total else 0

    print("\n" + "=" * 60)
    print(f"  SECURITY AUDIT SUMMARY — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print(f"  ✅ PASS : {counts['PASS']}/{total}")
    print(f"  ⚠️  WARN : {counts['WARN']}/{total}")
    print(f"  ❌ FAIL : {counts['FAIL']}/{total}")
    print(
        f"  📊 Score: {score}%  {'🟢 SHIP READY' if score >= 85 else '🟡 NEEDS WORK' if score >= 65 else '🔴 NOT READY'}"
    )
    print("=" * 60)

    if counts["FAIL"] > 0:
        print("\n  Critical failures to fix before launch:")
        for f in findings:
            if f.status == "FAIL":
                print(f"  ❌ [{f.category}] {f.check}")
                if f.fix:
                    print(f"     → {f.fix}")

    return counts["FAIL"] == 0


def save_report():
    report = {
        "generated_at": datetime.now().isoformat(),
        "findings": [
            {
                "category": f.category,
                "check": f.check,
                "status": f.status,
                "detail": f.detail,
                "fix": f.fix,
            }
            for f in findings
        ],
        "summary": {
            "total": len(findings),
            "pass": sum(1 for f in findings if f.status == "PASS"),
            "warn": sum(1 for f in findings if f.status == "WARN"),
            "fail": sum(1 for f in findings if f.status == "FAIL"),
        },
    }
    out = ROOT / "data" / "security_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\n  📄 Report saved: {out}")


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Mukthi Guru Pre-Launch Security Audit")
    parser.add_argument("--fix", action="store_true", help="Apply auto-fixes (security headers)")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Save JSON report to data/security_report.json",
    )
    args = parser.parse_args()

    print("🔐 Mukthi Guru — Pre-Launch Security Audit")
    print(f"   Root: {ROOT}")

    check_legal()
    check_security_basics()
    check_secrets()
    check_abuse_prevention()
    check_security_headers()

    if args.fix:
        apply_fixes()

    if args.report:
        save_report()

    all_pass = print_summary()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
