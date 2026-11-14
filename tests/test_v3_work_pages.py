"""Raporty and Finanse of v3 (WP20; docs/design/v3-spec.md, sections 7 and 8; spec section
11.9): the pages in Polish and English, the tracked changes and the fact guard of a scripted
edit, the decisions, saving with a confirmation, export; the portfolio, the board summary with
its fact guard and a budget request that only a person approves."""

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ui_check import problems, visible_text

from sentinel.app import planning, showcase
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION
from sentinel.llm import FakeLlmClient, Message

LANGUAGES = ("pl", "en")
REPORT = (
    "Raport tygodniowy\n\n"
    "Testy integracyjne są gotowe w 15 %. Budżet to 120 dni pracy, wydaliśmy 40 dni. "
    "Ogólnie rzecz biorąc wszystko idzie dobrze, choć są pewne kwestie.\n\n"
    "Odbiór planujemy do 16 listopada."
)


def editor(messages: Sequence[Message]) -> str:
    """The scripted model: an edit drops the filler and changes one figure; a summary repeats
    the sheet's first line and adds a figure that the sheet lacks."""
    system, user = messages[0].content, messages[-1].content
    if "fact sheet that code computed" in system:
        first = user.split("\n")[0]
        return json.dumps({"text": f"{first} Rezerwa: 7 %."}, ensure_ascii=False)
    text = user.replace(" Ogólnie rzecz biorąc wszystko idzie dobrze, choć są pewne kwestie.", "")
    return json.dumps({"text": text.replace("15 %", "20 %")}, ensure_ascii=False)


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


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    data: Path = tmp_path_factory.mktemp("v3-work")
    (data / "settings.json").write_text(json.dumps({"llm": {"provider": "ollama"}}), "utf-8")
    config = AppConfig(data_dir=data, inline_jobs=True)

    def factory(settings: Any, cache: Any) -> Any:
        client = FakeLlmClient(editor, cache=cache)
        client.model = "scripted"
        return client

    services = Services(config, llm_factory=factory)
    services.local_session()
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, "pl")
    project = services.projects(LOCAL_SESSION)[0].id
    with TestClient(create_app(config, services)) as client:
        token = client.get("/api/session").json()["csrf_token"]
        yield Site(client, {"X-CSRF-Token": token, "HX-Request": "true"}, services, project)


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", visible_text(html))


def new_draft(site: Site, audiences: Sequence[str] = ("board",)) -> str:
    form = {
        "title": "Tydzień 46",
        "text": REPORT,
        "date": "2026-11-13",
        "audience": list(audiences),
    }
    response = site.client.post("/v2/reports/new", data=form, headers=site.headers)
    assert response.status_code == 200, response.text
    target = response.headers["HX-Redirect"]
    assert target.startswith("/v2/reports/draft/")
    return target.split("?")[0]


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_report_pages_are_clean(site: Site, language: str) -> None:
    base = new_draft(site, ("edit", "board"))
    for path in ("/v2/reports", "/v2/reports/new", base, f"{base}?a=edit", "/v2/finance"):
        response = site.client.get(path, params={"lang": language})
        assert response.status_code == 200, path
        assert problems(response.text) == [], path


def test_an_edit_shows_tracked_changes_and_the_fact_guard(site: Site) -> None:
    base = new_draft(site)
    html = site.client.get(base, params={"lang": "pl"}).text
    text = text_of(html)
    assert "Śledzenie zmian" in text and "Strażnik faktów" in text and "Zarząd" in text
    assert 'id="chg-0" data-state="accepted"><del>15</del><ins>20</ins>' in html
    assert "<del>Ogólnie rzecz biorąc" in html
    assert "zmienione" in text and "15 % → 20 %" in text
    assert "bez zmian" in text and "16 listopada" in text
    assert "Jeszcze nie zapisano" in text
    for decision in ("D14", "D15", "D16"):
        assert f'data-dowod="/v2/dowod/{decision}"' in html


@pytest.mark.parametrize("message", ["", "board"])
def test_the_draft_page_renders_while_the_edit_runs(site: Site, message: str) -> None:
    """The draft page with a running job (before and after the job names its audience) shows
    the polled wait, whether or not the edit has finished by the time the page renders."""
    base = new_draft(site)
    store = site.services.store
    job = store.create_job(LOCAL_SESSION, None, "redact")
    try:
        store.update_job(job.id, status="running", message=message)
        response = site.client.get(base, params={"job": job.id, "lang": "pl"})
        assert response.status_code == 200, response.text
        assert problems(response.text) == []
        assert f"{base}/wait?job={job.id}" in response.text
        text = text_of(response.text)
        assert "AI redaguje raport…" in text
        assert ("Teraz: Zarząd" in text) == bool(message)
    finally:
        store.update_job(job.id, status="done")


