from services.dedup.hash import normalize_title, title_hash


def test_normalize_lowercases_and_strips_punctuation():
    assert normalize_title("Путин заявил: Россия справится!") == "путин заявил россия справится"


def test_normalize_collapses_whitespace():
    assert normalize_title("Текст   с      пробелами") == "текст с пробелами"


def test_identical_titles_produce_same_hash():
    a = title_hash("Путин заявил о поддержке участников СВО")
    b = title_hash("путин заявил о поддержке участников сво!")
    assert a == b


def test_different_titles_produce_different_hash():
    a = title_hash("Путин заявил о поддержке участников СВО")
    b = title_hash("Курс доллара вырос на 0.5%")
    assert a != b


def test_empty_title():
    assert normalize_title("") == ""
    assert normalize_title(None) == ""
