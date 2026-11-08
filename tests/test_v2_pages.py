"""The pages of the v2 interface (WP15; docs/design/v2-spec.md; spec section 11.8) on the
showcase project: every screen in Polish and English without internal terms, missing texts, raw
codes or ISO dates, the theme cookie, the decisions taken from the overview and the decision
page with the promised numbers shown after an approval (the WP12 guarantee, spec 11.5)."""

import csv
import html
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar
from ui_check import problems, visible_text

from sentinel.app import planning, showcase
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.names import accusative, vocabulary
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION
from sentinel.app.ui.v2.decision import reasoning
from sentinel.app.ui.v2.log import LogItem, csv_of
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import TITLE_LIMIT

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


def test_the_log_reads_as_the_record(site: Site) -> None:
    """Dziennik (8.6): who did what, the effect chips, the pending proposal's brief and fate,
    the chance over time with a dot per report linked to its entry, the filters and the CSV."""
    pid = site.project
    html = site.client.get(f"/v2/projects/{pid}/log", params={"lang": "pl"}).text
    text = text_of(html)
    assert "Szansa w czasie" in text and "Pobierz dziennik (CSV)" in text
    assert "Ty Zapisano raport z pt. 13 lis Szansa 92 → 39 na 100 ▼ gorzej" in text
    assert "Decyzja w tamtej chwili Szansa 39 → 57 na 100" in text
    assert "Stan decyzji oczekuje" in text
    labels = re.findall(r'aria-label="([^"]+)" data-open-entry', html.replace("\xa0", " "))
    assert labels == [
        "Plan gotowy: 83 na 100",
        "Zapisano raport z pt. 6 lis: 92 na 100",
        "Zapisano raport z pt. 13 lis: 39 na 100",
    ]
    anchors = re.findall(r'<a href="#(e-[^"]+)" aria-label', html)
    assert len(anchors) == 3 and all(f'id="{anchor}"' in html for anchor in anchors)
    params = {"lang": "pl", "show": "decisions"}
    only = text_of(site.client.get(f"/v2/projects/{pid}/log", params=params).text)
    listed = only[only.index("Wpisy") : only.index("Menu główne", only.index("Wpisy"))]
    assert "Nowa propozycja" in listed and "Zapisano raport" not in listed
    table = site.client.get(f"/v2/projects/{pid}/log.csv", params={"lang": "pl"})
    assert table.headers["content-disposition"] == 'attachment; filename="dziennik.csv"'
    rows = list(csv.reader(io.StringIO(table.text)))
    assert rows[0][:6] == ["data", "godzina", "projekt", "kto", "rodzaj", "zdarzenie"]
    assert rows[5][3:8] == ["Ty", "Raporty", "Zapisano raport z pt. 13 lis", "92", "39"]
    assert rows[6][3:5] == ["Sentinel", "Decyzje"] and rows[6][6:9] == ["39", "57", "oczekuje"]


def test_the_plan_shows_the_schedule_tasks_and_team(site: Site) -> None:
    """Plan (8.7): the Gantt chart with the forecast's band and the main risk marked in words,
    the tasks with a correction only for those not started, and the team's absences by date and
    next week's workload from the plan, never anyone's performance."""
    base = f"/v2/projects/{site.project}/plan"
    schedule = site.client.get(base, params={"lang": "pl"}).text
    shown = text_of(schedule)
    assert "Prognoza: najpewniej wt. 22 gru, w złym razie wt. 5 sty 2027" in shown
    assert "API katalogu produktów ryzyko" in shown and "Pobierz plan (CSV)" in shown
    assert 'class="bar-away' in schedule and 'class="g-window"' in schedule
    tasks = site.client.get(base, params={"lang": "pl", "view": "tasks"}).text
    rows = re.findall(r'<tr id="task-([^"]+)"[^>]*>(.*?)</tr>', tasks, re.S)
    fixable = {key for key, row in rows if "data-toggle" in row}
    assert fixable and all("nierozpoczęte" in row for key, row in rows if key in fixable)
    team = text_of(site.client.get(base, params={"lang": "pl", "view": "team"}).text)
    assert "Przyszły tydzień: pon. 16 lis – pt. 20 lis" in team
    assert "Bartosz Kowalski Programista backendu czw. 12 lis – wraca pon. 23 lis" in team
    assert "nieobecność cały tydzień" in team and "ok. 5 z 5 dni" in team
    assert "Sentinel nie mierzy niczyjej wydajności" in team


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_a_task_not_started_is_corrected_from_the_plan(fresh: Site) -> None:
    pid, client, headers = fresh.project, fresh.client, fresh.headers
    path = f"/v2/projects/{pid}/plan/tasks/T4"  # "Integracja płatności", not started, 5 days
    form = {"duration": "0", "crew_0": "1", "after": "T3"}
    refused = client.post(path, data=form, headers=headers)
    assert refused.status_code == 422 and "Podaj liczbę dni roboczych" in text_of(refused.text)
    saved = client.post(path, data={**form, "duration": "7"}, headers=headers)
    assert saved.headers["HX-Redirect"].endswith("/plan?view=tasks&done=corrected")
    log = text_of(client.get(f"/v2/projects/{pid}/log").text)
    assert "Ty Poprawiono „Integracja płatności”: szacunek 5 → 7 dni" in log
    started = client.post(f"/v2/projects/{pid}/plan/tasks/T3", data=form, headers=headers)
    assert started.status_code == 422  # a task under way keeps its definition