def test_rejecting_the_changed_number_restores_the_fact(site: Site) -> None:
    base = new_draft(site)
    html = site.client.get(base).text
    found = re.findall(r'id="chg-(\d+)"[^>]*><del>([^<]*)</del>', html)
    change = next(int(n) for n, deleted in found if deleted == "15")
    response = site.client.post(
        f"{base}/decide",
        data={"a": "board", "change": str(change), "accept": "0"},
        headers=site.headers,
    )
    text = text_of(response.text)
    # WP21: nothing left to look at on top; the fact joins the folded "bez zmian"
    assert "15 % → 20 %" not in text and 'id="guard-flagged"' not in response.text
    assert "bez zmian 15 %" in text  # listed among the facts kept
    response = site.client.post(
        f"{base}/decide", data={"a": "board", "accept": "1"}, headers=site.headers
    )
    assert "15 % → 20 %" in text_of(response.text)


def test_saving_a_version_with_a_changed_fact_asks_first(site: Site) -> None:
    base = new_draft(site)
    asked = site.client.post(f"{base}/save", headers=site.headers)
    assert "Zapisz mimo to" in text_of(asked.text) and "HX-Redirect" not in asked.headers
    saved = site.client.post(f"{base}/save", data={"confirm": "1"}, headers=site.headers)
    target = saved.headers["HX-Redirect"]
    page = site.client.get(target, params={"lang": "pl"})
    assert page.status_code == 200 and "Zapisano" in text_of(page.text)
    assert "Tydzień 46" in text_of(site.client.get("/v2/reports").text)
    again = site.client.post(f"{target}/edit", headers=site.headers)
    assert again.headers["HX-Redirect"].startswith("/v2/reports/draft/")


