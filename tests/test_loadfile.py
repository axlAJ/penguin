import pytest

from penguin.loadfile import FIELD_SEP, QUOTE_CHAR, LoadFileError, read_dat, read_opt


def write_dat(tmp_path, rows):
    body = "\r\n".join(
        FIELD_SEP.join(f"{QUOTE_CHAR}{cell}{QUOTE_CHAR}" for cell in row) for row in rows
    )
    path = tmp_path / "vol.dat"
    path.write_text(body + "\r\n", encoding="utf-8")
    return path


def test_read_dat_parses_concordance_delimiters(tmp_path):
    path = write_dat(tmp_path, [["BegDoc", "Custodian"], ["A-0001", "Cho, W."]])
    dat = read_dat(path)
    assert dat.columns == ["BegDoc", "Custodian"]
    assert len(dat) == 1
    assert dat.records[0].get("Custodian") == "Cho, W."


def test_commas_inside_fields_survive(tmp_path):
    path = write_dat(tmp_path, [["BegDoc", "Author"], ["A-0001", "Duarte, M., Jr."]])
    assert read_dat(path).records[0].get("Author") == "Duarte, M., Jr."


def test_short_rows_are_padded_not_shifted(tmp_path):
    path = write_dat(tmp_path, [["BegDoc", "Custodian", "FileName"], ["A-0001", "Cho, W."]])
    record = read_dat(path).records[0]
    assert record.get("Custodian") == "Cho, W."
    assert record.get("FileName") == ""


def test_multi_value_field(tmp_path):
    path = write_dat(tmp_path, [["BegDoc", "Custodian"], ["A-0001", "Cho, W.; Duarte, M."]])
    assert read_dat(path).records[0].multi("Custodian") == ["Cho, W.", "Duarte, M."]


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.dat"
    path.write_text("", encoding="utf-8")
    with pytest.raises(LoadFileError):
        read_dat(path)


def test_read_opt_marks_document_breaks(tmp_path):
    path = tmp_path / "vol.opt"
    path.write_text(
        "A-0001,VOL001,IMAGES\\A-0001.tif,Y,,,2\r\n"
        "A-0002,VOL001,IMAGES\\A-0002.tif,,,,\r\n",
        encoding="utf-8",
    )
    opt = read_opt(path)
    assert len(opt) == 2
    assert opt.document_keys() == ["A-0001"]
    assert opt.pages[0].pages == 2


def test_short_opt_line_raises(tmp_path):
    path = tmp_path / "vol.opt"
    path.write_text("A-0001,VOL001\r\n", encoding="utf-8")
    with pytest.raises(LoadFileError):
        read_opt(path)
