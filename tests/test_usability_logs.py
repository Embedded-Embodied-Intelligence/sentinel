"""The remote usability test's tools (WP13; docs/usability/README.md): the demo's request log of
each sandbox (ADR-0030), the owner's log export of a tester on a scripted run, the SUS score."""

import importlib.util
import sqlite3
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from app_cases import ABSENCE_CHECKIN, small
from fastapi.testclient import TestClient

import sentinel.app.api
import sentinel.app.store
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.security import CSRF_COOKIE, SESSION_COOKIE
from sentinel.app.store import Store

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # the script's dataclasses look their module up
    spec.loader.exec_module(module)
    return module


class Clock:
    """The store's and the request log's clock, moved by the test; it starts an hour ago, so
    the sandbox does not expire."""

    def __init__(self) -> None:
        self.at = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)

    def __call__(self) -> datetime:
        return self.at

    def tick(self, seconds: int) -> datetime:
        self.at += timedelta(seconds=seconds)
        return self.at


def demo(tmp_path: Path, *, request_log: bool = True, demo: bool = True) -> AppConfig:
    return AppConfig(
        data_dir=tmp_path, demo=demo, inline_jobs=True, showcase=False, request_log=request_log
    )


def logged(store: Store) -> list[tuple[str, str, str | None, bool, int]]:
    """The request log of every session of the store."""
    with sqlite3.connect(store.path) as db:
        sessions = [row[0] for row in db.execute("SELECT id FROM sessions ORDER BY created")]
    return [
        (r.method, r.path, r.project, r.partial, r.status)
        for session in sessions
        for r in store.requests(session)
    ]


def test_the_demo_logs_route_templates_without_addresses_ids_or_forms(tmp_path: Path) -> None:
    app = create_app(demo(tmp_path / "demo"))
    store = app.state.services.store
    with TestClient(app) as test:
        assert test.get("/").status_code == 200
        csrf = {"X-CSRF-Token": test.cookies[CSRF_COOKIE]}
        created = test.post("/api/projects", json=small().model_dump(mode="json"), headers=csrf)
        project = created.json()["id"]
        test.get(f"/projects/{project}/checkin", headers={"HX-Request": "true"})
        test.post(f"/projects/{project}/checkin", data={"date": "4 Nov, private"}, headers=csrf)
        test.get("/projects/typed-by-hand/checkin")
        test.get("/no-such-page?secret=1")
    assert logged(store) == [
        ("GET", "/", None, False, 200),
        ("POST", "/api/projects", None, False, 201),
        ("GET", "/projects/{project_id}/checkin", project, True, 200),
        ("POST", "/projects/{project_id}/checkin", project, False, 422),
        ("GET", "/projects/{project_id}/checkin", None, False, 404),
        ("GET", "", None, False, 404),
    ]
    with sqlite3.connect(store.path) as db:
        dump = "\n".join(db.iterdump())
    for text in ("private", "typed-by-hand", "secret", "testclient"):  # testclient: the address
        assert text not in dump
    assert store.expire(datetime.now(UTC) + timedelta(days=2)) == 1  # the log goes with it
    assert logged(store) == []
    for config in (demo(tmp_path / "off", request_log=False), demo(tmp_path / "local", demo=False)):
        app = create_app(config)
        with TestClient(app) as test:
            test.get("/")
        assert logged(app.state.services.store) == []


@pytest.fixture
def scripted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    """A tester's run of the protocol's tasks through the API and the pages at scripted times;
    the simulation and its end written to the store as the simulator writes them (no PSPLIB)."""
    clock = Clock()
    monkeypatch.setattr(sentinel.app.store, "now", clock)
    monkeypatch.setattr(sentinel.app.api, "now", clock)
    config = demo(tmp_path / "demo")
    app = create_app(config)
    store = app.state.services.store
    with TestClient(app) as test:
        first = clock.at
        test.get("/")  # the sandbox starts
        csrf = {"X-CSRF-Token": test.cookies[CSRF_COOKIE]}
        clock.tick(60)
        definition = small().model_copy(update={"name": "P1 Small"}).model_dump(mode="json")
        project = test.post("/api/projects", json=definition, headers=csrf).json()["id"]
        plan = clock.tick(90)
        assert test.post(f"/api/projects/{project}/plan", headers=csrf).status_code == 202
        clock.tick(10)
        test.get(f"/projects/{project}")
        clock.tick(40)
        assert test.post(f"/projects/{project}/checkin", data={}, headers=csrf).status_code == 422
        checkin = clock.tick(60)
        body = ABSENCE_CHECKIN.model_dump(mode="json")
        saved = test.post(f"/api/projects/{project}/checkins", json=body, headers=csrf).json()
        seq = max(r["seq"] for r in saved["project"]["recommendations"])
        clock.tick(40)
        test.get(f"/projects/{project}/recommendations/{seq}")
        decision = clock.tick(50)
        url = f"/api/projects/{project}/recommendations/{seq}/decision"
        assert test.post(url, json={"verdict": "approve"}, headers=csrf).status_code == 200
        clock.tick(30)
        test.get("/simulator")
        with sqlite3.connect(store.path) as db:
            sid = db.execute("SELECT id FROM sessions").fetchone()[0]
        clock.tick(10)
        spec = {"instance": "j3026_7", "disruptions": "typical", "policy": "sentinel"}
        sim = store.create_project(sid, "simulator", "Small example", "simulator", {"spec": spec})
        job = store.create_job(sid, sim.id, "advance")
        end = clock.tick(80)
        side = {"finish": "2027-02-17", "late_days": 8, "on_time": False, "cost_ratio": 1.03}
        late = {"policy": "no_reaction", "finish": "2027-03-03", "late_days": 18}
        result = {"finished": True, "main": {"policy": "sentinel", **side}, "compare": side | late}
        store.update_job(job.id, status="done", result=result)
        hidden = [sid, project, sim.id, job.id, test.cookies[SESSION_COOKIE], csrf["X-CSRF-Token"]]
    yield {
        "database": config.database,
        "times": [first, plan, checkin, decision, end],
        "hidden": [*hidden, "testclient"],
    }


