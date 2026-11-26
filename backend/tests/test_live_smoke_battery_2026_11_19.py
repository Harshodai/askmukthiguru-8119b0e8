"""Post-deploy smoke battery: pass/fail logic, offline (fake client, no network)."""

from __future__ import annotations

from scripts.ops import live_smoke_battery as smoke

_CLIP = {"route_decision": "first_person_bridge", "citations": [{"url": "x"}], "response": "q"}
_ABSTAIN = {"route_decision": "first_person_abstain", "citations": [], "response": "no"}


class _Fake(smoke.Client):
    def __init__(self, *, serve=True, helpline=True, cors=True, docs_open=False):
        super().__init__("https://api.test", "https://askmukthiguru.lovable.app")
        self.serve, self.helpline, self.cors, self.docs_open = serve, helpline, cors, docs_open

    def call(self, method, path, body=None, headers=None):
        if method == "OPTIONS":
            return 200, {"access-control-allow-origin": self.origin if self.cors else ""}, {}
        if path in smoke.CLOSED_PATHS:
            return (200 if self.docs_open and path == "/docs" else 401), {}, {}
        return 200, {}, {}

    def session(self):
        return "s"

    def ask(self, session, text, history):
        if text == smoke.CRISIS:
            return {"response": "Tele-MANAS 14416" if self.helpline else "hello", "citations": []}
        if text in (smoke.JAILBREAK, smoke.OUT_OF_CORPUS):
            return {"citations": [], "response": "outside"}
        return _CLIP if self.serve else _ABSTAIN


def test_healthy_deploy_passes():
    report = smoke.run(_Fake(), 0.7, 0.5)
    assert report.ok, report.table()


def test_each_failure_class_fails_the_battery():
    for fake, row in (
        (_Fake(serve=False), "in-domain serve rate"),
        (_Fake(helpline=False), "crisis helpline"),
        (_Fake(cors=False), "cors preflight"),
        (_Fake(docs_open=True), "closed /docs"),
    ):
        report = smoke.run(fake, 0.7, 0.5)
        failed = [n for n, ok, _ in report.rows if not ok]
        assert not report.ok and row in failed, (row, failed)


def test_an_error_or_timeout_is_never_a_refusal():
    for broken in ({"http": 500}, {"route_decision": "timeout"}, {}, {"response": ""}):
        assert not smoke.refused(broken), broken
    assert smoke.refused({"route_decision": "blocked", "response": "I stay with the teachings."})


def test_crisis_with_a_teacher_clip_fails():
    assert smoke.crisis_ok({"response": "Tele-MANAS 14416", "citations": []})
    assert not smoke.crisis_ok({"response": "Tele-MANAS 14416", "citations": [{"url": "x"}]})
    assert not smoke.crisis_ok({"http": 500, "error": "14416"})


def test_inline_200_reply_is_a_real_answer(monkeypatch):
    """The crisis pre-check answers with HTTP 200 and no job; that is not an error."""
    client = smoke.Client("https://api.test", "https://askmukthiguru.lovable.app")
    monkeypatch.setattr(client, "call", lambda *a, **k: (200, {}, {"response": "Tele-MANAS 14416"}))
    assert smoke.crisis_ok(client.ask("s", smoke.CRISIS, []))
    monkeypatch.setattr(client, "call", lambda *a, **k: (500, {}, {"detail": "boom"}))
    assert not smoke.answered(client.ask("s", "q", []))


def test_served_requires_non_empty_response():
    assert smoke.served(
        {"route_decision": "first_person_bridge", "citations": [{"url": "x"}], "response": "valid"}
    )
    assert not smoke.served(
        {"route_decision": "first_person_bridge", "citations": [{"url": "x"}], "response": ""}
    )
    assert not smoke.served(
        {"route_decision": "first_person_bridge", "citations": [{"url": "x"}], "response": "   "}
    )


def test_transport_url_error_recorded(monkeypatch):
    import urllib.error

    client = smoke.Client("https://api.test", "https://askmukthiguru.lovable.app")

    def _fail(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    status, headers, body = client.call("GET", "/api/healthz")
    assert status == 0
    assert body.get("http") == 0
    assert "connection refused" in body.get("error", "")
    assert not smoke.answered(body)


def test_client_reads_faculty_code_from_settings(monkeypatch):
    from app.config import settings

    monkeypatch.delenv("FACULTY_ACCESS_CODE", raising=False)
    monkeypatch.setattr(settings, "faculty_access_code", "test-faculty-code")
    client = smoke.Client("https://api.test", "https://askmukthiguru.lovable.app")
    assert client.faculty == "test-faculty-code"


def test_system_unavailable_causes_provider_outage_failure():
    outage_resp = {
        "route_decision": "first_person_abstain",
        "citations": [],
        "response": "I couldn't finish checking the teachings for this question just now.",
        "verification": {"passed": False, "abstain_cause": "system_unavailable"},
    }

    class _OutageClient(smoke.Client):
        def __init__(self):
            super().__init__("https://api.test", "https://askmukthiguru.lovable.app")

        def call(self, method, path, body=None, headers=None):
            if method == "OPTIONS":
                return 200, {"access-control-allow-origin": self.origin}, {}
            return 200, {}, {}

        def session(self):
            return "s"

        def ask(self, session, text, history):
            if text == smoke.CRISIS:
                return {"response": "Tele-MANAS 14416", "citations": []}
            if text in (smoke.JAILBREAK, smoke.OUT_OF_CORPUS):
                return {"citations": [], "response": "outside"}
            return outage_resp

    report = smoke.run(_OutageClient(), 0.7, 0.5)
    assert not report.ok
    table = report.table()
    assert "PROVIDER OUTAGE" in table
    assert "system_unavailable" in table


def test_genuine_abstain_reported_with_cause():
    genuine_abstain = {
        "route_decision": "first_person_abstain",
        "citations": [],
        "response": "I stay with the teachings.",
        "verification": {"passed": False, "abstain_cause": "no_evidence"},
    }

    class _AbstainClient(smoke.Client):
        def __init__(self):
            super().__init__("https://api.test", "https://askmukthiguru.lovable.app")

        def call(self, method, path, body=None, headers=None):
            if method == "OPTIONS":
                return 200, {"access-control-allow-origin": self.origin}, {}
            return 200, {}, {}

        def session(self):
            return "s"

        def ask(self, session, text, history):
            if text == smoke.CRISIS:
                return {"response": "Tele-MANAS 14416", "citations": []}
            if text in (smoke.JAILBREAK, smoke.OUT_OF_CORPUS):
                return {"citations": [], "response": "outside"}
            return genuine_abstain

    report = smoke.run(_AbstainClient(), 0.7, 0.5)
    assert not report.ok
    table = report.table()
    assert "no_evidence" in table
    assert "PROVIDER OUTAGE" not in table
