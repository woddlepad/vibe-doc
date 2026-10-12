"""Offline integration checks for the voice demo's privacy and tool lifecycle."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from rsi import live
from rsi.cases import splits


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RSI_LIVE_PASSWORD", raising=False)
    return TestClient(live.create_app())


def test_ui_and_train_only_case_library(client):
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/realtime.js").status_code == 200
    cases = client.get("/api/cases").json()
    assert {c["id"] for c in cases} == set(splits()["train"])
    assert all("answer" not in c and "notes" not in c for c in cases)
    card = client.get("/api/cases/mqx-004").json()
    assert card["answer"] == "Acute interstitial nephritis"
    assert "amoxicillin" in json.dumps(card["notes"])
    assert client.get(f"/api/cases/{splits()['test'][0]}").status_code == 404
    assert client.get(f"/api/cases/{splits()['dev'][0]}").status_code == 404
    assert client.get("/api/cases/not-a-case").status_code == 404
    assert client.get("/assets/../live.py").status_code == 404


def test_missing_key_does_not_attempt_openai(client, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("No upstream request should be made without a key")

    monkeypatch.setattr(httpx.AsyncClient, "post", unexpected)
    assert client.get("/api/config").json()["configured"] is False
    response = client.post("/api/sessions", json={"case_id": "mqx-004", "sdp": "v=0\r\ntest-offer"})
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_session_creation_keeps_patient_and_gold_out_of_doctor_context(client, monkeypatch):
    sent = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-not-for-the-browser")

    async def post(self, url, **kwargs):
        sent.append((url, kwargs))
        return httpx.Response(201, text="v=0\r\nanswer-sdp")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    response = client.post("/api/sessions", json={"case_id": "mqx-004", "sdp": "v=0\r\ntest-offer"})
    assert response.status_code == 200
    body = response.json()
    assert body["sdp"] == "v=0\r\nanswer-sdp" and len(body["id"]) >= 32
    assert "test-secret" not in response.text
    url, kwargs = sent[0]
    assert url.endswith("/realtime/calls")
    assert kwargs["headers"]["Authorization"] == "Bearer test-secret-not-for-the-browser"
    config = json.loads(kwargs["files"]["session"][1])
    assert config["type"] == "realtime"
    assert config["audio"]["input"]["turn_detection"]["interrupt_response"] is True
    serialized = json.dumps(config)
    for private in ["Acute interstitial nephritis", "amoxicillin", "cephalexin", "retired school teacher", "3% binucleated"]:
        assert private not in serialized
    assert "62-year-old woman" in serialized
    assert {tool["name"] for tool in config["tools"]} == {"examine", "order_test", "submit_diagnosis"}
    # Read-only UI endpoints contain no server secret either.
    assert "test-secret" not in client.get("/api/config").text
    assert client.delete(f"/api/sessions/{body['id']}").json() == {"ended": True}
    assert client.get(f"/api/sessions/{body['id']}/result").status_code == 404


def seeded(client, case_id="mqx-004"):
    visit = live.Visit(live.demo_cases()[case_id])
    client.app.state.visits["visit-token"] = visit
    return visit


def call(client, name, arguments, call_id="call-1"):
    return client.post("/api/sessions/visit-token/tools", json={"name": name, "arguments": arguments, "call_id": call_id})


def test_selected_findings_are_original_redacted_records_not_generated_text(client, monkeypatch):
    visit = seeded(client, "mqx-001")
    sent = []

    async def select(instructions, payload, schema, name):
        sent.append(payload)
        # Select the MRI findings, but not its comments; return IDs, never new values.
        return {"ids": ["0", "0"]}

    monkeypatch.setattr(live, "structured", select)
    response = call(client, "order_test", {"request": "brain MRI"})
    assert response.status_code == 200
    output = response.json()["output"]
    assert len(output["findings"]) == 1
    assert "Progressive" not in json.dumps(sent)
    assert "PML" not in json.dumps(sent)
    assert "encephalopathy" not in response.text.lower()
    assert "PML" not in response.text
    assert output["requests_left"] == 9
    assert visit.requests == 1
    assert call(client, "order_test", {"request": "brain MRI"}).json() == response.json()
    assert len(sent) == 1 and visit.requests == 1  # retry is idempotent


def test_missing_findings_and_budget(client, monkeypatch):
    visit = seeded(client)

    async def absent(*args):
        return []

    monkeypatch.setattr(live, "requested_findings", absent)
    output = call(client, "examine", {"request": "fundoscopy"}).json()["output"]
    assert not output["findings"]
    assert "Do not assume normal" in output["message"]
    visit.requests = live.MAX_REQUESTS
    response = call(client, "order_test", {"request": "a test"}, "call-2")
    assert response.json()["output"]["status"] == "budget_exhausted"
    assert visit.requests == live.MAX_REQUESTS


def test_submission_grade_is_human_only_and_closes_tools(client, monkeypatch):
    visit = seeded(client)

    async def no_helper(*args):
        pytest.fail("Exact matches need no helper model")

    monkeypatch.setattr(live, "structured", no_helper)
    diagnosis = {"diagnosis": "acute interstitial nephritis", "reasoning": "Drug exposure and renal findings.", "differential": ["Pyelonephritis"]}
    response = call(client, "submit_diagnosis", diagnosis)
    assert response.json()["output"]["status"] == "submitted"
    assert "correct" not in response.text and "answer" not in response.json()["output"]
    assert "acute interstitial nephritis" not in response.text.lower()
    result = client.get("/api/sessions/visit-token/result").json()
    assert result["answer"] == visit.case.diagnosis
    assert result["verdict"]["correct"] is True
    assert result["assessment"] == diagnosis
    assert client.get("/api/sessions/visit-token/result").json() == result
    assert call(client, "order_test", {"request": "anything"}, "call-2").json()["output"]["status"] == "closed"
    assert visit.requests == 0


def test_nonexact_grade_is_separate_and_retryable(client, monkeypatch):
    visit = seeded(client)
    visit.submission = {"diagnosis": "AIN", "reasoning": "Drug exposure.", "differential": []}
    calls = []

    async def grade(instructions, payload, schema, name):
        calls.append(payload)
        if len(calls) == 1:
            raise live.HTTPException(502, "Temporary failure")
        return {"correct": True, "rationale": "AIN is the abbreviation."}

    monkeypatch.setattr(live, "structured", grade)
    assert client.get("/api/sessions/visit-token/result").status_code == 502
    assert visit.submission["diagnosis"] == "AIN" and visit.verdict is None
    result = client.get("/api/sessions/visit-token/result").json()
    assert result["verdict"]["correct"] is True
    assert calls[-1] == {"prediction": "AIN", "reference": visit.case.diagnosis}
    client.get("/api/sessions/visit-token/result")
    assert len(calls) == 2  # no repeat charges once graded


def test_invalid_tool_arguments_and_multi_diagnosis(client):
    visit = seeded(client)
    assert call(client, "examine", {}).status_code == 422
    assert call(client, "order_test", {"request": 5}).status_code == 422
    assert call(client, "submit_diagnosis", {"diagnosis": "x"}).status_code == 422
    assert call(client, "read_answer", {}).status_code == 422
    multi = {"diagnosis": "AIN or pyelonephritis", "reasoning": "Unsure", "differential": []}
    assert call(client, "submit_diagnosis", multi).json()["output"]["status"] == "invalid"
    assert visit.submission is None
    assert client.get("/api/sessions/visit-token/result").json()["submitted"] is False


def test_selector_rejects_invalid_ids(client, monkeypatch):
    visit = seeded(client)

    async def invalid(*args):
        return {"ids": ["-1", "9999"]}

    monkeypatch.setattr(live, "structured", invalid)
    assert call(client, "order_test", {"request": "urinalysis"}).status_code == 502
    assert visit.requests == 0  # errors do not spend the request budget


def test_unicode_diagnosis_is_redacted_before_json_serialization(monkeypatch):
    from rsi.cases import Case

    case = Case("example", "Interview the patient", {"Demographics": "Adult", "History": "Crohn’s disease"},
                {}, {"Biopsy": "Consistent with Crohn’s disease."}, "Crohn’s disease")
    assert "Crohn" not in json.dumps(live.patient_card(case)["notes"])
    seen = []

    async def select(instructions, payload, schema, name):
        seen.append(payload)
        return {"ids": ["0"]}

    monkeypatch.setattr(live, "structured", select)
    findings = asyncio.run(live.requested_findings(case, "order_test", "biopsy"))
    assert "Crohn" not in json.dumps(seen) and "Crohn" not in json.dumps(findings)


def test_all_training_findings_hide_answer_in_names_and_values(monkeypatch):
    from rsi.judge import mentions

    async def audit(instructions, payload, schema, name):
        assert not mentions(json.dumps(payload["records"], ensure_ascii=False), current.diagnosis, current.aliases), current.id
        return {"ids": []}

    monkeypatch.setattr(live, "structured", audit)
    for current in live.demo_cases().values():
        for kind in ("examine", "order_test"):
            asyncio.run(live.requested_findings(current, kind, "a recorded finding"))


def test_local_origin_and_expiration(client):
    visit = seeded(client)
    assert client.post("/api/sessions", headers={"Origin": "https://unrelated.example"}, json={}).status_code == 403
    response = client.get("/")
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    visit.created = time.monotonic() - live.SESSION_TTL - 1
    assert client.get("/api/sessions/visit-token/result").status_code == 404
    assert "visit-token" not in client.app.state.visits


def test_password_protects_ui_and_all_api_calls(monkeypatch):
    monkeypatch.setenv("RSI_LIVE_PASSWORD", "test demo phrase")
    client = TestClient(live.create_app(), base_url="https://demo.example")
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/login").status_code == 200
    assert client.get("/assets/login.js").status_code == 200
    for path in ("/api/config", "/api/cases", "/api/cases/mqx-004", "/api/sessions/example/result"):
        assert client.get(path).status_code == 401
    assert client.post("/api/sessions", json={}).status_code == 401
    assert client.post("/api/sessions/example/tools", json={}).status_code == 401
    assert client.delete("/api/sessions/example").status_code == 401
    client.cookies.set("doctor_live_access", "test demo phrase")
    assert client.get("/api/cases").status_code == 401  # password itself is not a session cookie
    client.cookies.clear()
    assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    signed = client.post("/api/login", json={"password": "test demo phrase"})
    assert signed.status_code == 200
    cookie = signed.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "test demo phrase" not in cookie
    assert client.get("/").status_code == 200
    assert client.get("/api/config").status_code == 200
    assert client.get("/api/cases/mqx-004").status_code == 200
    assert client.get("/api/sessions/missing/result").status_code == 404  # reaches application after login
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/config").status_code == 401


def test_password_login_rejects_cross_origin_and_limits_guesses(monkeypatch):
    monkeypatch.setenv("RSI_LIVE_PASSWORD", "test demo phrase")
    client = TestClient(live.create_app())
    blocked = client.post("/api/login", headers={"Origin": "https://unrelated.example"}, json={"password": "test demo phrase"})
    assert blocked.status_code == 403
    assert not client.cookies
    for _ in range(5):
        assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"password": "wrong"}).status_code == 429
    assert client.get("/api/config").status_code == 401


def test_upstream_error_does_not_expose_secret(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    async def denied(self, url, **kwargs):
        return httpx.Response(401, json={"error": {"message": "test-secret was wrong"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", denied)
    response = client.post("/api/sessions", json={"case_id": "mqx-004", "sdp": "v=0\r\ntest-offer"})
    assert response.status_code == 502
    assert "test-secret" not in response.text
    assert not client.app.state.visits


def test_structured_helper_request_shape(monkeypatch):
    calls = []

    async def post(path, **kwargs):
        calls.append((path, kwargs))
        return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ids": ["0"]}'}]}]})

    monkeypatch.setattr(live, "openai_post", post)
    schema = {"type": "object"}
    assert asyncio.run(live.structured("select", {"request": "test"}, schema, "ids")) == {"ids": ["0"]}
    body = calls[0][1]["json_body"]
    assert calls[0][0] == "responses" and body["store"] is False
    assert body["text"]["format"] == {"type": "json_schema", "name": "ids", "strict": True, "schema": schema}
