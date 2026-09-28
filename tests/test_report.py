from pathlib import Path

from penguin.checks import BLOCKER, WARNING, Finding, ProductionSummary
from penguin.report import write_csv, write_html


def sample_findings():
    return [
        Finding("native-missing", BLOCKER, "A-0001", "NativeLink points at a file that is not in the volume."),
        Finding("bates-gap", WARNING, "A-0002", "3 number(s) missing before A-0006."),
    ]


def test_html_report_carries_interactive_log(tmp_path):
    path = write_html(sample_findings(), ProductionSummary(records=2), [], tmp_path / "r.html")
    html = path.read_text(encoding="utf-8")
    assert "id='log'" in html
    assert "data-sev='blocker'" in html and "data-sev='warning'" in html
    assert "id='rule-filter'" in html and "id='log-search'" in html
    assert "id='dl-csv'" in html
    assert "<script>" in html and "Download CSV" in html


def test_html_escapes_detail_text(tmp_path):
    findings = [Finding("date-format", WARNING, "A-0001", "DocDate '<b>x</b>' did not parse.")]
    html = write_html(findings, ProductionSummary(records=1), [], tmp_path / "r.html").read_text()
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_verdict_states(tmp_path):
    clean = write_html([], ProductionSummary(), [], tmp_path / "c.html").read_text()
    assert "verdict clear" in clean
    warn = write_html([sample_findings()[1]], ProductionSummary(), [], tmp_path / "w.html").read_text()
    assert "verdict review" in warn
    hold = write_html(sample_findings(), ProductionSummary(), [], tmp_path / "h.html").read_text()
    assert "verdict hold" in hold


def test_csv_export(tmp_path):
    path = write_csv(sample_findings(), tmp_path / "e.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "severity,rule,record,detail"
    assert len(lines) == 3
