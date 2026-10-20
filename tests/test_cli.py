"""`sentinel inspect` and `sentinel baselines` commands."""

from pathlib import Path

import pytest

from sentinel.cli import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, str], str]:
    """Run the CLI; return exit status, printed `label: value` fields and stderr."""
    status = main(list(argv))
    out, err = capsys.readouterr()
    fields = dict(line.split(":", 1) for line in out.splitlines())
    return status, {k: v.strip() for k, v in fields.items()}, err


def test_inspect_file_prints_summary(capsys: pytest.CaptureFixture[str], tiny_path: Path) -> None:
    status, fields, _ = run(capsys, "inspect", "--file", str(tiny_path))
    assert status == 0
    assert fields["name"] == "fixtures/tiny"
    assert fields["real activities"] == "3"
    assert fields["roles"] == "R1=3 (3 workers)"
    assert fields["total duration"] == "9"
    assert fields["LB0"] == "7"
    assert fields["reference"] == "none"


def test_inspect_missing_instance(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    status, _, err = run(capsys, "inspect", "j30/j301_1", "--root", str(tmp_path))
    assert status == 1
    assert "not found" in err
    assert "fetch_psplib.py" in err


@pytest.mark.parametrize(
    "argv",
    [["inspect"], ["inspect", "j30/j301_1", "--file", "x.sm"], ["inspect", "j301_1"], []],
)
def test_inspect_usage_errors(capsys: pytest.CaptureFixture[str], argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2
    capsys.readouterr()


@pytest.mark.data
def test_inspect_psplib_instance_with_reference(
    capsys: pytest.CaptureFixture[str], psplib_root: Path
) -> None:
    status, fields, _ = run(capsys, "inspect", "j30/j301_1", "--root", str(psplib_root))
    assert status == 0
    assert fields["real activities"] == "30"
    reference = dict(item.split("=") for item in fields["reference"].split(", "))
    assert int(reference["opt"]) == 43  # PSPLIB optimum of j301_1
    assert int(reference["opt"]) >= int(fields["LB0"]) == 38


def test_baselines_on_a_limited_set(
    capsys: pytest.CaptureFixture[str], fake_study: Path, tmp_path: Path
) -> None:
    cache = tmp_path / "cli-cache"
    argv = ["baselines", "--set", "tiny", "--method", "cpsat_det", "--config", str(fake_study)]
    argv += ["--limit", "1", "--workers", "1", "--cache", str(cache)]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "1 computed, 0 cached; statuses: OPTIMAL 1" in out
    assert "plan / C* (opt): mean 1.0000, max 1.0000, at C* 1 of 1" in out
    assert (cache / "tiny" / "tiny1_1.json").is_file()
    assert not (cache / "tiny" / "tiny1_2.json").exists()
    assert main(argv) == 0
    assert "0 computed, 1 cached" in capsys.readouterr().out


def test_baselines_in_parallel_use_the_config_cache(
    capsys: pytest.CaptureFixture[str], fake_study: Path, tmp_path: Path
) -> None:
    argv = ["baselines", "--set", "tiny", "--method", "sgs_lft", "--config", str(fake_study)]
    assert main([*argv, "--workers", "2"]) == 0
    assert "2 computed, 0 cached; statuses: FEASIBLE 2" in capsys.readouterr().out
    for stem in ("tiny1_1", "tiny1_2"):
        assert "sgs_lft" in (tmp_path / "cache" / "tiny" / f"{stem}.json").read_text("utf-8")


def test_baselines_errors(
    capsys: pytest.CaptureFixture[str], fake_study: Path, tmp_path: Path
) -> None:
    base = ["baselines", "--method", "sgs_lft"]
    assert main([*base, "--set", "tiny", "--config", str(tmp_path / "none.toml")]) == 1
    assert "not found" in capsys.readouterr().err
    assert main([*base, "--set", "j99", "--config", str(fake_study)]) == 1
    assert "j99 not found" in capsys.readouterr().err
    with pytest.raises(SystemExit) as excinfo:
        main([*base, "--set", "tiny", "--config", str(fake_study), "--limit", "0"])
    assert excinfo.value.code == 2
    capsys.readouterr()
