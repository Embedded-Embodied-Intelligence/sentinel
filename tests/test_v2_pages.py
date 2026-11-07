"""The pages of the v2 interface (WP15; docs/design/v2-spec.md; spec section 11.8) on the
showcase project: every screen in Polish and English without internal terms, missing texts, raw
codes or ISO dates, the theme cookie, the decisions taken from the overview and the decision
page with the promised numbers shown after an approval (the WP12 guarantee, spec 11.5)."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from ui_check import problems, visible_text

from sentinel.app import planning, showcase
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION

LANGUAGES = ("pl", "en")


@dataclass
class Site:
    client: TestClient
    headers: dict[str, str]
    services: Services
    project: str


@pytest.fixture(scope="module", autouse=True)
def fewer_futures() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(planning, "THREAT_ROLLOUTS", 50)
        yield


def _site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    config = AppConfig(data_dir=tmp_path_factory.mktemp("v2"), inline_jobs=True)
    services = Services(config)
    services.local_session()
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, "pl")
    project = services.projects(LOCAL_SESSION)[0].id
    with TestClient(create_app(config, services)) as client:
        token = client.get("/api/session").json()["csrf_token"]
        yield Site(client, {"X-CSRF-Token": token, "HX-Request": "true"}, services, project)


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    """The showcase, read only by the tests that use it."""
    yield from _site(tmp_path_factory)


@pytest.fixture
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    """The showcase for a test that decides on it."""
    yield from _site(tmp_path_factory)


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", visible_text(html))


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_v2_page_is_clean(site: Site, language: str) -> None:
    pid = site.project
    open_seq = site.services.live(LOCAL_SESSION, pid, "pl").open_recommendation
    paths = [
        "/v2",
        "/v2/projects",
        f"/v2/projects/{pid}",
        f"/v2/projects/{pid}/insights",
        f"/v2/projects/{pid}/pending",
        f"/v2/projects/{pid}/log",
        f"/v2/projects/{pid}/plan",
        f"/v2/projects/{pid}/settings",
        "/v2/log",
        "/v2/lab",
        "/v2/settings",
    ]
    assert open_seq is not None
    for path in paths:
        response = site.client.get(path, params={"lang": language})
        assert response.status_code == 200, path
        assert problems(response.text) == [], path


def test_the_overview_says_the_spec_example(site: Site) -> None:
    """The showcase's overview reads as the wireframe of section 8.2."""
    html = site.client.get(f"/v2/projects/{site.project}", params={"lang": "pl"}).text
    text = text_of(html)
    assert "Nie zdążymy bez zmian" in text
    assert "Spóźnimy się o ok. 2 dni robocze." in text
    assert "Główna przyczyna: „API katalogu produktów” potrwa dłużej." in text
    assert "39 na 100" in text and "W 78 z nich — czyli 39 na 100" in text
    assert "najpewniej wt. 22 gru" in text and "w złym razie wt. 5 sty 2027" in text
    assert "wydane 27 z 84 dni pracy" in text and "na koniec ok. 92 (+9 %)" in text
    assert "Decyzja do podjęcia" in text and "Szansa 39 → 57 na 100" in text
    assert "od raportu z pt. 13 lis (92 → 39 na 100)" in text
    assert "Bez wydłużenia „API katalogu produktów” szansa byłaby 80 na 100." in text
    assert "„API katalogu produktów”: im dłużej trwa, tym później koniec projektu." in text
    assert "zużyto 120 % zapasu (trzeba działać)" in text
    assert 'aria-label="39 ze 100 kropek wypełnionych"' in html
    assert 'data-theme="light"' in html