def test_the_settings_read_as_the_spec(site: Site) -> None:
    """Ustawienia (8.10): appearance, language and the model in plain words; the project's
    basics, team, days off, calendar reminder (Thursday 17:00), exports, the fixed text of
    section 3 and the red zone."""
    app = text_of(site.client.get("/v2/settings", params={"lang": "pl"}).text)
    for label in ("Wygląd", "Jasny (domyślny)", "Ciemny", "Systemowy", "Język", "Model AI"):
        assert label in app, label
    assert "Chmura (zalecany) Dokładniejszy" in app
    assert "Lokalny Dane nie wychodzą z firmy; wolniejszy" in app
    html = site.client.get(f"/v2/projects/{site.project}/settings", params={"lang": "pl"}).text
    shown = text_of(html)
    for label in ("Podstawy", "Zespół", "Dni wolne w firmie", "Kalendarz", "Eksport"):
        assert label in shown, label
    assert "Przypomnienie o raporcie" in shown and '<option value="3" selected>' in html
    assert 'value="17:00"' in html
    assert (
        "Jak Sentinel podejmuje decyzje Sentinel zbiera informacje, analizuje projekt i "
        "przygotowuje decyzje. Każdą zmianę zatwierdzasz Ty."
    ) in shown
    assert "Usuń projekt" in shown and 'class="card stack danger-zone"' in html
    assert "Wkrótce" not in shown


def test_the_demo_sets_no_model_or_key(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path, demo=True, inline_jobs=True, showcase=False)
    with TestClient(create_app(config, Services(config))) as client:
        page = client.get("/v2/settings", params={"lang": "pl"}).text
        assert "W pokazie model AI ustawia jego właściciel" in text_of(page)
        assert 'name="api_key"' not in page and 'name="groq_key"' not in page
        token = client.get("/api/session").json()["csrf_token"]
        refused = client.post(
            "/v2/settings/ai",
            data={"choice": "cloud", "api_key": "x"},
            headers={"X-CSRF-Token": token, "HX-Request": "true"},
        )
        assert refused.status_code == 403


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_project_settings_are_saved_and_the_project_deleted(fresh: Site) -> None:
    pid, client, headers = fresh.project, fresh.client, fresh.headers
    base = f"/v2/projects/{pid}/settings"
    refused = client.post(
        f"{base}/basics", data={"name": "", "deadline": "2026-12-18"}, headers=headers
    )
    assert refused.status_code == 422
    basics = {"name": "Sklep 2.0", "deadline": "2026-12-18", "budget": "90"}
    saved = client.post(f"{base}/basics", data=basics, headers=headers)
    assert saved.headers["HX-Redirect"].endswith("/settings?done=basics")
    assert fresh.services.live(LOCAL_SESSION, pid, "pl").definition.budget == 90
    reminder = {"reminder_day": "1", "reminder_time": "09:30"}
    client.post(f"{base}/reminder", data=reminder, headers=headers)
    calendar = fresh.services.store.calendar(LOCAL_SESSION, pid)
    assert calendar is not None and (calendar.reminder_day, calendar.reminder_time) == (1, "09:30")
    overview = text_of(client.get(f"/v2/projects/{pid}", params={"lang": "pl"}).text)
    assert "Następny raport: wt." in overview or "Decyzja do podjęcia" in overview
    bad = client.post(
        f"{base}/reminder", data={"reminder_day": "6", "reminder_time": "25:00"}, headers=headers
    )
    assert bad.status_code == 422
    day_off = {"action": "add", "day": "2026-12-24"}
    frozen = client.post(f"{base}/days-off", data=day_off, headers=headers)
    assert frozen.status_code == 422  # the calendar is fixed after the first report
    gone = client.post(f"/v2/projects/{pid}/delete", headers=headers)
    assert gone.headers["HX-Redirect"] == "/v2?done=deleted"
    assert fresh.services.projects(LOCAL_SESSION) == []
    assert "Usunięto projekt." in text_of(client.get(gone.headers["HX-Redirect"]).text)


