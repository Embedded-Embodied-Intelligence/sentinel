"""The survey import (WP20): a synthetic Google Forms export becomes an aggregate of counts,
with no free text and small demographic cells merged; Mapa granic shows the switch only when
the aggregate exists."""

import csv
import importlib.util
import re
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ui_check import problems, visible_text

from sentinel.evidence import load_boundary_map
from sentinel.evidence.survey import aggregate, agreement, load_survey, majority, suppressed

REPO_ROOT = Path(__file__).resolve().parents[1]
GRID = "Kto powinien wykonywać to zadanie w firmie?"
WEIGHTS = "Jak ważne jest to kryterium, decydując, czy AI może wykonać zadanie?"
TASKS = (
    "redakcja raportu napisanego przez człowieka",
    "wersje raportu dla działów",
    "streszczenie protokołu ze spotkania",
    "zamiana wiadomości statusowych na dane o postępie",
    "prognoza dotrzymania terminu",
    "wybór działania naprawczego w projekcie",
    "streszczenie budżetu i odchyleń",
    "zatwierdzenie przesunięcia budżetu lub wydatku",
    "ocena wydajności pracownika",
    "wybór osoby na zastępstwo",
    "komunikat do zespołu o trudnej decyzji",
    "decyzja strategiczna (np. wejście na nowy rynek)",
)
CRITERIA = (
    "odwracalność i stawka",
    "łatwość sprawdzenia wyniku",
    "praca językowa czy liczby i osąd",
    "wpływ na ludzi i pieniądze",
    "wartości, relacje i wyczucie („smak”)",
    "wrażliwość danych",
)
ZONES = ("AI samodzielnie", "AI z człowiekiem", "Tylko człowiek", "Nie wiem")
OPEN = "Gdzie, Twoim zdaniem, AI w firmie nie powinna być używana i dlaczego?"


def synthetic_export(path: Path, n: int = 7) -> Path:
    """A synthetic export in the layout of Google Forms: a timestamp, the filter, the grid as
    one column per row, the weights, the two mechanisms, the open question, the demographics."""
    headers = [
        "Sygnatura czasowa",
        "Czy pracujesz lub pracowałeś(-aś) zawodowo w firmie lub organizacji?",
    ]
    headers += [f"{GRID} [{task}]" for task in TASKS] + [f"{WEIGHTS} [{c}]" for c in CRITERIA]
    headers += [
        "Chcę widzieć każdą zmianę wprowadzoną przez AI (tryb śledzenia zmian)",
        "Wyjaśnienie AI sprawia, że łatwiej akceptuję jej rekomendację",
        OPEN,
        "Twoja rola",
        "Staż pracy",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for i in range(n):
            zones = [ZONES[1]] * 12
            zones[4] = ZONES[0] if i < 5 else ZONES[1]  # the forecast: AI alone, as our map
            zones[8] = ZONES[2]  # performance review: only a person
            zones[11] = ZONES[3] if i == 0 else ZONES[2]
            weights = [str(1 + (i + k) % 5) for k in range(6)]
            role = "PM" if i < 4 else ("HR" if i < 6 else "Zarząd")
            writer.writerow(
                [
                    "2026-11-20 10:00:00",
                    "Tak" if i else "Nie",
                    *zones,
                    *weights,
                    "5",
                    "3",
                    f"Prywatny tekst {i} z nazwą firmy",
                    role,
                    "2–5 lat",
                ]
            )
    return path


def test_the_export_becomes_counts_without_free_text(tmp_path: Path) -> None:
    with synthetic_export(tmp_path / "export.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    survey = aggregate(rows, ["Anonimowy cytat."], today=date(2026, 11, 23))
    assert survey.n == 7 and survey.n_working == 6 and len(survey.processes) == 12
    assert survey.processes["P05"] == {
        "ai_samodzielnie": 5,
        "ai_z_czlowiekiem": 2,
        "tylko_czlowiek": 0,
        "dont_know": 0,
    }
    assert survey.processes["P12"]["dont_know"] == 1
    assert set(survey.criteria) == {"1", "2", "3", "4", "5", "6"} and survey.criteria["2"].n == 7
    assert survey.mechanisms["tracked_changes"].mean == 5.0
    assert survey.demographics["role"] == {"<3": 3, "PM": 4}  # HR (2) and Zarząd (1) merged
    assert survey.quotes == ["Anonimowy cytat."]
    assert "Prywatny" not in survey.model_dump_json()
    boundary = load_boundary_map()
    ours = {p.id: p.zone for p in boundary.processes}
    expected = sum(majority(survey.processes[pid]) == ours[pid] for pid in ours)
    assert agreement(survey, boundary) == expected


def test_small_cells_are_merged_and_ties_have_no_majority() -> None:
    assert suppressed(["a", "a", "a", "b", "c", "d"]) == {"a": 3, "<3": 3}
    assert suppressed(["a", "b"]) == {}
    assert majority({"ai_samodzielnie": 2, "tylko_czlowiek": 2}) is None
    assert majority({"dont_know": 4}) is None


def test_the_script_writes_the_aggregate_the_map_reads(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "import_survey", REPO_ROOT / "scripts" / "import_survey.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_survey"] = module
    spec.loader.exec_module(module)
    out = tmp_path / "survey.json"
    export = synthetic_export(tmp_path / "export.csv")
    assert module.main([str(export), "--out", str(out)]) == 0
    survey = load_survey(out)
    assert survey is not None and survey.n == 7
    assert load_survey(tmp_path / "missing.json") is None
    empty = tmp_path / "empty.csv"
    empty.write_text("Sygnatura czasowa,Pytanie\n2026-11-20,x\n", encoding="utf-8")
    assert module.main([str(empty), "--out", str(tmp_path / "x.json")]) == 1


@pytest.fixture
def surveyed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The aggregate of a synthetic export where the map looks for it."""
    from sentinel.evidence import survey as module

    with synthetic_export(tmp_path / "export.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    path = tmp_path / "survey.json"
    module.write_survey(path, aggregate(rows, today=date(2026, 11, 23)))
    monkeypatch.setattr(module, "SURVEY_PATH", path)
    return path


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    from sentinel.app.api import create_app
    from sentinel.app.config import AppConfig
    from sentinel.app.services import Services

    config = AppConfig(data_dir=tmp_path / "app", inline_jobs=True)
    services = Services(config)
    services.local_session()
    with TestClient(create_app(config, services)) as found:
        yield found


def test_the_map_has_no_switch_before_the_survey(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sentinel.evidence import survey as module

    monkeypatch.setattr(module, "SURVEY_PATH", tmp_path / "none.json")
    html = client.get("/v2/map", params={"lang": "pl"}).text
    assert "Co odpowiedzieli ludzie" not in html and "Nasza mapa" not in html


@pytest.mark.parametrize("language", ["pl", "en"])
def test_the_survey_turns_on_the_switch_of_the_map(
    client: TestClient, surveyed: Path, language: str
) -> None:
    ours = client.get("/v2/map", params={"lang": language}).text
    switch = (
        "Co odpowiedzieli ludzie (N = 7)" if language == "pl" else "What people answered (N = 7)"
    )
    assert switch in ours and problems(ours) == []
    page = client.get("/v2/map", params={"lang": language, "view": "survey"}).text
    text = re.sub(r"\s+", " ", visible_text(page))
    if language == "pl":
        assert "Zgodność z naszą mapą:" in text and "z 12 procesów" in text
        assert "Sondaż opinii, próba wygodna, bez wniosków statystycznych" in text
    else:
        assert "Agreement with our map:" in text and "convenience sample" in text
    assert problems(page) == []
