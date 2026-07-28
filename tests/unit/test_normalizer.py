from services.ingestion.normalizer import normalize_text


def test_strips_html_tags():
    assert normalize_text("<b>Важная</b> новость") == "Важная новость"


def test_removes_subscribe_calls():
    result = normalize_text("Новость дня. Подписывайтесь на наш канал в Telegram!")
    assert "подпис" not in result.lower()


def test_removes_urls():
    result = normalize_text("Подробнее: https://example.com/page новость")
    assert "http" not in result


def test_collapses_whitespace():
    assert normalize_text("Текст   с      пробелами") == "Текст с пробелами"


def test_empty_input():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""
