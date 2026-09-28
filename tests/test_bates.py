from penguin import bates


def test_parse_splits_prefix_and_number():
    result = bates.parse("ACME-0000123")
    assert result is not None
    assert result.prefix == "ACME-"
    assert result.number == 123
    assert result.width == 7
    assert result.text == "ACME-0000123"


def test_parse_rejects_non_numeric_tail():
    assert bates.parse("ACME-000012A") is None
    assert bates.parse("") is None
    assert bates.parse("   ") is None


def test_find_gaps_reports_missing_span():
    values = [bates.parse(v) for v in ("A-0001", "A-0002", "A-0006")]
    gaps = bates.find_gaps([v for v in values if v])
    assert len(gaps) == 1
    assert gaps[0].missing == 3
    assert gaps[0].after == "A-0002"
    assert gaps[0].before == "A-0006"


def test_gaps_are_scoped_per_prefix():
    values = [bates.parse(v) for v in ("A-0001", "B-0900", "A-0002")]
    assert bates.find_gaps([v for v in values if v]) == []


def test_find_duplicates():
    values = [bates.parse(v) for v in ("A-0001", "A-0001", "A-0002")]
    assert bates.find_duplicates([v for v in values if v]) == {"A-0001": 2}


def test_expand_range():
    begin, end = bates.parse("A-0001"), bates.parse("A-0003")
    assert begin and end
    assert bates.expand_range(begin, end) == ["A-0001", "A-0002", "A-0003"]
