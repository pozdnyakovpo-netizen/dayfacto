"""Проверка RSS-кандидатов: живой ли адрес, сколько материалов, о чём.

Часть лент неизбежно окажется мёртвой — адреса меняются. Скрипт отбирает
рабочие и складывает их в feeds_ok.txt, откуда их можно грузить в sources.
"""

import concurrent.futures as cf
import re
import urllib.request

CANDIDATES = [
    # --- Законы, право, госрегулирование ---
    ("Российская газета", "https://rg.ru/xml/index.xml"),
    ("РГ: экономика", "https://rg.ru/tema/ekonomika/rss.xml"),
    ("Право.ру", "https://pravo.ru/export/"),
    ("Гарант: новости", "https://www.garant.ru/rss/news/"),
    ("Консультант: правовые новости", "https://www.consultant.ru/rss/hotdocs.xml"),
    ("Госдума", "http://duma.gov.ru/news/rss/"),
    ("Правительство России", "http://government.ru/all/rss/"),
    ("Минфин", "https://minfin.gov.ru/ru/rss/"),
    ("ФНС", "https://www.nalog.gov.ru/rss/rn77/news/"),
    ("Роспотребнадзор", "https://www.rospotrebnadzor.ru/rss/news.xml"),

    # --- Деньги, налоги, банки, выплаты ---
    ("Банки.ру", "https://www.banki.ru/xml/news.rss"),
    ("Банк России", "https://www.cbr.ru/rss/RssNews"),
    ("Ведомости", "https://www.vedomosti.ru/rss/news"),
    ("Ведомости: экономика", "https://www.vedomosti.ru/rss/rubric/economics"),
    ("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    ("РБК: финансы", "https://rssexport.rbc.ru/rbcnews/finances/30/full.rss"),
    ("Коммерсантъ", "https://www.kommersant.ru/RSS/news.xml"),
    ("Коммерсантъ: экономика", "https://www.kommersant.ru/RSS/section-economics.xml"),
    ("Forbes Россия", "https://www.forbes.ru/newrss.xml"),
    ("Frank Media", "https://frankmedia.ru/feed"),
    ("Финам", "https://www.finam.ru/analysis/conews/rsspoint/"),
    ("Пенсионный фонд/СФР", "https://sfr.gov.ru/rss/"),

    # --- ЖКХ, недвижимость, тарифы ---
    ("РБК Недвижимость", "https://rssexport.rbc.ru/rbcnews/realty/30/full.rss"),
    ("ЕРЗ (строительство)", "https://erzrf.ru/rss"),
    ("Домклик журнал", "https://blog.domclick.ru/rss"),

    # --- Транспорт, авто, правила для водителей ---
    ("За рулём", "https://www.zr.ru/export/rss/zr/news/"),
    ("Autonews", "https://rssexport.rbc.ru/rbcnews/autonews/30/full.rss"),
    ("Drom новости", "https://news.drom.ru/rss/"),
    ("МВД России", "https://мвд.рф/news/rss"),

    # --- Здоровье, медицина, лекарства ---
    ("Минздрав", "https://minzdrav.gov.ru/rss/news"),
    ("Vademecum", "https://vademec.ru/rss/"),
    ("Медвестник", "https://medvestnik.ru/rss/news.xml"),

    # --- Технологии, связь, цифровые сервисы ---
    ("Хабр: новости", "https://habr.com/ru/rss/news/"),
    ("CNews", "https://www.cnews.ru/inc/rss/news.xml"),
    ("3DNews", "https://3dnews.ru/news/rss/"),
    ("iXBT", "https://www.ixbt.com/export/news.rss"),
    ("Роскомнадзор", "https://rkn.gov.ru/rss/"),
    ("VC.ru", "https://vc.ru/rss/all"),

    # --- Образование, соцсфера ---
    ("Минпросвещения", "https://edu.gov.ru/press/rss/"),
    ("Минобрнауки", "https://minobrnauki.gov.ru/press-center/rss/"),
    ("Мел", "https://mel.fm/rss"),

    # --- Труд, работа, бизнес ---
    ("Минтруд", "https://mintrud.gov.ru/rss"),
    ("Клерк.ру", "https://www.klerk.ru/yandex.rss"),
    ("Бухонлайн", "https://www.buhonline.ru/rss/news.xml"),

    # --- Погода, ЧС, безопасность ---
    ("МЧС России", "https://mchs.gov.ru/rss"),
    ("Гидрометцентр", "https://meteoinfo.ru/rss/forecasts"),

    # --- Общие ленты с широким охватом ---
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
    ("Лента.ру", "https://lenta.ru/rss/news"),
    ("Газета.ру", "https://www.gazeta.ru/export/rss/lenta.xml"),
    ("Известия", "https://iz.ru/xml/rss/all.xml"),
    ("Новые Известия", "https://newizv.ru/rss"),
]

UA = {"User-Agent": "Mozilla/5.0 (compatible; DayFactoBot/1.0)"}


def check(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read(200_000).decode("utf-8", "ignore")
        items = len(re.findall(r"<(item|entry)[\s>]", body))
        if items == 0:
            return name, url, 0, "нет материалов"
        return name, url, items, "ok"
    except Exception as exc:
        return name, url, 0, type(exc).__name__


def main():
    print(f"Проверяю {len(CANDIDATES)} лент...\n")
    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(check, CANDIDATES))

    ok = [r for r in results if r[3] == "ok"]
    bad = [r for r in results if r[3] != "ok"]

    print(f"{'мат.':>5}  название")
    print("-" * 60)
    for name, url, n, _ in sorted(ok, key=lambda x: -x[2]):
        print(f"{n:5}  {name}")

    if bad:
        print(f"\nНе ответили ({len(bad)}):")
        for name, _, _, err in bad:
            print(f"       {name} — {err}")

    with open("feeds_ok.txt", "w", encoding="utf-8") as f:
        for name, url, n, _ in ok:
            f.write(f"{name}\t{url}\n")

    print(f"\nРабочих: {len(ok)} из {len(CANDIDATES)}. Сохранено в feeds_ok.txt")


if __name__ == "__main__":
    main()
