"""The HTTP API (WP9a; ADR-0022, ADR-0024): contract tests with FastAPI's test client, the
error format, CSRF tokens, demo isolation and limits, LLM settings that never show the key."""

import json
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from app_cases import ABSENCE_CHECKIN, small
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentinel.app.api import create_app
from sentinel.app.config import AppConfig, Limits
from sentinel.app.llm import LlmSettings
from sentinel.app.models import CheckIn, Settings
from sentinel.app.services import Services
from sentinel.llm import FakeLlmClient, LlmCache, LlmClient, Message

KEY = "gsk_" + "testkey0123456789abcdef"  # pragma: allowlist secret


def client(
    config: AppConfig, services: Services | None = None, app: FastAPI | None = None
) -> tuple[TestClient, dict[str, str]]:
    """A test client (a visitor) of a new app, or of `app`, and its session's CSRF header."""
    test = TestClient(create_app(config, services) if app is None else app)
    token = test.get("/api/session").json()["csrf_token"]
    return test, {"X-CSRF-Token": token}


def local(tmp_path: Path) -> AppConfig:
    return AppConfig(data_dir=tmp_path / "local", inline_jobs=True)


def demo(tmp_path: Path, **limits: Any) -> AppConfig:
    return AppConfig(
        data_dir=tmp_path / "demo",
        demo=True,
        inline_jobs=True,
        showcase=False,
        limits=Limits(**limits),
    )


def _definition(**update: Any) -> dict[str, Any]:
    return small().model_copy(update=update).model_dump(mode="json")


