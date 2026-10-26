"""The pages of the application (WP9b; spec section 11; ADR-0025): every screen and state in
Polish and English without internal terms, missing texts, raw codes or ISO dates (spec section
11.7); the friendly error pages; and the undo of an automatic plan change (spec section 11.5)."""

import html
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from app_cases import ABSENCE_CHECKIN, small
from fastapi.testclient import TestClient
from ui_check import problems, visible_text

from sentinel.app import names
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig, Limits
from sentinel.app.events import Recommended
from sentinel.app.models import Person, ProjectDefinition
from sentinel.app.services import Services
from sentinel.app.simulator import SimulatorSpec
from sentinel.app.store import LOCAL_SESSION

LANGUAGES = ("pl", "en")


@dataclass
class Site:
    """An app with live projects in every state a page shows."""

    client: TestClient
    headers: dict[str, str]
    services: Services
    ids: dict[str, str]


def _create(site_client: TestClient, headers: dict[str, str], definition: ProjectDefinition) -> str:
    response = site_client.post(
        "/api/projects", json=definition.model_dump(mode="json"), headers=headers
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _checkin(client: TestClient, headers: dict[str, str], pid: str, body: Any) -> None:
    response = client.post(
        f"/api/projects/{pid}/checkins",
        content=body.model_dump_json(),
        headers={**headers, "content-type": "application/json"},
    )
    assert response.status_code == 200, response.text


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    config = AppConfig(
        data_dir=tmp_path_factory.mktemp("ui"),
        inline_jobs=True,
        psplib_root=tmp_path_factory.mktemp("no_psplib"),
    )
    services = Services(config)
    with TestClient(create_app(config, services)) as client:
        csrf = client.get("/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        ids: dict[str, str] = {}
        team_only = ProjectDefinition(
            name="Draft",
            start=date(2026, 11, 2),
            team=(
                Person(key="P1", name="Ada", role="Developer"),
                Person(key="P2", name="", role="Tester"),
            ),
        )
        ids["draft"] = _create(client, headers, team_only)
        for name, definition in (
            ("planned", small()),
            ("open", small()),
            ("calm", small(deadline=date(2026, 12, 18))),
            ("undated", small(deadline=None)),
        ):
            ids[name] = _create(client, headers, definition)
            assert (
                client.post(f"/api/projects/{ids[name]}/plan", headers=headers).status_code == 202
            )
        _checkin(client, headers, ids["open"], ABSENCE_CHECKIN)
        _checkin(client, headers, ids["calm"], ABSENCE_CHECKIN)
        # Copies of the open project by its JSON export: approved, and changed automatically.
        export = client.get(f"/api/projects/{ids['open']}/export.json").json()
        for name in ("approved", "auto"):
            files = {"file": ("p.json", json.dumps(export).encode(), "application/json")}
            response = client.post("/api/import/json", files=files, headers=headers)
            assert response.status_code == 201
            ids[name] = response.json()["id"]
        seq = client.get(f"/api/projects/{ids['approved']}").json()["open_recommendation"]
        decision = client.post(
            f"/api/projects/{ids['approved']}/recommendations/{seq}/decision",
            json={"verdict": "approve"},
            headers=headers,
        )
        assert decision.status_code == 200
        _automatic_shift(services, ids["auto"])
        spec = SimulatorSpec(instance="j301_1", start=date(2026, 11, 2), name="Example")
        services.store.create_project(
            LOCAL_SESSION,
            "simulator",
            "Example",
            "simulator",
            {"spec": spec.model_dump(mode="json")},
        )
        yield Site(client, headers | {"HX-Request": "true"}, services, ids)


def _automatic_shift(services: Services, pid: str) -> None:
    """Sentinel's SHIFT candidate of the open recommendation, applied automatically through the
    engine (as if the autonomy allowed it): an automatic plan change that can be undone."""
    state = services.state(LOCAL_SESSION, pid)
    entry = state.recommendations[-1]
    recommendation = entry.recommendation
    shift = next(c for c in recommendation.record.candidates if c.label == "SHIFT")
    record = recommendation.record.model_copy(update={"chosen": "SHIFT", "gate": "auto"})
    applied = state.project.resolve_action(shift.decision, "SHIFT", "shift")
    assert not isinstance(applied, str) and applied.plan and not applied.crews
    event = Recommended(
        recommendation=recommendation.model_copy(update={"record": record}), applied=applied
    )
    row = services.store.project(LOCAL_SESSION, pid)
    assert row is not None
    services.store.append(
        LOCAL_SESSION, pid, "recommendation", event.model_dump(mode="json"), expected=row.seq
    )


def _get(site: Site, url: str, language: str, status: int = 200, htmx: bool = False) -> str:
    headers = {"HX-Request": "true"} if htmx else {}
    response = site.client.get(url, params={"lang": language}, headers=headers)
    assert response.status_code == status, (url, response.status_code, response.text[:400])
    found = problems(response.text)
    assert found == [], (url, language, found)
    return response.text


def _post(site: Site, url: str, language: str, data: dict[str, Any], status: int = 200) -> Any:
    response = site.client.post(url, params={"lang": language}, data=data, headers=site.headers)
    assert response.status_code == status, (url, response.status_code, response.text[:400])
    assert problems(response.text) == [], (url, language, problems(response.text))
    return response


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_screen_and_state_renders_without_internal_terms(site: Site, language: str) -> None:
    ids = site.ids
    start = _get(site, "/", language)
    assert all(f"/projects/{ids[k]}" in start for k in ("planned", "open", "calm"))
    for name in ("planned", "undated"):
        _get(site, f"/projects/{ids[name]}/chance", language, htmx=True)
    # the wizard: new project, the draft's three steps and every tab
    _get(site, "/new", language)
    _post(site, "/new", language, {"name": "", "start": "x"}, 422)
    for step in ("basics", "team", "tasks"):
        _get(site, f"/projects/{ids['draft']}/setup/{step}", language)
    for tab in ("describe", "import", "manual"):
        _get(site, f"/projects/{ids['draft']}/setup/tasks?tab={tab}", language)
    team = {
        "person_key": ["P1", "P2"],
        "person_name": ["Ada", ""],
        "person_role": ["Developer", "Tester"],
    }
    _post(site, f"/projects/{ids['draft']}/setup/team", language, {**team, "action": "add"})
    _post(site, f"/projects/{ids['draft']}/setup/team", language, {**team, "action": "next"}, 422)
    tasks = {"task_key": ["T1"], "task_name": ["Build"], "task_days": ["x"], "crew_T1_0": "1"}
    status = _post(
        site, f"/projects/{ids['draft']}/setup/tasks", language, {**tasks, "action": "autosave"}
    )
    assert "issue-1" in status.text
    _post(
        site, f"/projects/{ids['draft']}/setup/tasks", language, {**tasks, "action": "finish"}, 422
    )
    # every live project's screens
    for name in ("planned", "open", "approved", "auto", "calm", "undated"):
        pid = ids[name]
        _get(site, f"/projects/{pid}", language)
        _get(site, f"/projects/{pid}/forecast", language, htmx=True)
        _get(site, f"/projects/{pid}/checkin", language)
        for show in ("all", "checkins", "recommendations", "changes"):
            _get(site, f"/projects/{pid}/history?show={show}", language)
        _get(site, f"/projects/{pid}/settings", language)
    for name in ("open", "approved", "auto", "calm"):
        pid = ids[name]
        seq = max(
            int(s)
            for s in re.findall(
                rf"/projects/{pid}/recommendations/(\d+)",
                _get(site, f"/projects/{pid}/history", language),
            )
        )
        _get(site, f"/projects/{pid}/recommendations/{seq}", language)
    _get(site, f"/projects/{ids['open']}/delete", language)
    # refused forms keep the manager's input and name the problems
    _post(site, f"/projects/{ids['open']}/checkin", language, {"date": "", "shown": ["T1"]}, 422)
    _post(site, f"/projects/{ids['open']}/settings", language, {"name": "", "autonomy": "9"}, 422)
    for url in ("/how-it-works", "/settings", "/simulator"):
        _get(site, url, language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_states_show_what_happened(site: Site, language: str) -> None:
    ids = site.ids
    words = {"pl": ("Cofnij", "Zatwierdź", "Bez zmian"), "en": ("Undo", "Approve", "No change")}
    undo, approve, keep = words[language]
    auto = _get(site, f"/projects/{ids['auto']}", language)
    assert undo in auto and "/undo" in auto
    open_ = _get(site, f"/projects/{ids['open']}", language)
    assert "Cleo" in open_ and "Ada" in open_  # the substitute and the absent member, by name
    history = _get(site, f"/projects/{ids['open']}/history", language)
    seq = re.findall(rf"/projects/{ids['open']}/recommendations/(\d+)", history)[0]
    page = _get(site, f"/projects/{ids['open']}/recommendations/{seq}", language)
    assert approve in page and "verdict" in page
    calm = _get(site, f"/projects/{ids['calm']}", language)
    assert ("plan wciąż jest najlepszy" if language == "pl" else "still the best") in calm
    undated = _get(site, f"/projects/{ids['undated']}/forecast", language, htmx=True)
    assert "/settings" in undated  # set a deadline
    assert keep in _get(
        site, f"/projects/{ids['calm']}/recommendations/{_last(site, 'calm', language)}", language
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_one_comparison_and_costs_in_cost_units(site: Site, language: str) -> None:
    """WP9c answers 1 and 4: "no change" on a recommendation is the overview's chance on the
    same project and day; costs are cost units with their meaning, changes also a share of the
    budget."""
    pid = site.ids["open"]
    forecast = _get(site, f"/projects/{pid}/forecast", language, htmx=True)
    found = re.search(r'headline-number">([^<]+)<', forecast)
    assert found is not None
    chance = found.group(1)
    page = _get(site, f"/projects/{pid}/recommendations/{_last(site, 'open', language)}", language)
    assert f"{chance} →" in page  # the chip: no change → with the action
    unit, meaning, short, note = {
        "pl": ("jednostek kosztu", "(osobodni)", "25 jedn.", "jedna jednostka to jeden osobodzień"),
        "en": ("cost units", "(person-days)", "25 units", "one cost unit is one person-day"),
    }[language]
    assert unit in forecast and meaning in forecast
    assert short in page and note in page  # the options compared, in cost units
    assert ("rzadziej" if language == "pl" else "rougher") not in page  # the v2.0.1 note


def _last(site: Site, name: str, language: str) -> int:
    pid = site.ids[name]
    history = _get(site, f"/projects/{pid}/history", language)
    return max(int(s) for s in re.findall(rf"/projects/{pid}/recommendations/(\d+)", history))


def test_loading_and_error_states(site: Site, tmp_path: Path) -> None:
    services, ids = site.services, site.ids
    for language in LANGUAGES:
        _get(site, "/projects/nope", language, 404)
        _get(site, "/nothing-here", language, 404)
        running = services.store.create_job(LOCAL_SESSION, ids["open"], "recommend")
        progress = _get(site, f"/jobs/{running.id}?label=job.recommend", language, htmx=True)
        assert "<progress" in progress and f"/jobs/{running.id}" in progress
        failed = services.store.create_job(LOCAL_SESSION, ids["open"], "recommend")
        services.store.update_job(failed.id, status="failed", error={"code": "no_deadline"})
        assert "alert-error" in _get(site, f"/jobs/{failed.id}", language, htmx=True)
        services.store.update_job(running.id, status="done", result={"recommendation": 1})
    empty = AppConfig(data_dir=tmp_path / "empty", inline_jobs=True)
    with TestClient(create_app(empty), raise_server_exceptions=False) as client:
        for language in LANGUAGES:
            page = client.get("/", params={"lang": language})
            assert page.status_code == 200 and problems(page.text) == []
            assert "/new" in page.text and "empty-state" in page.text
        broken = client.app.state.services  # type: ignore[attr-defined]

        def fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        broken.projects = fail
        crashed = client.get("/", params={"lang": "pl"})
        assert crashed.status_code == 500 and "boom" not in crashed.text
        assert re.search(r"Numer zgłoszenia: [0-9a-f]{8}", crashed.text)
        assert problems(crashed.text) == []


def test_demo_pages_are_read_only_and_need_the_csrf_header(tmp_path: Path) -> None:
    config = AppConfig(
        data_dir=tmp_path / "demo", demo=True, inline_jobs=True, showcase=False, limits=Limits()
    )
    with TestClient(create_app(config)) as client:
        page = client.get("/settings", params={"lang": "en"})
        assert page.status_code == 200 and problems(page.text) == []
        assert 'name="api_key"' not in page.text and "deleted 24 hours" in page.text
        token = re.search(r'"X-CSRF-Token": "([0-9a-f]{64})"', page.text)
        assert token is not None
        refused = client.post("/new", data={"name": "X", "start": "2026-11-02"})
        assert refused.status_code == 403 and problems(refused.text) == []
        created = client.post(
            "/new",
            data={"name": "X", "start": "2026-11-02"},
            headers={"X-CSRF-Token": token.group(1), "HX-Request": "true"},
        )
        assert created.status_code == 200 and "/setup/team" in created.headers["HX-Redirect"]
        assert (
            client.post(
                "/settings", data={"provider": "ollama"}, headers={"X-CSRF-Token": token.group(1)}
            ).status_code
            == 403
        )


def test_a_check_in_and_a_decision_through_the_pages(site: Site) -> None:
    client, headers, ids = site.client, site.headers, site.ids
    form = {
        "date": "2026-11-04",
        "shown": ["T1", "T2"],
        "status_T1": "in_progress",
        "percent_T1": "30",
        "status_T2": "done",
        "finish_T2": "2026-11-04",
        "away_rows": ["1"],
        "away_1_person": "a",
        "away_1_from": "2026-11-05",
        "away_1_back": "2026-11-16",
    }
    pid = ids["planned"]
    saved = client.post(f"/projects/{pid}/checkin", data=form, headers=headers)
    assert saved.headers["HX-Redirect"] == f"/projects/{pid}?flash=checkin_saved"
    view = client.get(f"/api/projects/{pid}").json()
    assert view["checkins"][0]["date"] == "2026-11-04" and view["open_recommendation"] is not None
    again = client.post(
        f"/projects/{pid}/checkin", data={**form, "date": "2026-11-03"}, headers=headers
    )
    assert again.status_code == 422 and "alert-error" in again.text  # out of order
    seq = view["open_recommendation"]
    later = client.post(
        f"/projects/{pid}/recommendations/{seq}/decision",
        data={"verdict": "later"},
        headers=headers,
    )
    assert later.headers["HX-Redirect"].endswith("flash=later")
    approved = client.post(
        f"/projects/{pid}/recommendations/{seq}/decision",
        data={"verdict": "approve"},
        headers=headers,
    )
    assert approved.headers["HX-Redirect"].endswith("flash=approved")
    history = visible_text(client.get(f"/projects/{pid}/history", params={"lang": "en"}).text)
    assert "You approved: Substitute: Cleo takes over Ada's part in “Build API”" in history


def test_undo_restores_the_plan_before_an_automatic_change(site: Site) -> None:
    client, headers, services = site.client, site.headers, site.services
    pid = site.ids["auto"]
    state = services.state(LOCAL_SESSION, pid)
    entry = state.recommendations[-1]
    assert entry.status == "auto" and state.can_undo(entry) and entry.applied is not None
    before = {
        key: services.state(LOCAL_SESSION, site.ids["open"]).project.tasks[key].planned
        for key in entry.applied.plan
    }
    undone = client.post(f"/projects/{pid}/recommendations/{entry.seq}/undo", headers=headers)
    assert undone.headers["HX-Redirect"].endswith("flash=undone")
    after = services.state(LOCAL_SESSION, pid)
    assert {key: after.project.tasks[key].planned for key in before} == before
    assert after.recommendations[-1].status == "undone" and not after.project.actions
    assert (
        after.project.observation()
        == services.state(LOCAL_SESSION, site.ids["open"]).project.observation()
    )
    twice = client.post(f"/projects/{pid}/recommendations/{entry.seq}/undo", headers=headers)
    assert twice.status_code == 409


def test_language_switch_ask_settings_report_and_delete(site: Site) -> None:
    client, headers, ids = site.client, site.headers, site.ids
    switched = client.get("/lang/en", params={"next": "/how-it-works"}, follow_redirects=False)
    assert switched.status_code == 303 and switched.headers["location"] == "/how-it-works"
    assert "sentinel_lang=en" in switched.headers["set-cookie"]
    away = client.get("/lang/pl", params={"next": "//evil.example/x"}, follow_redirects=False)
    assert away.headers["location"] == "/"
    client.cookies.delete("sentinel_lang")
    pid = ids["calm"]
    asked = client.post(f"/projects/{pid}/ask", headers=headers)
    job = re.search(r'hx-get="(/jobs/[^"]+)"', asked.text)
    assert job is not None
    done = client.get(job.group(1).replace("&amp;", "&"), headers=headers)
    assert re.fullmatch(rf"/projects/{pid}/recommendations/\d+", done.headers["HX-Redirect"])
    form = {"name": "Calm project", "deadline": "2026-12-18", "autonomy": "1", "cost_0": "2"}
    saved = client.post(f"/projects/{pid}/settings", data=form, headers=headers)
    assert saved.headers["HX-Redirect"].endswith("flash=settings_saved")
    definition = client.get(f"/api/projects/{pid}").json()["definition"]
    assert definition["name"] == "Calm project" and definition["settings"]["autonomy"] == 1
    assert definition["roles"] == [{"role": "Developer", "daily_cost": 2.0}]
    report = client.post(f"/projects/{pid}/report", headers=headers)
    job = re.search(r'hx-get="(/jobs/[^"]+)"', report.text)
    assert job is not None
    ready = client.get(job.group(1).replace("&amp;", "&"), headers=headers)
    link = re.search(r'href="(/api/jobs/[^"]+/cockpit.html)"', ready.text)
    assert link is not None and "<svg" in client.get(link.group(1)).text
    gone = client.post(f"/projects/{ids['draft']}/delete", headers=headers)
    assert gone.headers["HX-Redirect"] == "/?flash=deleted"
    assert client.get(f"/projects/{ids['draft']}/setup/team").status_code == 404


def test_ai_features_through_the_pages(tmp_path: Path) -> None:
    from sentinel.llm import FakeLlmClient, LlmCache, LlmClient

    extraction = {
        "team": [{"role": "Developer", "count": 2}],
        "activities": [
            {"name": "Design", "duration_days": 2, "crew": {"Developer": 1}, "predecessors": []},
            {
                "name": "Build",
                "duration_days": 3,
                "crew": {"Developer": 2},
                "predecessors": ["Design"],
            },
        ],
    }

    def answer(messages: Any) -> str:
        system = messages[0].content
        if system.startswith("You turn messages"):  # Ada (worker 0) back on day 10 (Mon 16 Nov)
            return json.dumps({"events": [{"type": "absence", "worker": 0, "return_day": 10}]})
        if system.startswith("Answer with the JSON object"):
            return json.dumps({"ok": True})
        return json.dumps(extraction)

    def factory(settings: Any, cache: LlmCache) -> LlmClient:
        assert cache.store_prompts is False
        return FakeLlmClient(answer, cache=cache)

    config = AppConfig(data_dir=tmp_path / "ai", inline_jobs=True)
    with TestClient(create_app(config, Services(config, llm_factory=factory))) as client:
        csrf = client.get("/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}

        def finish(response: Any) -> Any:
            job = re.search(r'hx-get="(/jobs/[^"]+)"', response.text)
            assert job is not None, response.text[:300]
            return client.get(job.group(1).replace("&amp;", "&"), headers=headers)

        tested = finish(client.post("/settings/test", data={"provider": "ollama"}, headers=headers))
        assert "scripted" in tested.text and problems(tested.text) == []
        pid = _create(client, headers, small())
        found = finish(
            client.post(
                f"/projects/{pid}/setup/describe",
                data={"text": "Design, then build."},
                headers=headers,
            )
        )
        assert problems(found.text) == [] and "Design" in found.text
        draft = re.search(r'name="draft" value="([^"]+)"', found.text)
        assert draft is not None
        used = client.post(
            f"/projects/{pid}/setup/use-extraction",
            data={"draft": html.unescape(draft.group(1))},
            headers=headers,
        )
        assert used.headers["HX-Redirect"].endswith("tab=manual")
        tasks = client.get(f"/api/projects/{pid}").json()["definition"]["tasks"]
        assert [t["name"] for t in tasks] == ["Design", "Build"]
        other = _create(client, headers, small())
        client.post(f"/api/projects/{other}/plan", headers=headers)
        read = finish(
            client.post(
                f"/projects/{other}/checkin/message",
                data={"message": "Ada is out until Monday the 16th.", "date": "2026-11-04"},
                headers=headers,
            )
        )
        assert problems(read.text) == []
        value = re.search(r'name="msg_absence" value="([^"]+)"', read.text)
        assert value is not None
        absence = json.loads(html.unescape(value.group(1)))
        assert absence == {"person": "a", "first_day": "2026-11-04", "return_date": "2026-11-16"}


@pytest.mark.data
@pytest.mark.slow  # a simulator world and 10 simulated days, about 7 s
def test_the_simulator_pages(tmp_path: Path, psplib_root: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "sim", inline_jobs=True, psplib_root=psplib_root)
    with TestClient(create_app(config)) as client:
        csrf = client.get("/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
        for language in LANGUAGES:
            setup = client.get("/simulator", params={"lang": language})
            assert setup.status_code == 200 and problems(setup.text) == []
            # the simulator runs with the application's settings (WP9c answer 3)
            note = "a nie ustawień badań" if language == "pl" else "not the setup of the research"
            assert note in setup.text
        created = client.post(
            "/simulator",
            data={"example": "small", "disruptions": "turbulent", "policy": "sentinel"},
            headers=headers,
        )
        job = re.search(r'hx-get="(/jobs/[^"]+)"', created.text)
        assert job is not None
        pid = (
            client.get(job.group(1).replace("&amp;", "&"), headers=headers)
            .headers["HX-Redirect"]
            .split("/")[2]
        )
        advanced = client.post(f"/projects/{pid}/advance", data={"days": "10"}, headers=headers)
        job = re.search(r'hx-get="(/jobs/[^"]+)"', advanced.text)
        assert job is not None
        client.get(job.group(1).replace("&amp;", "&"), headers=headers)
        first = {lang: set(names.vocabulary(lang).simulator.first_names) for lang in LANGUAGES}
        for language in LANGUAGES:
            page = client.get(f"/projects/{pid}", params={"lang": language})
            assert page.status_code == 200 and problems(page.text) == []
            assert "timeline" in page.text
            # people named in the page's language (WP9c answer 4), e.g. "Zofia N." in Polish
            shown = set(re.findall(r"(\w+) [A-Z]\.", visible_text(page.text)))
            other = "en" if language == "pl" else "pl"
            assert shown & (first[language] - first[other])
            assert not shown & (first[other] - first[language])
        start = client.get("/", params={"lang": "en"})
        assert "Days simulated: 10" in start.text and problems(start.text) == []
