"""Повторная проверка с браузерными заголовками и точными кодами ошибок."""

import concurrent.futures as cf
import re
import urllib.error
import urllib.request

RETRY = [
    ("РГ: экономика", "https://rg.ru/tema/ekonomika/rss.xml"),
    ("Право.ру", "https://pravo.ru/rss/"),
    ("Госдума", "http://duma.gov.ru/news/rss/"),
    ("Минфин", "https://minfin.gov.ru/ru/rss/"),
    ("ФНС", "https://www.nalog.gov.ru/rss/rn77/news/"),
    ("Роспотребнадзор", "https://www.rospotrebnadzor.ru/rss/news.xml"),
    ("Банки.ру", "https://www.banki.ru/xml/news.rss"),
    ("РБК: финансы", "https://rssexport.rbc.ru/rbcnews/finances/30/full.rss"),
    ("Forbes Россия", "https://www.forbes.ru/newrss.xml"),
    ("СФР", "https://sfr.gov.ru/rss/"),
    ("РБК Недвижимость", "https://rssexport.rbc.ru/rbcnews/realty/30/full.rss"),
    ("За рулём", "https://www.zr.ru/export/rss/zr/news/"),
    ("Autonews", "https://rssexport.rbc.ru/rbcnews/autonews/30/full.rss"),
    ("Drom новости", "https://news.drom.ru/rss/"),
    ("МВД России", "https://xn--b1aew.xn--p1ai/news/rss"),
    ("Минздрав", "https://minzdrav.gov.ru/rss/news"),
    ("Роскомнадзор", "https://rkn.gov.ru/rss/"),
    ("Минпросвещения", "https://edu.gov.ru/press/rss/"),
    ("Мел", "https://mel.fm/rss.xml"),
    ("Клерк.ру", "https://www.klerk.ru/yandex.rss"),
    ("Бухонлайн", "https://www.buhonline.ru/rss/news.xml"),
    ("МЧС России", "https://mchs.gov.ru/rss"),
    ("Газета.ру", "https://www.gazeta.ru/export/rss/lenta.xml"),
    ("Известия", "https://iz.ru/xml/rss/all.xml"),
    ("Новые Известия", "https://newizv.ru/rss.xml"),
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def check(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(200_000).decode("utf-8", "ignore")
        n = len(re.findall(r"<(item|entry)[\s>]", body))
        return name, url, n, ("ok" if n else "пустая лента")
    except urllib.error.HTTPError as e:
        codes = {403: "403 блокирует ботов", 404: "404 адрес не существует",
                 451: "451 недоступно по праву", 503: "503 сервис недоступен"}
        return name, url, 0, codes.get(e.code, f"HTTP {e.code}")
    except urllib.error.URLError as e:
        return name, url, 0, f"нет связи ({e.reason})"
    except Exception as e:
        return name, url, 0, type(e).__name__


def main():
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        res = list(pool.map(check, RETRY))

    ok = [r for r in res if r[3] == "ok"]
    bad = [r for r in res if r[3] != "ok"]

    print("ЗАРАБОТАЛИ:")
    for name, url, n, _ in sorted(ok, key=lambda x: -x[2]):
        print(f"{n:5}  {name}")

    print("\nВСЁ ЕЩЁ НЕТ:")
    for name, _, _, err in bad:
        print(f"       {name} — {err}")

    if ok:
        with open("feeds_ok.txt", "a", encoding="utf-8") as f:
            for name, url, n, _ in ok:
                f.write(f"{name}\t{url}\n")
        print(f"\nДобавлено в feeds_ok.txt: {len(ok)}")


if __name__ == "__main__":
    main()
