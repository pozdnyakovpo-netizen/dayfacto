from services.clustering.story_builder import (
    extract_entity_stems,
    is_same_event,
    significant_words,
    titles_are_similar,
)


def test_real_match_elbrus_story():
    a = "На Эльбрусе пропала группа альпинистов из Боснии"
    b = "На Эльбрусе нашли тела погибших альпинистов из Боснии"
    assert is_same_event(a, b) is True


def test_false_positive_donetsk_region_vs_city_prevented():
    # Реальный ложный сценарий из предыдущего проекта: общий стем
    # "донецк" не должен сам по себе связывать разные темы.
    a = "В Донецке отремонтировали мост после обстрела"
    b = "Донецкая область получила новые квоты на экспорт зерна"
    assert is_same_event(a, b) is False


def test_false_positive_center_word_prevented():
    # Реальный ложный сценарий: "Центр" (название группировки войск)
    # не должен цеплять новости про какой угодно другой "центр".
    a = "Кадры боевого слаживания штурмовиков группировки войск «Центр»"
    b = "В центре Москвы открылся новый торговый центр"
    assert is_same_event(a, b) is False


def test_unrelated_news_not_matched():
    a = "Курс доллара вырос на 0.5%"
    b = "Спасатели ищут тело школьницы в карьере на Урале"
    assert is_same_event(a, b) is False


def test_titles_are_similar_threshold():
    # wa целиком содержится в wb -> ratio = 1.0 при любом пороге,
    # это ожидаемое поведение формулы (intersection / smaller-set-size).
    wa = {"путин", "заявил", "поддержк"}
    wb = {"путин", "заявил", "поддержк", "участник", "сво"}
    assert titles_are_similar(wa, wb, threshold=0.5) is True
    assert titles_are_similar(wa, wb, threshold=1.0) is True
    # Частичное пересечение — порог должен реально отсеивать.
    wc = {"путин", "экономика", "нефть", "газ"}
    assert titles_are_similar(wa, wc, threshold=0.5) is False


def test_extract_entity_stems_excludes_common_words():
    stems = extract_entity_stems("Группировка войск «Центр» ведёт бои")
    assert "центр" not in stems


def test_significant_words_filters_stopwords_and_short_words():
    words = significant_words("Это новый закон о поддержке участников")
    assert "это" not in words
    assert "новый" not in words
    assert "поддер" in words
