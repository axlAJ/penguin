from penguin import searchterms
from penguin.loadfile import FIELD_SEP, QUOTE_CHAR, read_dat


def build(tmp_path, docs):
    (tmp_path / "TEXT").mkdir(exist_ok=True)
    columns = ["BegDoc", "TextLink"]
    rows = []
    for name, text in docs.items():
        (tmp_path / "TEXT" / f"{name}.txt").write_text(text, encoding="utf-8")
        rows.append([name, f"TEXT/{name}.txt"])
    body = [FIELD_SEP.join(f"{QUOTE_CHAR}{c}{QUOTE_CHAR}" for c in columns)]
    body += [FIELD_SEP.join(f"{QUOTE_CHAR}{c}{QUOTE_CHAR}" for c in row) for row in rows]
    path = tmp_path / "vol.dat"
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8")
    return read_dat(path)


def test_wildcard_expands(tmp_path):
    dat = build(tmp_path, {"A-1": "the auditor called", "A-2": "nothing here"})
    hits = {h.term: h for h in searchterms.run(dat, tmp_path, ["audit*"])}
    assert hits["audit*"].documents == 1


def test_term_matching_is_case_insensitive(tmp_path):
    dat = build(tmp_path, {"A-1": "Rebate accrual"})
    assert searchterms.run(dat, tmp_path, ["rebate"])[0].documents == 1


def test_word_boundary_prevents_substring_hits(tmp_path):
    dat = build(tmp_path, {"A-1": "in the trebate report"})
    assert searchterms.run(dat, tmp_path, ["rebate"])[0].documents == 0


def test_unique_hits_exclude_documents_other_terms_reach(tmp_path):
    dat = build(tmp_path, {"A-1": "rebate accrual", "A-2": "rebate only"})
    hits = {h.term: h for h in searchterms.run(dat, tmp_path, ["rebate", "accrual"])}
    assert hits["rebate"].documents == 2
    assert hits["rebate"].unique == 1
    assert hits["accrual"].unique == 0


def test_overbroad_term_is_noted(tmp_path):
    dat = build(tmp_path, {"A-1": "the thing", "A-2": "the other"})
    assert "too broad" in searchterms.run(dat, tmp_path, ["the"])[0].note


def test_zero_hit_term_is_noted(tmp_path):
    dat = build(tmp_path, {"A-1": "nothing relevant"})
    assert "No hits" in searchterms.run(dat, tmp_path, ["unicorn"])[0].note


def test_punctuation_in_term_is_escaped(tmp_path):
    dat = build(tmp_path, {"A-1": "profit & loss statement"})
    assert searchterms.run(dat, tmp_path, ["profit & loss"])[0].documents == 1