def test_export_asks_on_a_warning_then_gives_markdown_and_a_print_page(site: Site) -> None:
    base = new_draft(site)
    asked = site.client.get(f"{base}/export", params={"a": "board", "fmt": "md"})
    assert "Eksportuj mimo to" in text_of(asked.text)
    md = site.client.get(f"{base}/export", params={"a": "board", "fmt": "md", "confirm": "1"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("# Tydzień 46") and "20 %" in md.text and "Ogólnie" not in md.text
    printed = site.client.get(
        f"{base}/export", params={"a": "board", "fmt": "html", "confirm": "1"}
    )
    assert "data-print" in printed.text and problems(printed.text) == []


def test_nothing_of_a_report_is_stored_before_it_is_saved(site: Site) -> None:
    before = len(site.services.store.reports(LOCAL_SESSION))
    new_draft(site)
    assert len(site.services.store.reports(LOCAL_SESSION)) == before
    for job in site.services.store.project_jobs(LOCAL_SESSION, site.project):
        assert "Raport tygodniowy" not in json.dumps(job.result or {})


def test_a_new_report_needs_text_and_an_audience(site: Site) -> None:
    form = {"title": "", "text": " ", "date": "2026-11-13", "audience": ["board"]}
    response = site.client.post("/v2/reports/new", data=form, headers=site.headers)
    assert "Najpierw wpisz lub wklej raport." in text_of(response.text)
    form = {"title": "", "text": REPORT, "date": "2026-11-13"}
    response = site.client.post("/v2/reports/new", data=form, headers=site.headers)
    assert "Wybierz co najmniej jednego odbiorcę." in text_of(response.text)


# ---- Finanse


def test_the_portfolio_is_computed_by_code_and_the_summary_is_guarded(site: Site) -> None:
    html = site.client.get("/v2/finance", params={"lang": "pl"}).text
    text = text_of(html)
    assert "Portfel projektów" in text and "Streszczenie dla zarządu (AI)" in text
    assert "Nowa odsłona sklepu internetowego" in text and "na 100 w budżecie" in text
    assert 'data-dowod="/v2/dowod/D17"' in html and "AI nie ma prawa zatwierdzać" in text
    line = site.services.portfolio(LOCAL_SESSION, "pl")[0]
    assert f">{round(line.budget)}<" in html.replace(" ", "")
    started = site.client.post("/v2/finance/summary", headers=site.headers)
    job = re.search(r"job=([\w-]+)", started.text)
    assert job, started.text
    done = text_of(site.client.get("/v2/finance/summary", params={"job": job[1]}).text)
    assert "Strażnik faktów" in done and "Nowe w tej wersji: 7 %" in done
    assert "nie jest zapisywane" in done


@pytest.fixture
def two(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    """Two live projects with a plan (the showcase twice, the second renamed)."""
    data: Path = tmp_path_factory.mktemp("v3-finance")
    config = AppConfig(data_dir=data, inline_jobs=True)
    services = Services(config)
    services.local_session()
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, "pl")
    services.showcase(LOCAL_SESSION, "pl")
    first, second = (p.id for p in services.projects(LOCAL_SESSION))
    definition = services.state(LOCAL_SESSION, second).project.definition
    services.update_definition(
        LOCAL_SESSION, second, definition.model_copy(update={"name": "Aplikacja mobilna"}), "pl"
    )
    with TestClient(create_app(config, services)) as client:
        token = client.get("/api/session").json()["csrf_token"]
        yield Site(client, {"X-CSRF-Token": token, "HX-Request": "true"}, services, first)


def test_a_budget_request_changes_nothing_until_a_person_approves_it(two: Site) -> None:
    lines = {line.name: line for line in two.services.portfolio(LOCAL_SESSION, "pl")}
    shop, app = lines["Nowa odsłona sklepu internetowego"], lines["Aplikacja mobilna"]
    form = {"source": shop.id, "target": app.id, "amount": "5", "reason": "Więcej testów"}
    filed = two.client.post("/v2/finance/requests", data=form, headers=two.headers)
    assert filed.headers["HX-Redirect"] == "/v2/finance"
    after = {line.name: line.budget for line in two.services.portfolio(LOCAL_SESSION, "pl")}
    assert after == {shop.name: shop.budget, app.name: app.budget}
    text = text_of(two.client.get("/v2/finance").text)
    assert "czeka na decyzję człowieka" in text and "AI nie ma prawa zatwierdzać" in text
    (request,) = two.services.budget_requests(LOCAL_SESSION)
    asked = two.client.get(f"/v2/finance/requests/{request.id}/confirm", headers=two.headers)
    assert "Tak, zatwierdzam" in text_of(asked.text)
    two.client.post(f"/v2/finance/requests/{request.id}/approve", headers=two.headers)
    moved = {line.name: line.budget for line in two.services.portfolio(LOCAL_SESSION, "pl")}
    assert moved == {shop.name: shop.budget - 5, app.name: app.budget + 5}
    assert "zatwierdzony i zastosowany" in text_of(two.client.get("/v2/finance").text)
    log = text_of(two.client.get("/v2/log", params={"lang": "pl"}).text)
    assert "Budżet przesunięty zatwierdzonym wnioskiem" in log and "Więcej testów" in log
    again = two.client.post(f"/v2/finance/requests/{request.id}/approve", headers=two.headers)
    assert again.status_code == 409


def test_a_request_the_source_cannot_afford_is_recorded_as_not_applied(two: Site) -> None:
    lines = two.services.portfolio(LOCAL_SESSION, "pl")
    source, target = lines
    amount = str(round(source.budget - source.spent + 10))
    form = {"source": source.id, "target": target.id, "amount": amount, "reason": ""}
    two.client.post("/v2/finance/requests", data=form, headers=two.headers)
    (request,) = two.services.budget_requests(LOCAL_SESSION)
    two.client.post(f"/v2/finance/requests/{request.id}/approve", headers=two.headers)
    (done,) = two.services.budget_requests(LOCAL_SESSION)
    assert done.status == "not_applied" and done.why == "below_spent"
    assert [line.budget for line in two.services.portfolio(LOCAL_SESSION, "pl")] == [
        source.budget,
        target.budget,
    ]
    text = text_of(two.client.get("/v2/finance").text)
    assert "zatwierdzony, nie zastosowany" in text and "wydał już" in text
    same = {"source": source.id, "target": source.id, "amount": "3", "reason": ""}
    refused = two.client.post("/v2/finance/requests", data=same, headers=two.headers)
    assert "Wybierz dwa różne projekty." in text_of(refused.text)