def test_the_owners_log_of_a_scripted_run(scripted: dict[str, object], tmp_path: Path) -> None:
    logs = script("usability_logs")
    database = scripted["database"]
    assert isinstance(database, Path)
    text = logs.export(database, "P1", UTC)
    assert text is not None
    first, plan, checkin, decision, end = (t.strftime("%H:%M:%S") for t in scripted["times"])  # type: ignore[attr-defined]
    for row in (
        f"| 1. Project from the spreadsheet | the first request {first} | the plan {plan} | "
        "150 s (2:30) | 1 | 0 |",
        f"| 3. Absence (with task 2) | the plan {plan} | the saved status report {checkin} | "
        "110 s (1:50) | 1 | 1 |",
        f"| 4. Recommendation | the saved status report {checkin} | the decision {decision} | "
        "90 s (1:30) | 1 | 0 |",
        f"| 5. Simulator | the decision {decision} | the end of the simulation {end} | "
        "120 s (2:00) | 1 | 0 |",
        "| Status report saved: “P1 Small” | as of Wed 4 Nov 2026; Build API: in progress 30 %; "
        "Build UI: done on 4 Nov; Ada absent from 5 Nov, back 16 Nov |",
        "| Sent the status report (“P1 Small”) | refused (422) |",
        "| Opened a recommendation (“P1 Small”) |  |",
        "| Simulation finished: simulation 1 | Sentinel: finish Wed 17 Feb 2027, 8 working days "
        "late, cost 103 % of the budget; no reaction: finish Wed 3 Mar 2027, 18 working days "
        "late, cost 103 % of the budget |",
    ):
        assert row in text
    assert "| Decision (approved): “P1 Small” | Zastępstwo: " in text
    assert "| Overview shows: “P1 Small” | chance " in text
    for hidden in scripted["hidden"]:  # type: ignore[attr-defined]
        assert hidden not in text
    data_dir = database.parent
    assert logs.main(["--data-dir", str(data_dir), "--code", "p1", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "p1.md").read_text("utf-8").startswith("# Usability test log p1")
    assert logs.main(["--data-dir", str(data_dir), "--code", "P2", "--out", str(tmp_path)]) == 1
    assert [logs.matches(n, "P1") for n in ("P1 A", "p1: A", " P1", "P10 A", "XP1 A")] == [
        True,
        True,
        True,
        False,
        False,
    ]


def test_sus_scores_a_card_as_brooke_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sus = script("sus_score")
    assert sus.sus_score([4, 2, 4, 1, 5, 2, 4, 2, 4, 1]) == 82.5
    assert sus.sus_score([3] * 10) == 50.0
    assert (sus.sus_score([5, 1] * 5), sus.sus_score([1, 5] * 5)) == (100.0, 0.0)
    for wrong in ([4] * 9, [0] + [3] * 9, [3] * 11):
        with pytest.raises(ValueError):
            sus.sus_score(wrong)
    cards = tmp_path / "cards.txt"
    cards.write_text("# code and answers\nP1: 4,2,4,1,5,2,4,2,4,1\nP2 3 3 3 3 3 3 3 3 3 3\n")
    assert sus.main(["--file", str(cards)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "| P1 | 4 | 2 | 4 | 1 | 5 | 2 | 4 | 2 | 4 | 1 | 82,5 |",
        "| P2 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 50,0 |",
        "| **Średnia (min–max)** | | | | | | | | | | | 66,3 (50,0–82,5) |",
    ]
    assert sus.main(["P3", "4", "2", "4"]) == 2


def test_the_log_of_a_sandbox_made_without_the_request_log_says_so(tmp_path: Path) -> None:
    config = demo(tmp_path, request_log=False)
    with TestClient(create_app(config)) as test:
        test.get("/")
        csrf = {"X-CSRF-Token": test.cookies[CSRF_COOKIE]}
        definition = small().model_copy(update={"name": "P1 Small"}).model_dump(mode="json")
        assert test.post("/api/projects", json=definition, headers=csrf).status_code == 201
    text = script("usability_logs").export(config.database, "P1", UTC)
    assert text is not None and "The demo kept no request log" in text
    assert "| the plan: not reached | – | – | – |" in text
