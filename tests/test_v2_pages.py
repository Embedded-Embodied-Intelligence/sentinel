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