def test_health_session_and_the_error_format(tmp_path: Path) -> None:
    test, csrf = client(local(tmp_path))
    assert test.get("/api/health").json() == {"status": "ok", "version": "1.0.0", "demo": False}
    session = test.get("/api/session").json()
    assert session["demo"] is False and len(session["csrf_token"]) == 64
    missing = test.get("/api/projects/nope?lang=pl")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {"code": "project_not_found", "message": "Nie ma takiego projektu.", "details": []}
    }
    route = test.get("/api/nothing-here")
    assert route.status_code == 404 and route.json()["error"]["code"] == "not_found"
    invalid = test.post("/api/projects", json={"name": "x"}, headers=csrf)
    assert invalid.status_code == 422
    error = invalid.json()["error"]
    assert error["code"] == "invalid_request"
    assert {d["message"] for d in error["details"]} == {"start is required."}
    refused = test.post("/api/projects", json=_definition())
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "csrf_failed"
    forged = test.post("/api/projects", json=_definition(), headers={"X-CSRF-Token": "0" * 64})
    assert forged.status_code == 403


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_a_live_project_through_the_api(tmp_path: Path) -> None:
    test, csrf = client(local(tmp_path))
    created = test.post("/api/projects", json=_definition(), headers=csrf)
    assert created.status_code == 201
    project = created.json()
    pid = project["id"]
    assert project["kind"] == "live" and project["has_plan"] is False and project["issues"] == []
    assert [p["id"] for p in test.get("/api/projects").json()] == [pid]
    plan = test.post(f"/api/projects/{pid}/plan", headers=csrf)
    assert plan.status_code == 202 and plan.json()["status"] == "done"
    assert plan.json()["result"]["makespan"] == 9
    checkin = test.post(
        f"/api/projects/{pid}/checkins",
        content=ABSENCE_CHECKIN.model_dump_json(),
        headers={**csrf, "content-type": "application/json"},
    )
    assert checkin.status_code == 200
    body = checkin.json()
    assert body["recommendation_job"]["status"] == "done"
    view = test.get(f"/api/projects/{pid}").json()
    assert view["as_of"] == "2026-11-05" and view["tracking"] is True
    seq = view["open_recommendation"]
    recommendation = next(r for r in view["recommendations"] if r["seq"] == seq)
    assert recommendation["title"] == "Let Cleo take over for the absent crew of “Build API”"
    assert recommendation["needs_approval"] is True
    assert recommendation["with_action"]["p_on_time"] > recommendation["without"]["p_on_time"]
    approved = test.post(
        f"/api/projects/{pid}/recommendations/{seq}/decision",
        json={"verdict": "approve"},
        headers=csrf,
    )
    assert approved.status_code == 200
    task = next(t for t in approved.json()["tasks"] if t["key"] == "T1")
    assert task["crew_names"] == ["Cleo", "Ben"] and task["state"] == "in_progress"
    again = test.post(
        f"/api/projects/{pid}/recommendations/{seq}/decision",
        json={"verdict": "reject"},
        headers=csrf,
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "recommendation_closed"
    types = [e["type"] for e in test.get(f"/api/projects/{pid}/events").json()]
    assert types == ["created", "baseline", "checkin", "recommendation", "decision"]
    forecast = test.post(f"/api/projects/{pid}/forecast", headers=csrf).json()
    assert forecast["status"] == "done" and forecast["result"]["rollouts"] == 200
    assert forecast["result"]["drivers"]
    csv_text = test.get(f"/api/projects/{pid}/plan.csv").text
    assert csv_text.splitlines()[1].startswith("T1,Build API,started,,,2026-11-02,")
    cockpit = test.post(f"/api/projects/{pid}/cockpit", headers=csrf).json()
    assert cockpit["status"] == "done"
    page = test.get(cockpit["result"]["html"])
    assert page.status_code == 200 and "<svg" in page.text and "Build API" in page.text
    exported = test.get(f"/api/projects/{pid}/export.json").json()
    imported = test.post(
        "/api/import/json",
        files={"file": ("p.json", json.dumps(exported).encode())},
        headers=csrf,
    )
    assert imported.status_code == 201
    copy = imported.json()
    assert copy["id"] != pid and copy["source"] == "json"
    assert copy["tasks"] == approved.json()["tasks"]
    assert test.delete(f"/api/projects/{pid}", headers=csrf).status_code == 204
    assert test.get(f"/api/projects/{pid}").status_code == 404


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_checkin_and_definition_errors_are_user_readable(tmp_path: Path) -> None:
    test, csrf = client(local(tmp_path))
    pid = test.post("/api/projects", json=_definition(), headers=csrf).json()["id"]
    unplanned = test.post(
        f"/api/projects/{pid}/checkins?lang=pl",
        content=ABSENCE_CHECKIN.model_dump_json(),
        headers={**csrf, "content-type": "application/json"},
    )
    assert unplanned.status_code == 422
    assert unplanned.json()["error"]["message"] == "Najpierw zbuduj plan."
    broken = _definition()
    broken["tasks"][2]["predecessors"] = ["T1", "T9"]
    issues = test.post("/api/projects/validate", json=broken, headers=csrf).json()
    assert [i["code"] for i in issues] == ["unknown_predecessor"]
    assert issues[0]["message"] == "“Test” comes after T9, which is not a task of this project."
    test.put(f"/api/projects/{pid}/definition", json=broken, headers=csrf)
    plan = test.post(f"/api/projects/{pid}/plan", headers=csrf)
    assert plan.status_code == 422 and plan.json()["error"]["code"] == "unknown_predecessor"
    test.put(f"/api/projects/{pid}/definition", json=_definition(), headers=csrf)
    assert test.post(f"/api/projects/{pid}/plan", headers=csrf).json()["status"] == "done"
    test.post(
        f"/api/projects/{pid}/checkins",
        content=CheckIn(date=date(2026, 11, 3)).model_dump_json(),
        headers={**csrf, "content-type": "application/json"},
    )
    frozen = test.put(
        f"/api/projects/{pid}/definition", json=_definition(name="Renamed"), headers=csrf
    )
    assert frozen.status_code == 200 and frozen.json()["name"] == "Renamed"
    longer = _definition()
    longer["tasks"][0]["duration"] = 7
    refused = test.put(f"/api/projects/{pid}/definition", json=longer, headers=csrf)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "structure_frozen"


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_csv_import_and_templates(tmp_path: Path) -> None:
    test, csrf = client(local(tmp_path))
    template = test.get("/api/templates/tasks.csv")
    assert template.status_code == 200 and template.text.startswith("id,name,duration_days")
    team = test.get("/api/templates/team.csv").content
    imported = test.post(
        "/api/import/csv",
        files={"tasks": ("tasks.csv", template.content), "team": ("team.csv", team)},
        data={"name": "From CSV", "start": "2026-11-02", "deadline": "2026-11-30"},
        headers=csrf,
    )
    assert imported.status_code == 201
    assert [t["name"] for t in imported.json()["tasks"]][:1] == ["Design the payment API"]
    bad = test.post(
        "/api/import/csv?lang=pl",
        files={"tasks": ("tasks.csv", b"id,name,duration_days\nT1,,x\n")},
        data={"name": "Bad", "start": "2026-11-02"},
        headers=csrf,
    )
    assert bad.status_code == 422
    assert [d["message"] for d in bad.json()["error"]["details"]] == [
        "Wiersz 2: pole name jest wymagane.",
        "Wiersz 2: duration_days musi być liczbą całkowitą (jest „x”).",
    ]


def test_llm_settings_are_kept_server_side_and_never_returned(tmp_path: Path) -> None:
    config = local(tmp_path)
    test, csrf = client(config)
    assert test.get("/api/settings/llm").json() == {
        "provider": "none",
        "model": None,
        "host": None,
        "has_key": False,
        "available": False,
    }
    saved = test.put(
        "/api/settings/llm",
        json={"provider": "groq", "api_key": KEY},
        headers=csrf,
    )
    assert saved.status_code == 200 and saved.json()["has_key"] is True
    assert KEY not in saved.text and KEY not in test.get("/api/settings/llm").text
    assert KEY not in test.get("/api/session").text
    assert os.stat(config.settings_file).st_mode & 0o777 == 0o600
    assert json.loads(config.settings_file.read_text())["llm"]["api_key"] == KEY
    kept = test.put("/api/settings/llm", json={"provider": "groq", "model": "m"}, headers=csrf)
    assert kept.json()["has_key"] is True and kept.json()["model"] == "m"
    keyless = test.put(
        "/api/settings/llm", json={"provider": "openrouter", "api_key": ""}, headers=csrf
    )
    assert keyless.status_code == 422 and keyless.json()["error"]["code"] == "settings_invalid"


EXTRACTION = {
    "team": [{"role": "Developer", "count": 2}],
    "activities": [
        {"name": "Design", "duration_days": 2, "crew": {"Developer": 1}, "predecessors": []},
        {"name": "Build", "duration_days": 4, "crew": {"Developer": 2}, "predecessors": ["Design"]},
    ],
}


PROPOSALS = {"proposals": [{"operations": [{"op": "SUBST", "activity": 1}, {"op": "SHIFT"}]}]}


def _fake(explanation: dict[str, Any], seen: list[str]) -> Any:
    """A scripted model: proposals, explanations or an extraction by the system prompt; `seen`
    collects the first words of every system prompt it was asked with."""

    def answer(messages: Sequence[Message]) -> str:
        system = messages[0].content
        seen.append(" ".join(system.split()[:2]))
        if system.startswith("You advise"):
            return json.dumps(PROPOSALS)
        if system.startswith("You explain"):
            return json.dumps(explanation)
        return json.dumps(EXTRACTION)

    def factory(settings: LlmSettings, cache: LlmCache) -> LlmClient:
        assert cache.store_prompts is False  # real data: no prompts in the cache (spec 10)
        return FakeLlmClient(answer, cache=cache)

    return factory


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_extraction_and_explanations_use_the_configured_model(tmp_path: Path) -> None:
    config = local(tmp_path)
    explanation = {
        "summary": "Replace Ada on Build API to raise the chance to finish on time.",
        "cited_facts": [
            {"kind": "chosen_action", "value": "SUBST(1)"},
            {"kind": "deciding_component", "value": "stability"},
        ],
    }
    seen: list[str] = []
    services = Services(config, llm_factory=_fake(explanation, seen))
    test, csrf = client(config, services)
    off = test.post("/api/extract", json={"text": "A plan."}, headers=csrf)
    assert off.status_code == 503 and off.json()["error"]["code"] == "llm_disabled"
    test.put("/api/settings/llm", json={"provider": "ollama"}, headers=csrf)
    job = test.post(
        "/api/extract", json={"text": "Two developers design, then build."}, headers=csrf
    )
    result = job.json()["result"]
    assert job.json()["status"] == "done" and result["issues"] == 0
    draft = result["definition"]
    assert [p["name"] for p in draft["team"]] == ["Developer 1", "Developer 2"]
    assert [(t["key"], t["predecessors"]) for t in draft["tasks"]] == [("T1", []), ("T2", ["T1"])]
    proposing = small().model_copy(update={"settings": Settings(llm_proposals=True)})
    pid = test.post("/api/projects", json=proposing.model_dump(mode="json"), headers=csrf).json()[
        "id"
    ]
    test.post(f"/api/projects/{pid}/plan", headers=csrf)
    test.post(
        f"/api/projects/{pid}/checkins",
        content=ABSENCE_CHECKIN.model_dump_json(),
        headers={**csrf, "content-type": "application/json"},
    )
    assert seen == ["You extract", "You advise"]  # one proposal call at the gated deliberation
    seq = test.get(f"/api/projects/{pid}").json()["open_recommendation"]
    explained = test.post(f"/api/projects/{pid}/recommendations/{seq}/explanation", headers=csrf)
    assert explained.json()["status"] == "done"
    shown = next(
        r for r in test.get(f"/api/projects/{pid}").json()["recommendations"] if r["seq"] == seq
    )
    assert shown["llm_explanation"]["source"] == "llm"
    assert shown["llm_explanation"]["badge"] == "faithful"
    assert shown["explanation"]["source"] == "template"


def test_demo_sessions_are_isolated(tmp_path: Path) -> None:
    config = demo(tmp_path)
    services = Services(config)
    app = create_app(config, services)
    alice, alice_csrf = client(config, app=app)
    bob, bob_csrf = client(config, app=app)
    pid = alice.post("/api/projects", json=_definition(), headers=alice_csrf).json()["id"]
    job = services.store.create_job(_session(services, pid), pid, "plan").id
    assert alice.get(f"/api/jobs/{job}").status_code == 200
    assert bob.get("/api/projects").json() == []
    assert bob.get(f"/api/projects/{pid}").status_code == 404
    assert bob.get(f"/api/projects/{pid}/export.json").status_code == 404
    assert bob.get(f"/api/projects/{pid}/events").status_code == 404
    assert bob.get(f"/api/jobs/{job}").status_code == 404
    assert bob.delete(f"/api/projects/{pid}", headers=bob_csrf).status_code == 404
    assert (
        bob.put(f"/api/projects/{pid}/definition", json=_definition(), headers=bob_csrf).status_code
        == 404
    )
    # Alice's token does not work in Bob's session, nor a forged session cookie.
    assert bob.post("/api/projects", json=_definition(), headers=alice_csrf).status_code == 403
    stranger = TestClient(app)
    stranger.cookies.set("sentinel_session", alice.cookies["sentinel_session"][:-2] + "00")
    assert stranger.get("/api/projects").json() == []
    assert alice.get("/api/settings/llm").status_code == 403
    assert (
        alice.put("/api/settings/llm", json={"provider": "none"}, headers=alice_csrf).status_code
        == 403
    )
    assert alice.get("/api/docs").status_code == 404
    # Without a session a state-changing request is refused rather than given a sandbox.
    fresh = TestClient(app)
    assert fresh.post("/api/projects", json=_definition()).status_code == 403


def test_demo_limits(tmp_path: Path) -> None:
    config = demo(
        tmp_path,
        projects_per_session=2,
        tasks_per_project=3,
        simulator_days=10,
        concurrent_jobs=1,
        upload_kb=1,
    )
    services = Services(config)
    test, csrf = client(config, services)
    assert test.post("/api/projects", json=_definition(), headers=csrf).status_code == 201
    four = _definition()
    four["tasks"].append({"key": "T4", "name": "Docs", "duration": 1})
    too_many = test.post("/api/projects", json=four, headers=csrf)
    assert too_many.status_code == 429
    assert too_many.json()["error"]["message"] == "A demo project can have at most 3 tasks."
    pid = test.post("/api/projects", json=_definition(), headers=csrf).json()["id"]
    third = test.post("/api/projects", json=_definition(), headers=csrf)
    assert third.status_code == 429 and third.json()["error"]["code"] == "limit_projects"
    days = test.post(f"/api/projects/{pid}/advance", json={"days": 11}, headers=csrf)
    assert days.status_code == 429 and days.json()["error"]["code"] == "limit_days"
    session = test.get("/api/session").json()
    assert session["limits"]["concurrent_jobs"] == 1 and session["expires_hours"] == 24
    services.store.create_job(_session(services, pid), pid, "plan")  # a job still running
    busy = test.post(f"/api/projects/{pid}/plan", headers=csrf)
    assert busy.status_code == 429 and busy.json()["error"]["code"] == "limit_jobs"
    upload = test.post("/api/import/json", files={"file": ("p.json", b"x" * 2048)}, headers=csrf)
    assert upload.status_code == 413


def _session(services: Services, project_id: str) -> str:
    with services.store._connect() as db:
        return str(
            db.execute("SELECT session FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
        )


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_demo_request_rate_and_sandbox_expiry(tmp_path: Path) -> None:
    config = demo(tmp_path, requests_per_minute=5)
    services = Services(config)
    test, csrf = client(config, services)  # one request
    codes = [test.get("/api/projects").status_code for _ in range(6)]
    assert codes == [200, 200, 200, 200, 429, 429]
    config = demo(tmp_path / "expiry", sandbox_hours=1)
    services = Services(config)
    test, csrf = client(config, services)
    test.post("/api/projects", json=_definition(), headers=csrf)
    assert len(test.get("/api/projects").json()) == 1
    from datetime import timedelta

    from sentinel.app.store import now

    services.store.expire(now() + timedelta(seconds=1))
    assert test.get("/api/projects").json() == []  # a new, empty sandbox
    assert "sentinel_session" in test.cookies


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_session_info_reports_the_llm_and_limits(tmp_path: Path) -> None:
    test, _ = client(demo(tmp_path, projects_per_session=3))
    info = test.get("/api/session").json()
    assert info["demo"] is True and info["llm_available"] is False
    assert info["limits"]["projects_per_session"] == 3


@pytest.mark.data
@pytest.mark.slow
def test_simulator_projects_through_the_api(psplib_root: Path, tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path, inline_jobs=True, psplib_root=psplib_root)
    test = TestClient(create_app(config))
    csrf = {"X-CSRF-Token": test.get("/api/session").json()["csrf_token"]}
    assert "j301_1" in test.get("/api/simulator/instances?set=j30").json()
    spec = {"instance": "j301_1", "start": "2026-11-02", "scenario": 1}
    created = test.post("/api/simulator", json=spec, headers=csrf).json()
    assert created["status"] == "done"
    pid = created["project"]
    advanced = test.post(f"/api/projects/{pid}/advance", json={"days": 10}, headers=csrf).json()
    assert advanced["status"] == "done" and advanced["result"]["days"] == 10
    view = test.get(f"/api/projects/{pid}").json()
    assert view["kind"] == "simulator" and view["main"]["day"] == 10
    while not test.get(f"/api/projects/{pid}").json()["finished"]:
        test.post(f"/api/projects/{pid}/advance", json={"days": 60}, headers=csrf)
    cockpit = test.post(f"/api/projects/{pid}/cockpit", headers=csrf).json()
    assert cockpit["status"] == "done"
    page = test.get(cockpit["result"]["html"]).text
    assert "j30/j301_1" in page and "<svg" in page
    unknown = test.post("/api/simulator", json={**spec, "instance": "j309_99"}, headers=csrf)
    assert unknown.status_code == 404