def test_the_theme_is_remembered_in_a_cookie(site: Site) -> None:
    response = site.client.get("/v2/theme/dark", params={"next": "/v2"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/v2"
    assert "sentinel_theme=dark" in response.headers["set-cookie"]
    site.client.cookies.set("sentinel_theme", "dark")
    assert 'data-theme="dark"' in site.client.get("/v2").text
    site.client.cookies.set("sentinel_theme", "nonsense")
    assert 'data-theme="light"' in site.client.get("/v2").text
    site.client.cookies.delete("sentinel_theme")
    bad = site.client.get(
        "/v2/theme/dark", params={"next": "//evil.example"}, follow_redirects=False
    )
    assert bad.headers["location"] == "/v2"


def test_the_first_interface_links_to_v2(site: Site) -> None:
    assert 'href="/v2"' in site.client.get("/", params={"lang": "pl"}).text


def seq_of(site: Site) -> int:
    found = site.services.live(LOCAL_SESSION, site.project, "pl").open_recommendation
    assert found is not None
    return found


def test_the_decision_page_reads_as_the_brief(site: Site) -> None:
    seq = seq_of(site)
    html = site.client.get(f"/v2/projects/{site.project}/decisions/{seq}", params={"lang": "pl"})
    text = text_of(html.text)
    assert "Dotyczy ludzi, dlatego wymaga Twojej zgody." in text
    assert "Szansa 39 → 57 na 100" in text and "Budżet 92 → 94 dni pracy" in text
    assert "Ta zmiana podnosi szansę z 39 do 57 na 100" in text  # written by code (8.4)
    assert "dałaby mniej (56 na 100)" in text
    assert "Cezary Mazur: przejmuje „API katalogu produktów”" in text
    assert "Każdy dzień czekania to ok. \u22125 na 100." in text
    assert "ważna do czw. 19 lis" in text
    assert "Bez zmian 39 na 100" in text  # every option, "Bez zmian" included
    dist = site.client.get(f"/v2/projects/{site.project}/decisions/{seq}/distribution")
    assert "Na 200: w terminie 114, później 86." in text_of(dist.text)
    assert "Na 200: w terminie 78, później 122." in text_of(dist.text)
    state = site.services.state(LOCAL_SESSION, site.project)
    validity = state.recommendation(seq).validity  # type: ignore[union-attr]
    assert validity is not None and validity.valid_day == 12 and validity.chances[0] == 0.57


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_approval_from_the_decision_page_keeps_the_promise(fresh: Site) -> None:
    """The WP12 guarantee on v2: after "Zatwierdź" the overview shows the card's numbers."""
    seq = seq_of(fresh)
    path = f"/v2/projects/{fresh.project}/decisions/{seq}"
    fresh.client.get(path)  # the validity, so that the brief stored has it
    response = fresh.client.post(
        f"{path}/approve", data={"back": "decision"}, headers=fresh.headers
    )
    assert response.headers["HX-Redirect"] == f"/v2/projects/{fresh.project}?done=approved"
    text = text_of(fresh.client.get(f"/v2/projects/{fresh.project}?done=approved").text)
    assert "Zatwierdzono. Projekt ma nowy plan." in text
    assert "57 na 100" in text and "najpewniej pt. 18 gru" in text
    assert "na koniec ok. 94" in text
    archive = text_of(fresh.client.get(f"/v2/projects/{fresh.project}/decisions").text)
    assert "zatwierdzona" in archive and " Ty " in archive
    assert "Szansa 39 → 57 na 100" in archive
    rows = fresh.services.store.events(LOCAL_SESSION, fresh.project)
    decided = [r for r in rows if r.type == "decision"][-1].payload
    assert decided["brief"]["p_after"] == 0.57 and decided["brief"]["valid_day"] == 12


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_rejection_needs_a_reason_and_keeps_it(fresh: Site) -> None:
    seq = seq_of(fresh)
    path = f"/v2/projects/{fresh.project}/decisions/{seq}"
    refused = fresh.client.post(f"{path}/reject", data={}, headers=fresh.headers)
    assert refused.status_code == 422
    words = "Wolę poczekać na powrót."
    response = fresh.client.post(
        f"{path}/reject",
        data={"reason": "other", "note": words, "back": "overview"},
        headers=fresh.headers,
    )
    assert response.headers["HX-Redirect"].endswith("?done=rejected")
    archive = text_of(fresh.client.get(f"/v2/projects/{fresh.project}/decisions").text)
    assert "odrzucona" in archive and f"Powód: Inny powód: „{words}”" in archive
    overview = text_of(fresh.client.get(f"/v2/projects/{fresh.project}").text)
    assert "Nic nie czeka na Twoją decyzję" in overview


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_postpone_and_expiry(fresh: Site) -> None:
    from datetime import date

    seq = seq_of(fresh)
    path = f"/v2/projects/{fresh.project}/decisions/{seq}"
    fresh.client.get(path)
    response = fresh.client.post(f"{path}/postpone", headers=fresh.headers)
    target = response.headers["HX-Redirect"]
    assert "done=postponed" in target and "valid=2026-11-19" in target
    text = text_of(fresh.client.get(target).text)
    assert "Przypomnę przy następnej wizycie. Decyzja ważna do czw. 19 lis." in text
    assert "odłożona" in text_of(fresh.client.get(path).text)
    fresh.services.expire(LOCAL_SESSION, fresh.project, date(2026, 11, 19))  # still valid
    assert fresh.services.state(LOCAL_SESSION, fresh.project).open is not None
    fresh.services.expire(LOCAL_SESSION, fresh.project, date(2026, 11, 20))
    state = fresh.services.state(LOCAL_SESSION, fresh.project)
    assert state.open is None and state.recommendation(seq).status == "expired"  # type: ignore[union-attr]
    archive = text_of(fresh.client.get(f"/v2/projects/{fresh.project}/decisions").text)
    assert "wygasła" in archive and "Sentinel" in archive


def test_start_lists_decisions_by_validity_and_the_latest_events(site: Site) -> None:
    text = text_of(site.client.get("/v2", params={"lang": "pl"}).text)
    assert "Decyzje do podjęcia (1)" in text and "posortowane wg daty ważności" in text
    assert "+18 na 100" in text and "ważna do czw. 19 lis" in text
    assert "Nie zdążymy bez zmian" in text and "1 decyzja" in text
    events = text[text.index("Ostatnie zdarzenia") :]
    assert events.index("Nowa propozycja: Zastępstwo") < events.index("Utworzono projekt")
    assert "Sentinel Nowa odsłona sklepu internetowego: Nowa propozycja" in events


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_the_first_visit_offers_three_ways_in(tmp_path_factory: pytest.TempPathFactory) -> None:
    config = AppConfig(data_dir=tmp_path_factory.mktemp("v2-empty"), inline_jobs=True)
    services = Services(config)
    with TestClient(create_app(config, services)) as client:
        token = client.get("/api/session").json()["csrf_token"]
        text = text_of(client.get("/v2", params={"lang": "pl"}).text)
        assert "Zacznij od pierwszego projektu" in text
        for card in ("Zaimportuj arkusz", "Opisz projekt głosem", "Otwórz projekt przykładowy"):
            assert card in text
        made = client.post("/v2/example", headers={"X-CSRF-Token": token, "HX-Request": "true"})
        assert made.headers["HX-Redirect"].startswith("/v2/projects/")
        assert "39 na 100" in text_of(client.get(made.headers["HX-Redirect"]).text)


def test_dictated_and_pasted_teams() -> None:
    from sentinel.app.ui.v2.wizard import parse_day, people_of

    assert people_of("Anna, programistka; Bartek, programista") == [
        ("Anna", "programistka"),
        ("Bartek", "programista"),
    ]
    assert people_of("Anna, programistka, Bartek, programista.") == [
        ("Anna", "programistka"),
        ("Bartek", "programista"),
    ]
    assert people_of("Anna\tdesigner\nTom, tester\n\n") == [("Anna", "designer"), ("Tom", "tester")]
    assert parse_day("31.12.2026") == parse_day("2026-12-31") is not None
    assert parse_day("jutro") is None


def test_the_wizard_makes_a_project_without_asking_about_absences(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    config = AppConfig(data_dir=tmp_path_factory.mktemp("v2-new"), inline_jobs=True)
    services = Services(config)
    with TestClient(create_app(config, services)) as client:
        headers = {
            "X-CSRF-Token": client.get("/api/session").json()["csrf_token"],
            "HX-Request": "true",
        }
        first = client.get("/v2/new", params={"lang": "pl"})
        assert problems(first.text) == [] and "Np. „Aplikacja rezerwacji”" in first.text
        basics = {"name": "Aplikacja", "start": "2026-11-09", "deadline": "2026-12-18"}
        made = client.post("/v2/new", data={**basics, "days_off": "24.12.2026"}, headers=headers)
        pid = made.headers["HX-Redirect"].split("/")[3]
        team_page = text_of(client.get(f"/v2/new/{pid}/team").text)
        assert "nie pyta, jak często ktoś bywa nieobecny" in team_page and "ok. 4 %" in team_page
        team = {"team": "Anna, programista; Bartek, programista; Celina, tester"}
        client.post(f"/v2/new/{pid}/team", data=team, headers=headers)
        rows = {
            "t_name": ["Projekt", "API", "Testy", ""],
            "t_days": ["3", "6", "3", "1"],
            "t_count": ["1", "2", "1", "1"],
            "t_role": ["programista", "programista", "tester", "programista"],
            "t_after": ["", "Projekt", "API", ""],
        }
        client.post(f"/v2/new/{pid}/tasks", data=rows, headers=headers)
        tasks_page = client.get(f"/v2/new/{pid}/tasks")
        assert problems(tasks_page.text) == [] and "Pobierz przykładowy arkusz" in tasks_page.text
        client.post(f"/v2/new/{pid}/plan", headers=headers)
        ready = text_of(client.get(f"/v2/new/{pid}/ready").text)
        assert "Plan gotowy: zdążymy w 100 na 100" in ready
        assert "Budżet z planu: 21 dni pracy" in ready and "Zmień" in ready
        client.post(f"/v2/new/{pid}/budget", data={"budget": "30"}, headers=headers)
        assert "Budżet z planu: 30 dni pracy" in text_of(client.get(f"/v2/new/{pid}/ready").text)
        definition = services.state(LOCAL_SESSION, pid).project.definition
    assert definition.settings.advanced.lambda_a == 0.014  # ADR-0034
    assert [t.predecessors for t in definition.tasks] == [(), ("T1",), ("T2",)]
    assert str(definition.settings.days_off[0]) == "2026-12-24"
