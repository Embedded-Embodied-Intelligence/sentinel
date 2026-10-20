"""`sentinel inspect` command."""

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
