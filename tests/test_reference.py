"""Parsing of PSPLIB solution files; samples reproduce the layouts of the real files."""

from pathlib import Path

import pytest

from sentinel.data.reference import load_reference, parse_reference, reference_path

OPT_SAMPLE = """\
Authors' Name           : E. Demeulemeester / W. Herroelen
Instance Set            : j30
Clockpulse       : 25 MHz
Average CPU-Time : 28.97

==================================================================
Paramter Instance Makespan CPU-Time[sec.]
------------------------------------------------------------------
1       1         43       0.30
1       10        45       0.04
48      10        54       0.01
"""

HRS_SAMPLE = """\
solutionlist data/j60hrs.sm
===============================================================================
Par  Inst  Makespan  Date                     Author
===============================================================================
  1     1       77 Tue Apr 2 16:26:00 1996 R. Kolisch / A. Drexl
  1     8       75 Wed Aug 14 12:07:44 1996 Haase / Kohlmorgen / Schmeck
"""

# The escaped newline after "77   " keeps that line's trailing blanks, as in the real file.
LB_SAMPLE = """\
The lower bounds were calculated with the methods given in:

Brucker, P. and Knust, S. (1998): A Linear Programming and Constraint Propagation-Based ...
Instances where LB = UB holds are marked with an "*".
============================================================================
Par  Inst    LB         Author LB
============================================================================
  1    1    77   \n  1    4    91   Klein & Scholl Brucker & Knust
 41   10   111*  Philippe Laborie
"""


def test_parse_opt_layout() -> None:
    assert parse_reference(OPT_SAMPLE, "j30") == {
        "j30/j301_1": 43,
        "j30/j301_10": 45,
        "j30/j3048_10": 54,
    }


def test_parse_hrs_layout_ignores_numbers_in_date_and_author() -> None:
    assert parse_reference(HRS_SAMPLE, "j60") == {"j60/j601_1": 77, "j60/j601_8": 75}


def test_parse_lb_layout_with_trailing_blanks_and_star_marker() -> None:
    assert parse_reference(LB_SAMPLE, "j60") == {
        "j60/j601_1": 77,
        "j60/j601_4": 91,
        "j60/j6041_10": 111,
    }


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("header\n1 1 4x\n", "malformed data line"),
        ("1 1\n", "malformed data line"),
        ("1 1 40\n1 1 41\n", "duplicate entry for j30/j301_1"),
        ("only a header\n", "no data lines"),
    ],
)
def test_parse_rejects_bad_content(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_reference(text, "j30")


def test_load_reference_from_root(tmp_path: Path) -> None:
    path = reference_path("j30", "opt", tmp_path)
    assert path == tmp_path / "solutions" / "j30_opt.sm"
    path.parent.mkdir()
    path.write_text(OPT_SAMPLE)
    assert load_reference("j30", "opt", tmp_path)["j30/j301_1"] == 43


def test_load_reference_errors_name_the_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"fetch_psplib\.py"):
        load_reference("j30", "opt", tmp_path)
    path = reference_path("j30", "hrs", tmp_path)
    path.parent.mkdir()
    path.write_text("nothing here\n")
    with pytest.raises(ValueError, match=r"j30_hrs\.sm: no data lines"):
        load_reference("j30", "hrs", tmp_path)
