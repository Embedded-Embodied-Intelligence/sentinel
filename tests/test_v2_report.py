"""The v2 Raport and its voice (WP15; docs/design/v2-spec.md, sections 8.3 and 9): "Postęp
zgodny z planem" as cards unchecked by default, the dry-run "Wpływ na projekt", questions that
block saving, the save at the v2 gate that replaces the pending decision, and the voice
endpoint: a live preview outside the daily AI cap, a five-minute cap, nothing stored."""

import html
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_app_voice import WAV, Scripted, app, project
from test_v2_pages import Site, _site, text_of

from sentinel.app import planning
from sentinel.app.config import Limits
from sentinel.app.store import LOCAL_SESSION


@pytest.fixture(scope="module", autouse=True)
def fewer_futures() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(planning, "THREAT_ROLLOUTS", 50)
        yield


@pytest.fixture
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    yield from _site(tmp_path_factory)


def cards(fragment: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name, value in re.findall(r'name="(c_[a-z]+)" value="([^"]+)"', fragment):
        found.setdefault(name, []).append(html.unescape(value))
    return found


@pytest.mark.slow  # a few seconds of forecasts (default run: 90 s)
def test_progress_as_planned_then_save_replaces_the_decision(fresh: Site) -> None:
    pid = fresh.project
    page = fresh.client.get(f"/v2/projects/{pid}/report", params={"lang": "pl"}).text
    day = re.search(r'name="date" value="([0-9-]+)"', page)
    assert day is not None and day.group(1) == "2026-11-16"  # the working day after the last
    shown = text_of(page)
    assert "Zdarzenia od ostatniego raportu" in shown and "ostatni raport: pt. 13 lis" in shown
    planned = fresh.client.post(
        f"/v2/projects/{pid}/report/planned", data={"date": day.group(1)}, headers=fresh.headers
    ).text
    assert "„API katalogu produktów”: wykonano 30 %, zgodnie z planem" in text_of(planned)
    assert " checked" not in planned  # cards are unchecked by default (8.3)
    items = cards(planned)
    assert len(items["c_task"]) == 3
    nothing = fresh.client.post(
        f"/v2/projects/{pid}/report/impact", data={"date": day.group(1)}, headers=fresh.headers
    ).text
    assert "Zaznacz zmiany, aby zobaczyć ich wpływ." in text_of(nothing)
    assert re.search(r'type="submit"[^>]*disabled', nothing)
    form: dict[str, Any] = {"date": day.group(1), "planned_used": "1", **items}
    impact = fresh.client.post(
        f"/v2/projects/{pid}/report/impact", data=form, headers=fresh.headers
    )
    text = text_of(impact.text)
    assert "Szansa 39 → 42 na 100" in text and "Koniec wt. 22 gru → pon. 21 gru" in text
    assert not re.search(r'type="submit"[^>]*disabled', impact.text)
    one = {"date": day.group(1), "c_task": items["c_task"][:1]}
    partial = fresh.client.post(
        f"/v2/projects/{pid}/report/impact", data=one, headers=fresh.headers
    )
    assert "2 zadania w toku bez wieści: czy od pt. 13 lis nic się nie zmieniło?" in text_of(
        partial.text
    )
    saved = fresh.client.post(f"/v2/projects/{pid}/report", data=form, headers=fresh.headers)
    assert saved.headers["HX-Redirect"] == f"/v2/projects/{pid}?done=report"
    state = fresh.services.state(LOCAL_SESSION, pid)
    assert [e.status for e in state.recommendations] == ["none", "superseded", "open"]
    assert state.open is not None and state.open.validity is not None
    overview = text_of(fresh.client.get(saved.headers["HX-Redirect"]).text)
    assert "Raport zapisany." in overview and "42 na 100" in overview


def test_an_open_question_blocks_saving(site_report: Site) -> None:
    pid = site_report.project
    base = {"date": "2026-11-16", "planned_used": "1", "qn": "1"}
    blocked = site_report.client.post(
        f"/v2/projects/{pid}/report/impact", data=base, headers=site_report.headers
    ).text
    assert "Najpierw odpowiedz na pytania." in text_of(blocked)
    assert re.search(r'type="submit"[^>]*disabled', blocked)
    refused = site_report.client.post(
        f"/v2/projects/{pid}/report", data=base, headers=site_report.headers
    )
    assert refused.status_code == 422
    skipped = site_report.client.post(
        f"/v2/projects/{pid}/report/impact",
        data={**base, "q-0": "skip"},
        headers=site_report.headers,
    ).text
    assert not re.search(r'type="submit"[^>]*disabled', skipped)


@pytest.fixture(scope="module")
def site_report(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    yield from _site(tmp_path_factory)


def test_the_form_adds_ticked_cards_and_keeps_its_errors(site_report: Site) -> None:
    """ "Wypełnij formularz" (8.3, WP16): the first form's fields, read by its reader, become
    ticked cards; a wrong value keeps the form with its message and adds nothing; an untouched
    form adds nothing, a share shown in whole per cent included."""
    pid, client, headers = site_report.project, site_report.client, site_report.headers
    page = client.get(f"/v2/projects/{pid}/report", params={"lang": "pl"}).text
    assert 'id="form-panel"' in page and "Zadania w toku i najbliższe" in text_of(page)
    base = {"date": "2026-11-16", "away_rows": "0", "grow_rows": "0", "new_rows": "0"}
    filled = {
        **base,
        "shown": "T3",
        "status_T3": "done",
        "finish_T3": "2026-11-16",
        "away_0_person": "ada",
        "away_0_from": "2026-11-17",
        "away_0_back": "2026-11-20",
        "new_0_name": "Testy płatności",
        "new_0_days": "3",
        "new_0_after": "T3",
    }
    added = client.post(f"/v2/projects/{pid}/report/form", data=filled, headers=headers).text
    shown = text_of(added)
    assert "„API katalogu produktów” skończone pon. 16 lis" in shown
    assert "Anna Nowak: nieobecność od wt. 17 lis, wraca pt. 20 lis" in shown
    assert "Nowe zadanie „Testy płatności”, 3 dni" in shown
    assert len(re.findall(r'name="c_[a-z]+" value="[^"]+" checked', added)) == 3
    # An announced absence from a later day counts at once (spec 11.3, v2.4.1): Anna away
    # from Thu 19 Nov lowers the chance in a report of Mon 16 Nov.
    away = '{"person":"ada","first_day":"2026-11-19","return_date":"2026-11-27"}'
    impact = client.post(
        f"/v2/projects/{pid}/report/impact",
        data={"date": "2026-11-16", "c_absence": away},
        headers=headers,
    )
    chance = re.search(r"Szansa (\d+) → (\d+) na 100", text_of(impact.text))
    assert chance is not None and int(chance.group(2)) < int(chance.group(1))
    assert 'id="form-panel-body" class="stack" hx-swap-oob="true"' in added
    wrong = {**base, "grow_0_task": "T3", "grow_0_days": "-2"}
    kept = client.post(f"/v2/projects/{pid}/report/form", data=wrong, headers=headers).text
    assert "Podaj dodatkowe dni robocze jako liczbę większą od 0." in text_of(kept)
    assert "data-card" not in kept and 'value="-2"' in kept
    untouched = {**base, "shown": "T3", "status_T3": "in_progress", "percent_T3": "27"}
    same = client.post(f"/v2/projects/{pid}/report/form", data=untouched, headers=headers).text
    assert "Formularz jeszcze niczego nie zmienia" in text_of(same) and "data-card" not in same


def send(client: TestClient, path: str, csrf: dict[str, str], seconds: str, body: bytes) -> Any:
    headers = {"content-type": "audio/webm", "x-recording-seconds": seconds, **csrf}
    return client.post(path, content=body, headers=headers)


def test_a_visitor_cannot_use_up_the_ai_or_the_recordings(tmp_path: Path) -> None:
    """WP17: the public demo caps each visitor's AI calls and seconds of audio a day, previews
    included (each at least the 10 s a provider bills); another visitor keeps their own."""
    scripted = Scripted("Interfejs skończony.")  # 15.1 s each: 16 s counted
    limits = Limits(
        llm_calls_per_day=100,
        llm_calls_per_session=1,
        voice_seconds_per_day=1000,
        voice_seconds_per_session=40,
    )
    with app(tmp_path, scripted, cap=100, limits=limits) as first:
        pid, csrf = project(first)
        path = f"/v2/transcribe?project={pid}&preview=1"
        codes = [send(first, path, csrf, "15", WAV).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]  # 16, 32, 48 s: the fourth is refused
        refused = send(first, path, csrf, "15", WAV).json()["error"]
        assert "limit" in refused.lower()
        with TestClient(first.app) as second:
            pid, csrf = project(second)
            final = f"/v2/transcribe?project={pid}&preview=0"
            assert send(second, final, csrf, "15", WAV).status_code == 200
            assert send(second, final, csrf, "15", WAV).status_code == 429  # one AI call a day


def test_the_live_preview_is_outside_the_cap_and_nothing_is_stored(tmp_path: Path) -> None:
    scripted = Scripted("Interfejs skończony.")
    with app(tmp_path, scripted, cap=1) as client:
        pid, csrf = project(client)
        for _ in range(3):  # previews every few seconds do not use the day's AI calls
            preview = send(client, f"/v2/transcribe?project={pid}&preview=1", csrf, "3", WAV)
            assert preview.status_code == 200 and preview.json()["text"] == "Interfejs skończony."
        final = send(client, f"/v2/transcribe?project={pid}&preview=0", csrf, "9", WAV + b"x")
        assert final.status_code == 200
        again = send(client, f"/v2/transcribe?project={pid}", csrf, "9", WAV)
        assert again.status_code == 429  # the final transcription counts
        too_long = send(client, "/v2/transcribe", csrf, "400", WAV)
        assert too_long.status_code == 413
        store = client.app.state.services.store  # type: ignore[attr-defined]
    assert len(scripted.calls) == 4 and "Build API" in scripted.calls[0][3]
    with sqlite3.connect(store.path) as db:
        dump = "\n".join(db.iterdump())
        logged = db.execute("SELECT seconds FROM requests WHERE seconds IS NOT NULL").fetchall()
    assert "Interfejs" not in dump and "unique" not in dump
    assert logged == [(15.1,)]  # only the final recording's length, not the previews'
