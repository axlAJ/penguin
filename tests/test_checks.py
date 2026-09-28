from pathlib import Path

from penguin import checks
from penguin.loadfile import FIELD_SEP, QUOTE_CHAR, read_dat, read_opt


def make_dat(tmp_path, rows, columns):
    body = [FIELD_SEP.join(f"{QUOTE_CHAR}{c}{QUOTE_CHAR}" for c in columns)]
    body += [FIELD_SEP.join(f"{QUOTE_CHAR}{c}{QUOTE_CHAR}" for c in row) for row in rows]
    path = tmp_path / "vol.dat"
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8")
    return read_dat(path)


def rules(findings):
    return {f.rule for f in findings}


def test_missing_required_column_is_a_blocker(tmp_path):
    dat = make_dat(tmp_path, [["A-0001"]], ["BegDoc"])
    findings = checks.check_required_fields(dat)
    assert "required-field" in rules(findings)
    assert all(f.is_blocker for f in findings)


def test_duplicate_bates_is_a_blocker(tmp_path):
    dat = make_dat(
        tmp_path,
        [["A-0001", "A-0001"], ["A-0001", "A-0001"]],
        ["BegDoc", "EndDoc"],
    )
    findings, _ = checks.check_bates(dat)
    assert "bates-duplicate" in rules(findings)


def test_end_before_beg_is_a_blocker(tmp_path):
    dat = make_dat(tmp_path, [["A-0010", "A-0002"]], ["BegDoc", "EndDoc"])
    findings, _ = checks.check_bates(dat)
    assert "bates-range" in rules(findings)


def test_gap_is_a_warning_not_a_blocker(tmp_path):
    dat = make_dat(tmp_path, [["A-0001", "A-0001"], ["A-0005", "A-0005"]], ["BegDoc", "EndDoc"])
    findings, _ = checks.check_bates(dat)
    gap = [f for f in findings if f.rule == "bates-gap"]
    assert gap and gap[0].severity == checks.WARNING


def test_attachment_without_parent_is_an_orphan(tmp_path):
    dat = make_dat(tmp_path, [["A-0002", "A-0900"]], ["BegDoc", "BegAttach"])
    assert "family-orphan" in rules(checks.check_families(dat))


def test_attachment_with_parent_present_is_clean(tmp_path):
    dat = make_dat(
        tmp_path,
        [["A-0001", ""], ["A-0002", "A-0001"]],
        ["BegDoc", "BegAttach"],
    )
    assert checks.check_families(dat) == []


def test_missing_native_is_reported(tmp_path):
    dat = make_dat(tmp_path, [["A-0001", "NATIVES/A-0001.msg"]], ["BegDoc", "NativeLink"])
    findings, counts = checks.check_linked_files(dat, tmp_path)
    assert "native-missing" in rules(findings)
    assert counts["natives_expected"] == 1
    assert counts["natives_found"] == 0


def test_present_native_counts_as_found(tmp_path):
    (tmp_path / "NATIVES").mkdir()
    (tmp_path / "NATIVES" / "A-0001.msg").write_text("hello", encoding="utf-8")
    dat = make_dat(tmp_path, [["A-0001", "NATIVES/A-0001.msg"]], ["BegDoc", "NativeLink"])
    findings, counts = checks.check_linked_files(dat, tmp_path)
    assert findings == []
    assert counts["natives_found"] == 1


def test_empty_text_file_is_a_warning(tmp_path):
    (tmp_path / "TEXT").mkdir()
    (tmp_path / "TEXT" / "A-0001.txt").write_text("", encoding="utf-8")
    dat = make_dat(tmp_path, [["A-0001", "TEXT/A-0001.txt"]], ["BegDoc", "TextLink"])
    findings, _ = checks.check_linked_files(dat, tmp_path)
    assert "text-empty" in rules(findings)


def test_page_count_mismatch_against_opt(tmp_path):
    opt_path = tmp_path / "vol.opt"
    opt_path.write_text(
        "A-0001,VOL001,IMAGES\\A-0001.tif,Y,,,1\r\n", encoding="utf-8"
    )
    dat = make_dat(tmp_path, [["A-0001", "3"]], ["BegDoc", "PageCount"])
    findings = checks.check_images(dat, read_opt(opt_path))
    assert "page-count" in rules(findings)


def test_image_key_absent_from_dat_is_an_orphan(tmp_path):
    opt_path = tmp_path / "vol.opt"
    opt_path.write_text("A-9999,VOL001,IMAGES\\A-9999.tif,Y,,,1\r\n", encoding="utf-8")
    dat = make_dat(tmp_path, [["A-0001", "1"]], ["BegDoc", "PageCount"])
    assert "image-orphan" in rules(checks.check_images(dat, read_opt(opt_path)))


def test_unparseable_date_is_flagged(tmp_path):
    dat = make_dat(tmp_path, [["A-0001", "Sept 4th 2024"]], ["BegDoc", "DocDate"])
    assert "date-format" in rules(checks.check_field_hygiene(dat))


def test_iso_and_us_dates_both_parse(tmp_path):
    dat = make_dat(
        tmp_path, [["A-0001", "2024-09-04"], ["A-0002", "09/04/2024"]], ["BegDoc", "DocDate"]
    )
    assert checks.check_field_hygiene(dat) == []


def test_designated_document_needs_an_endorsement(tmp_path):
    dat = make_dat(
        tmp_path, [["A-0001", "CONFIDENTIAL", ""]], ["BegDoc", "Confidentiality", "Endorsement"]
    )
    assert "endorsement-missing" in rules(checks.check_confidentiality(dat))


def test_multipage_documents_do_not_read_as_gaps(tmp_path):
    dat = make_dat(
        tmp_path,
        [["A-0001", "A-0003"], ["A-0004", "A-0005"], ["A-0006", "A-0006"]],
        ["BegDoc", "EndDoc"],
    )
    findings, _ = checks.check_bates(dat)
    assert "bates-gap" not in rules(findings)


def test_real_gap_between_documents_is_still_found(tmp_path):
    dat = make_dat(
        tmp_path, [["A-0001", "A-0003"], ["A-0008", "A-0008"]], ["BegDoc", "EndDoc"]
    )
    findings, _ = checks.check_bates(dat)
    gap = [f for f in findings if f.rule == "bates-gap"]
    assert len(gap) == 1 and "4 number(s)" in gap[0].detail
