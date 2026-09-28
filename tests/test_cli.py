import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from penguin.cli import main
from sample.make_sample import build


def test_end_to_end_on_the_sample_volume(tmp_path, capsys):
    root = build(tmp_path / "VOL001")
    code = main(
        [
            "run",
            "--dat", str(root / "VOL001.dat"),
            "--opt", str(root / "VOL001.opt"),
            "--volume", str(root),
            "--terms", str(root / "terms.txt"),
            "--html", str(tmp_path / "report.html"),
            "--csv", str(tmp_path / "exceptions.csv"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 1  # the sample volume has seeded blocking defects
    assert "Records" in out
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "exceptions.csv").exists()


def test_fail_on_never_exits_zero(tmp_path):
    root = build(tmp_path / "VOL001")
    code = main(
        [
            "run",
            "--dat", str(root / "VOL001.dat"),
            "--volume", str(root),
            "--fail-on", "never",
        ]
    )
    assert code == 0


def test_unreadable_dat_exits_two(tmp_path):
    assert main(["run", "--dat", str(tmp_path / "nope.dat")]) == 2