def test_the_new_screens_have_calm_empty_states(tmp_path: Path) -> None:
    """No project, or a draft without a plan: every WP16 screen says what to do next."""
    config = AppConfig(data_dir=tmp_path, inline_jobs=True)
    services = Services(config)
    services.local_session()
    with TestClient(create_app(config, services)) as client:
        expected = {
            "/v2/log": "Dziennik jest pusty",
            "/v2/lab": "Brak projektu z planem",
            "/v2/settings": "Model AI",
        }
        for path, words in expected.items():
            response = client.get(path, params={"lang": "pl"})
            assert response.status_code == 200 and problems(response.text) == [], path
            assert words in text_of(response.text), path
        draft = showcase.definition("pl").model_copy(update={"tasks": ()})
        pid = services.create(LOCAL_SESSION, draft, "pl").id
        for tab, words in (
            ("plan", "Brak planu"),
            ("log", "Utworzono projekt"),
            ("settings", "Podstawy"),
        ):
            response = client.get(f"/v2/projects/{pid}/{tab}", params={"lang": "pl"})
            assert response.status_code == 200 and problems(response.text) == [], tab
            assert words in text_of(response.text), tab


def test_a_log_cell_is_never_a_formula() -> None:
    item = LogItem(datetime(2026, 11, 9, 9, tzinfo=UTC), "Ty", "=HYPERLINK(1)", "/", "checkin")
    row = list(csv.reader(io.StringIO(csv_of(TextsV2("en"), [item]))))[1]
    assert row[5] == "'=HYPERLINK(1)"


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


def test_the_banner_is_quiet_where_the_page_shows_it_already(site: Site) -> None:
    """WP17: the banner reports a new decision elsewhere, not on the project's own Pulpit or
    decision page, which show it themselves (a saved report was announced twice)."""
    pid = site.project
    since = {"since": "2000-01-01T00:00:00+00:00", "lang": "pl"}

    def banner(page: str) -> str:
        current = {"HX-Current-URL": f"http://testserver{page}", "HX-Request": "true"}
        return text_of(site.client.get("/v2/banner", params=since, headers=current).text)

    elsewhere = banner("/v2") + banner(f"/v2/projects/{pid}/plan")
    assert elsewhere.count("nowa decyzja do podjęcia") == 2
    here = banner(f"/v2/projects/{pid}") + banner(f"/v2/projects/{pid}/decisions/6")
    assert "nowa decyzja" not in here


def test_the_first_interface_links_to_v2(site: Site) -> None:
    assert 'href="/v2?look=v2"' in site.client.get("/", params={"lang": "pl"}).text


