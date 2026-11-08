"""The v2 Laboratorium (WP16; docs/design/v2-spec.md, section 8.8): "Co jeśli?" shows the dry run
of a scenario on the latest report's day and saves nothing, "Dodaj do raportu" opens the Raport
with the scenario's items as ticked cards, and the restyled simulator runs Sentinel against no
reaction on the same events with a day counter."""

import html
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_v2_pages import Site, _site, text_of
from ui_check import problems

from sentinel.app import planning
from sentinel.app.store import LOCAL_SESSION


@pytest.fixture(scope="module", autouse=True)
def fewer_futures() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(planning, "THREAT_ROLLOUTS", 50)
        yield


@pytest.fixture(scope="module")
def lab_site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    yield from _site(tmp_path_factory)


SCENARIO = {
    "date": "2026-11-13",
    "away_rows": "0",
    "away_0_person": "ada",
    "away_0_from": "2026-11-16",
    "away_0_back": "2026-11-23",
    "grow_rows": "0",
    "grow_0_task": "T4",
    "grow_0_days": "2",
    "new_rows": "0",
    "new_0_name": "Testy płatności",
    "new_0_days": "3",
    "new_0_after": "T4",
}


def test_what_if_shows_the_effect_and_adds_to_the_report(lab_site: Site) -> None:
    pid, client, headers = lab_site.project, lab_site.client, lab_site.headers
    page = client.get("/v2/lab", params={"lang": "pl"}).text
    assert problems(page) == []
    assert "według raportu z pt. 13 lis" in text_of(page) and 'value="2026-11-13"' in page
    events = len(lab_site.services.store.events(LOCAL_SESSION, pid))
    effect = client.post(f"/v2/lab/whatif/{pid}", data=SCENARIO, headers=headers).text
    shown = text_of(effect)
    assert "Szansa 39 → 3 na 100 ▼ gorzej" in shown and "Nic nie zostało zapisane." in shown
    assert len(lab_site.services.store.events(LOCAL_SESSION, pid)) == events  # nothing saved
    found = re.search(r'href="([^"]+/report\?[^"]+)"', effect)
    assert found is not None
    report = client.get(html.unescape(found.group(1))).text  # params would replace its query
    ticked = re.findall(r'id="card-lab-\d" name="(c_[a-z]+)" value="[^"]+" checked', report)
    assert ticked == ["c_absence", "c_increase", "c_new"]
    text = text_of(report)
    assert "Anna Nowak: nieobecność od pon. 16 lis, wraca pon. 23 lis" in text
    assert "„Integracja płatności” potrwa o 2 dni dłużej" in text
    assert 'hx-trigger="load, change from:#report-form' in report  # the effect at once
    assert 'name="away_0_from" value="2026-11-16"' in page  # the first day that counts (11.3)
    alone = {**SCENARIO, "grow_0_task": "", "new_0_name": "", "new_0_days": ""}
    later = {**alone, "away_0_from": "2026-11-17"}
    note = text_of(client.post(f"/v2/lab/whatif/{pid}", data=later, headers=headers).text)
    assert "Szansa 39 → 39 na 100" in note and "ustaw „Od” na pon. 16 lis" in note
    sooner = text_of(client.post(f"/v2/lab/whatif/{pid}", data=alone, headers=headers).text)
    assert "Szansa 39 → 39" not in sooner and "ustaw „Od”" not in sooner
    empty = {**SCENARIO, "away_0_person": "", "grow_0_task": "", "new_0_name": "", "new_0_days": ""}
    nothing = text_of(client.post(f"/v2/lab/whatif/{pid}", data=empty, headers=headers).text)
    assert "Wypełnij co najmniej jeden wiersz" in nothing


@pytest.mark.data
@pytest.mark.slow  # a simulator world and five days of Sentinel (about 10 s)
def test_the_simulator_runs_sentinel_against_no_reaction(
    tmp_path_factory: pytest.TempPathFactory, psplib_root: Path
) -> None:
    del psplib_root  # the app reads data/psplib itself; the fixture skips without it
    site = next(_site(tmp_path_factory))
    client, headers = site.client, site.headers
    setup = text_of(client.get("/v2/lab", params={"lang": "pl", "tab": "sim"}).text)
    assert "Mało zakłóceń" in setup and "Dużo zakłóceń" in setup
    started = client.post(
        "/v2/lab/sim", data={"example": "small", "level": "high"}, headers=headers
    )
    poll = re.search(r'hx-get="([^"]+)"', started.text)
    assert poll is not None
    target = client.get(html.unescape(poll.group(1)), headers=headers).headers["HX-Redirect"]
    first = client.get(target, params={"lang": "pl"}).text
    assert problems(first) == []
    shown = text_of(first)
    assert "Dzień 0 z ok. 56" in shown and "Sentinel wobec braku reakcji" in shown
    assert "+1 dzień" in shown and "+5 dni" in shown and "Do końca" in shown
    client.post(f"{target}/advance", data={"days": "5"}, headers=headers)
    later = text_of(client.get(target, params={"lang": "pl"}).text)
    assert "Dzień 5 z ok. 56" in later and "na 100, że zdążymy" in later
    assert "Sentinel Zadania skończone" in later and "Bez reakcji Zadania skończone" in later
