"""Regression tests for the 2026-11-24 Antigravity end-to-end remediation PR.

Designed to run both under pytest (CI / Python 3.12 venv) and standalone via
``python3 -m unittest`` in dependency-constrained environments.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestAnthropicGatewayActivationContract(unittest.TestCase):
    """P0: ANTHROPIC_API_KEY alone must NEVER activate direct Anthropic generation."""

    def _load_gateway_module(self):
        # Load anthropic_gateway.py directly so tests run even when pydantic v2 / aiohttp are absent
        import importlib.util

        if "aiohttp" not in sys.modules:
            sys.modules["aiohttp"] = types.ModuleType("aiohttp")
        gw_path = BACKEND_DIR / "services" / "gateways" / "anthropic_gateway.py"
        spec = importlib.util.spec_from_file_location("_test_anthropic_gateway", gw_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_api_key_alone_does_not_activate_gateway(self):
        mod = self._load_gateway_module()
        cfg = mod.AnthropicGatewayConfig(
            api_key="sk-ant-test-key",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-6",
            api_version="2023-06-01",
            beta_features=("prompt-caching-2024-07-31",),
            max_tokens=1024,
            temperature=0.7,
            timeout_s=30,
            system_cache_ttl="1h",
            extended_thinking_enabled=False,
            extended_thinking_budget_tokens=0,
            enabled=False,
        )
        gw = mod.AnthropicGateway(cfg)
        self.assertFalse(gw.enabled)

    def test_explicit_flag_plus_key_activates_gateway(self):
        mod = self._load_gateway_module()
        cfg = mod.AnthropicGatewayConfig(
            api_key="sk-ant-test-key",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-6",
            api_version="2023-06-01",
            beta_features=("prompt-caching-2024-07-31",),
            max_tokens=1024,
            temperature=0.7,
            timeout_s=30,
            system_cache_ttl="1h",
            extended_thinking_enabled=False,
            extended_thinking_budget_tokens=0,
            enabled=True,
        )
        gw = mod.AnthropicGateway(cfg)
        self.assertTrue(gw.enabled)

    def test_explicit_flag_without_key_stays_disabled(self):
        mod = self._load_gateway_module()
        cfg = mod.AnthropicGatewayConfig(
            api_key="",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-6",
            api_version="2023-06-01",
            beta_features=("prompt-caching-2024-07-31",),
            max_tokens=1024,
            temperature=0.7,
            timeout_s=30,
            system_cache_ttl="1h",
            extended_thinking_enabled=False,
            extended_thinking_budget_tokens=0,
            enabled=True,
        )
        gw = mod.AnthropicGateway(cfg)
        self.assertFalse(gw.enabled)


class TestConfigDefaultsAndFingerprint(unittest.TestCase):
    """P1: Reconciled OFF defaults and deterministic runtime_config_fingerprint."""

    def test_expansion_flags_and_anthropic_gateway_default_off_in_source(self):
        src = (BACKEND_DIR / "app" / "config.py").read_text(encoding="utf-8")
        for line in (
            "first_person_enrichment_window_enabled: bool = False",
            "first_person_graph_expansion_enabled: bool = False",
            "first_person_okf_expansion_enabled: bool = False",
            "first_person_cross_video_diversity_enabled: bool = False",
            "anthropic_gateway_enabled: bool = False",
            "first_person_llm_fallback_enabled: bool = False",
        ):
            self.assertIn(line, src, f"Expected default declaration missing: {line}")

    def test_runtime_config_fingerprint_is_deterministic_and_sensitive(self):
        from app import runtime_budget

        base = SimpleNamespace(
            llm_provider="openrouter",
            anthropic_gateway_enabled=False,
            anthropic_gateway_model="claude-sonnet-4-6",
            first_person_serving_posture="v13_shadow",
            first_person_mode="retrieval_only",
            first_person_collection="first_person_v13_shadow",
            first_person_context_collection="first_person_v13_shadow",
            first_person_context_harness_enabled=True,
            first_person_context_terminal_enabled=True,
            first_person_llm_fallback_enabled=False,
            first_person_answerability_check_enabled=True,
            first_person_relevance_min_score=2,
            first_person_relevance_model="anthropic/claude-haiku-5.5",
            first_person_context_use_sparse=False,
            first_person_hyde_enabled=True,
            first_person_comparative_judge_enabled=False,
            first_person_enrichment_window_enabled=False,
            first_person_graph_expansion_enabled=False,
            first_person_okf_expansion_enabled=False,
            first_person_cross_video_diversity_enabled=False,
            first_person_teaching_unit_graph_enabled=False,
            first_person_multipart_enabled=False,
        )
        fp1 = runtime_budget.runtime_config_fingerprint(base)
        fp2 = runtime_budget.runtime_config_fingerprint(base)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 16)

        changed = SimpleNamespace(**{**base.__dict__, "first_person_okf_expansion_enabled": True})
        self.assertNotEqual(fp1, runtime_budget.runtime_config_fingerprint(changed))


class TestCsrfSessionBinding(unittest.TestCase):
    """P0: validate_csrf_token must bind token to session_or_user_id and reject future timestamps."""

    def _load_csrf_funcs(self):
        # Extract and test validate_csrf_token & generate_csrf_token cleanly even without redis installed
        import hmac
        import secrets

        src = (BACKEND_DIR / "app" / "security_utils.py").read_text(encoding="utf-8")
        # Locate generate_csrf_token and validate_csrf_token via AST to test actual repo code
        import ast

        tree = ast.parse(src)
        ns = {"hmac": hmac, "hashlib": hashlib, "secrets": secrets, "time": time}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in (
                "generate_csrf_token",
                "validate_csrf_token",
            ):
                mod_ast = ast.Module(body=[node], type_ignores=[])
                exec(compile(mod_ast, "security_utils.py", "exec"), ns)
        return ns["generate_csrf_token"], ns["validate_csrf_token"]

    def test_csrf_rejects_cross_user_token(self):
        gen, val = self._load_csrf_funcs()
        secret = "super-secret-key"
        token = gen(secret, "user-alice")
        self.assertTrue(val(token, secret, "user-alice"))
        self.assertFalse(val(token, secret, "user-bob"))

    def test_csrf_rejects_future_timestamp(self):
        import hmac

        _, val = self._load_csrf_funcs()
        secret = "super-secret-key"
        future_ts = str(int(time.time()) + 3600)
        payload = f"{future_ts}.deadbeef.user-alice"
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        self.assertFalse(val(f"{payload}.{sig}", secret, "user-alice"))


class TestAsrCleanerDualHash(unittest.TestCase):
    """P1: clean_clips must update transcript_hash, source_text_hash, and span_text_sha256 atomically."""

    def test_clean_clips_updates_all_hashes(self):
        from ingest.verbatim.asr_cleaner import clean_clips

        clip = {
            "verbatim_text": "So, So the mind is peaceful peaceful.",
            "transcript_hash": "stale-1",
            "source_text_hash": "stale-2",
            "span_text_sha256": "stale-3",
        }
        clean_clips([clip])
        expected = hashlib.sha256(clip["verbatim_text"].encode("utf-8")).hexdigest()
        self.assertEqual(clip["transcript_hash"], expected)
        self.assertEqual(clip["source_text_hash"], expected)
        self.assertEqual(clip["span_text_sha256"], expected)


class TestMemgraphSyncDriverExpansion(unittest.TestCase):
    """P1: expand_teaching_units must work with standard synchronous Neo4j/Memgraph driver."""

    def test_expand_teaching_units_handles_sync_driver(self):
        from services.first_person_graph_expansion import expand_teaching_units

        class FakeSyncSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                assert "tenant_id" in kwargs
                return [{"span_id": "span-neighbor-1"}, {"span_id": "span-neighbor-2"}]

        class FakeSyncDriver:
            def session(self):
                return FakeSyncSession()

        fake_deps = types.ModuleType("app.dependencies")
        fake_deps.get_container = lambda: SimpleNamespace(neo4j_driver=FakeSyncDriver())
        prev_deps = sys.modules.get("app.dependencies")
        sys.modules["app.dependencies"] = fake_deps
        try:
            out = expand_teaching_units(
                ["span-seed-1"],
                max_hops=1,
                max_nodes=5,
                timeout_s=2.0,
            )
        finally:
            if prev_deps is None:
                sys.modules.pop("app.dependencies", None)
            else:
                sys.modules["app.dependencies"] = prev_deps
        self.assertEqual(out, ["span-neighbor-1", "span-neighbor-2"])


class TestOntologyGuardrailsFailClosed(unittest.TestCase):
    """P2: OntologyConstraintChecker must fail closed on DB exception and deduplicate pairs."""

    def test_db_error_returns_invalid_report(self):
        from services.ontology_guardrails import OntologyConstraintChecker

        class BrokenDriver:
            def session(self):
                raise RuntimeError("memgraph unavailable")

        checker = OntologyConstraintChecker(BrokenDriver())
        report = checker.check_constraints(entities=["Suffering State", "Beautiful State"])
        self.assertFalse(report.is_valid)
        self.assertTrue(any(v.violation_type == "ONTOLOGY_CHECK_ERROR" for v in report.violations))


class TestInfraAndScriptParity(unittest.TestCase):
    """P1/P2: Dockerfile healthz, docker-compose.prod.yml OOM/Redis fixes, and ops script parity."""

    def test_dockerfile_healthcheck_uses_healthz(self):
        df = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("/api/healthz", df)
        self.assertNotIn("/api/health ||", df)

    def test_prod_compose_avoids_oom_and_redis_cli_password_arg(self):
        import yaml

        prod = yaml.safe_load((REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
        backend_env = prod["services"]["backend"]["environment"]
        self.assertIn("WEB_CONCURRENCY=${WEB_CONCURRENCY:-1}", backend_env)
        self.assertIn("FIRST_PERSON_LLM_FALLBACK_ENABLED=false", backend_env)
        self.assertEqual(prod["services"]["backend"]["deploy"]["resources"]["limits"]["memory"], "4G")
        redis_hc = " ".join(prod["services"]["redis"]["healthcheck"]["test"])
        self.assertIn("REDISCLI_AUTH", redis_hc)
        self.assertNotIn(" -a ", redis_hc)

    def test_data_quality_audit_copies_are_byte_identical(self):
        a = (REPO_ROOT / "backend" / "scripts" / "ops" / "data_quality_audit.py").read_bytes()
        b = (REPO_ROOT / "scripts" / "ops" / "data_quality_audit.py").read_bytes()
        self.assertEqual(a, b)



class TestIndependentReviewRegressions(unittest.TestCase):
    """Covers blockers & warnings caught during Phase 4 independent review."""

    def test_anthropic_gateway_from_settings_respects_env_opt_in(self):
        import importlib.util

        if "aiohttp" not in sys.modules:
            sys.modules["aiohttp"] = types.ModuleType("aiohttp")
        gw_path = BACKEND_DIR / "services" / "gateways" / "anthropic_gateway.py"
        spec = importlib.util.spec_from_file_location("_test_anthropic_gw_env", gw_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        old_key = os.environ.get("ANTHROPIC_API_KEY")
        old_en = os.environ.get("ANTHROPIC_GATEWAY_ENABLED")
        try:
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-env-test"
            os.environ["ANTHROPIC_GATEWAY_ENABLED"] = "false"
            gw = mod.AnthropicGateway.from_settings()
            self.assertFalse(gw.enabled)

            os.environ["ANTHROPIC_GATEWAY_ENABLED"] = "true"
            gw2 = mod.AnthropicGateway.from_settings()
            self.assertTrue(gw2.enabled)
        finally:
            if old_key is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            if old_en is None:
                os.environ.pop("ANTHROPIC_GATEWAY_ENABLED", None)
            else:
                os.environ["ANTHROPIC_GATEWAY_ENABLED"] = old_en

    def test_boundary_defects_receives_tokens_and_catches_dangling_conjunction(self):
        from ingest.verbatim.boundaries import boundary_defects

        defects = boundary_defects("The mind settles and".split())
        self.assertIn("tail_dangling_word", defects)

    def test_teaching_unit_graph_queries_enforce_tenant_id(self):
        import json

        qpath = BACKEND_DIR / "config" / "teaching_unit_graph_queries.json"
        if qpath.exists():
            data = json.loads(qpath.read_text(encoding="utf-8"))
            for key, cypher in data.get("queries", {}).items():
                if "neighbor:TUTeachingUnit" in cypher:
                    self.assertIn("$tenant_id", cypher, f"Query {key} missing $tenant_id filter")

    def test_ontology_mutual_exclusivity_query_deduplicates_pairs(self):
        from services.ontology_guardrails import CHECK_MUTUAL_EXCLUSIVITY_CYPHER

        self.assertIn("coalesce(a.entity_id, a.name) < coalesce(b.entity_id, b.name)", CHECK_MUTUAL_EXCLUSIVITY_CYPHER)

    def test_runtime_budget_preserves_v10_only_warning_label(self):
        from app import runtime_budget

        s = SimpleNamespace(
            first_person_answerability_check_enabled=True,
            is_production=True,
            first_person_serving_posture="",
            first_person_context_harness_enabled=True,
            first_person_context_terminal_enabled=True,
            first_person_collection="first_person_v10",
        )
        warnings = runtime_budget.serving_gate_warnings(s)
        self.assertTrue(any("v10-only context harness" in w for w in warnings))

if __name__ == "__main__":
    unittest.main()