def test_the_home_can_be_v2_and_v1_stays_a_link_away(tmp_path: Path) -> None:
    """WP17: with `home = "v2"` (the public demo) "/" opens v2; "Poprzedni wygląd" shows v1
    and keeps it until v1's link back to v2."""
    config = AppConfig(data_dir=tmp_path, home="v2", showcase=False)
    with TestClient(create_app(config)) as client:
        first = client.get("/", params={"lang": "en"}, follow_redirects=False)
        assert first.status_code == 303 and first.headers["location"] == "/v2?lang=en"
        assert 'href="/?look=v1"' in client.get("/v2").text
        old = client.get("/", params={"look": "v1"}, follow_redirects=False)
        assert old.status_code == 200 and client.cookies.get("sentinel_look") == "v1"
        assert client.get("/", follow_redirects=False).status_code == 200  # remembered
        client.get("/v2", params={"look": "v2"})
        assert client.get("/", follow_redirects=False).status_code == 303


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
    # The short title; the full wording heads "Kogo dotyczy" (WP16 hotfix).
    assert (
        "Decyzja do podjęcia" in text
        and "Cezary zastępuje Bartosza w „API katalogu produktów”" in text
    )
    who = text[text.index("Kogo dotyczy") : text.index("Koszt zwłoki")]
    assert who.startswith("Kogo dotyczy Zastępstwo: Cezary Mazur przejmuje udział osoby nieobecnej")
    assert "Bartosz Kowalski: po powrocie wraca do swoich zadań" in who
    assert "za osobę" not in who and who.count("Cezary") == 1  # nothing twice (WP17)
    # The contrast is the best option of another kind, never the same one with a re-plan (56).
    assert (
        "Najlepsza możliwość innego rodzaju, „Rezygnacja z «Karty podarunkowe»”, dałaby mniej "
        "(39 na 100), choć bez dodatkowego kosztu." in text
    )
    assert "56 na 100" not in text[: text.index("Kogo dotyczy")]
    assert "Każdy dzień czekania to ok. \u22125 na 100." in text
    assert "ważna do czw. 19 lis" in text
    assert "Bez zmian 39 na 100" in text  # every option, "Bez zmian" included
    dist = site.client.get(f"/v2/projects/{site.project}/decisions/{seq}/distribution")
    assert "Na 200: w terminie 114, później 86." in text_of(dist.text)
    assert "Na 200: w terminie 78, później 122." in text_of(dist.text)
    state = site.services.state(LOCAL_SESSION, site.project)
    validity = state.recommendation(seq).validity  # type: ignore[union-attr]
    assert validity is not None and validity.valid_day == 12 and validity.chances[0] == 0.57


def test_decision_titles_are_short_on_the_pulpit_and_the_start(site: Site) -> None:
    """WP16 hotfix: a decision's title is short and plain, by first names, the person stood in
    for declined in Polish; the Pulpit card and the Start list show it too."""
    title = "Cezary zastępuje Bartosza w „API katalogu produktów”"
    overview = text_of(site.client.get(f"/v2/projects/{site.project}", params={"lang": "pl"}).text)
    start = text_of(site.client.get("/v2", params={"lang": "pl"}).text)
    assert title in overview and title in start
    assert "przejmuje udział" not in overview + start
    english = site.client.get(f"/v2/projects/{site.project}", params={"lang": "en"}).text
    assert "Cezary stands in for Bartosz on “API katalogu produktów”" in text_of(english)
    for language in LANGUAGES:
        for rec in site.services.live(LOCAL_SESSION, site.project, language).recommendations:
            shown = [rec.headline, *(a.headline for a in rec.alternatives)]
            assert all(0 < len(words) <= TITLE_LIMIT for words in shown), shown


def test_polish_first_names_are_declined_for_a_title() -> None:
    expected = {
        "Bartosz": "Bartosza",
        "Anna": "Annę",
        "Cezary": "Cezarego",
        "Antoni": "Antoniego",
        "Marek": "Marka",
        "Paweł": "Pawła",
        "Staś": "Stasia",
        "Aleksander": "Aleksandra",
        "Julia": "Julię",
    }
    assert {name: accusative(name, "pl") for name in expected} == expected
    assert all(accusative(name, "pl") for name in vocabulary("pl").simulator.first_names)
    assert accusative("Tester 1", "pl") is None and accusative("Anna Nowak", "pl") is None
    assert accusative("Bartosz", "en") == "Bartosz"


def test_the_reasoning_contrasts_another_kind_of_action(site: Site) -> None:
    """WP16 hotfix: "Uzasadnienie" contrasts the best option of another kind of action, never
    the same action with a re-plan; within the materiality threshold of the chance it says that
    a similar result was possible and why the choice stands."""
    view = site.services.live(LOCAL_SESSION, site.project, "pl")
    rec = next(r for r in view.recommendations if r.action == "subst")
    assert rec.with_action is not None
    p, delay = rec.with_action.p_on_time, rec.with_action.tardiness
    t = TextsV2("pl")
    same = next(a for a in rec.alternatives if a.action == "subst")  # with a re-plan
    other = next(a for a in rec.alternatives if a.action == "descope")
    better_same = same.model_copy(update={"p_on_time": p + 0.1})
    close = other.model_copy(update={"p_on_time": p - 0.01, "tardiness": delay})

    def second(*alternatives: object) -> str:
        return reasoning(t, rec.model_copy(update={"alternatives": list(alternatives)}), True)[1]

    assert second(better_same, close) == (
        "Podobny wynik dałoby też „Rezygnacja z «Karty podarunkowe»”; wybrano prostsze rozwiązanie."
    )
    slower = close.model_copy(update={"tardiness": delay + 1.0})
    assert second(slower).endswith("; wybrano wariant z mniejszym oczekiwanym opóźnieniem.")
    assert second(close.model_copy(update={"p_on_time": p - rec.eps_d})).startswith(
        "Najlepsza możliwość innego rodzaju, „Rezygnacja z «Karty podarunkowe»”, dałaby mniej"
    )
    assert "Cezary" not in second(better_same)  # only the same kind: no contrast with it


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
    log = text_of(fresh.client.get(f"/v2/projects/{fresh.project}/log").text)
    assert (
        "Ty Odrzucono: Cezary zastępuje Bartosza" in log and "(inny powód)" in log
    )  # the fate in the log
    assert log.count(f"Stan decyzji odrzucona Powód: Inny powód: „{words}”") == 2  # 8.6


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
    assert events.index("Nowa propozycja: Cezary zastępuje Bartosza") < events.index(
        "Utworzono projekt"
    )
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


# ---- the calendar feed (section 8.9, ADR-0035), read by a standard parser (dev only)


def link_of(client: TestClient, project: str, headers: dict[str, str]) -> str:
    """Make the project's calendar link and read it from the settings page; its path."""
    client.post(f"/v2/projects/{project}/calendar", headers=headers)
    page = client.get(f"/v2/projects/{project}/settings", params={"lang": "pl"}).text
    assert "Kto ma ten link, widzi imiona osób i daty nieobecności." in page
    found = re.search(r'id="calendar-link" value="https?://testserver([^"]+)"', page)
    assert found is not None
    return html.unescape(found.group(1))


def events(text: str) -> dict[str, list[tuple[object, object]]]:
    by_summary: dict[str, list[tuple[object, object]]] = {}
    for event in Calendar.from_ical(text).walk("VEVENT"):
        start = event.decoded("DTSTART")
        end = event.decoded("DTEND") if "DTEND" in event else None
        by_summary.setdefault(str(event.get("SUMMARY")), []).append((start, end))
    return by_summary


def test_the_feed_is_valid_icalendar_with_the_project_dates(site: Site) -> None:
    client, headers, pid = site.client, site.headers, site.project
    path = link_of(client, pid, headers)
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    text = response.text
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    parsed = Calendar.from_ical(text)
    assert str(parsed.get("X-WR-CALNAME")) == "Sentinel: Nowa odsłona sklepu internetowego"
    found = events(text)
    uids = [str(e.get("UID")) for e in parsed.walk("VEVENT")]
    assert len(uids) == len(set(uids))
    deadline = found["Termin: Nowa odsłona sklepu internetowego"]
    assert deadline == [(date(2026, 12, 18), date(2026, 12, 19))]
    assert found["Nieobecność: Bartosz Kowalski"] == [(date(2026, 11, 12), date(2026, 11, 23))]
    assert any(
        name.startswith("Decyzja ważna do dziś: Cezary zastępuje Bartosza") for name in found
    )
    valid = next(v for k, v in found.items() if k.startswith("Decyzja ważna do dziś"))
    assert valid == [(date(2026, 11, 19), date(2026, 11, 20))]
    assert "Start: Integracja płatności" in found and "Koniec: API katalogu produktów" in found
    reminder = next(
        e for e in parsed.walk("VEVENT") if str(e.get("SUMMARY")).startswith("Raport tygodniowy")
    )
    first = reminder.decoded("DTSTART")
    assert isinstance(first, datetime) and first.weekday() == 3 and first.hour == 17
    assert reminder.get("RRULE")["FREQ"] == ["WEEKLY"] and reminder.get("RRULE")["BYDAY"] == ["TH"]
    for word in ("chor", "urlop", "powód", "L4"):  # dates and names only (invariant 7)
        assert word not in text


def test_a_wrong_or_revoked_link_finds_nothing(site: Site) -> None:
    client, headers, pid = site.client, site.headers, site.project
    path = link_of(client, pid, headers)
    token = path.split("/")[3].split(".")[0]
    assert client.get(path.replace(token, "0" * 32)).status_code == 404
    client.post(f"/v2/projects/{pid}/calendar/revoke", headers=headers)
    assert client.get(path).status_code == 404
    again = link_of(client, pid, headers)
    assert again != path and client.get(again).status_code == 200
