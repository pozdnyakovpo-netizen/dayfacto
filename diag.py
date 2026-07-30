"""Диагностика пайплайна: источники, кластеризация, отбор."""
import os, sys, re
from collections import Counter
from sqlalchemy import create_engine, text
sys.path.insert(0, "/app")
from ranking.prefilter import prefilter

db = create_engine(os.environ["DATABASE_URL"])
P = print

def q(sql, **kw):
    with db.connect() as c:
        return list(c.execute(text(sql), kw))

P("\n" + "="*62 + "\n1. ИСТОЧНИКИ\n" + "="*62)
rows = q("""SELECT s.name, s.weight, count(r.id) n,
            max(r.fetched_at) last FROM sources s
            LEFT JOIN raw_items r ON r.source_id=s.id
            WHERE s.active GROUP BY s.name,s.weight ORDER BY n DESC""")
dead = [r[0] for r in rows if r[2] == 0]
P(f"{'вес':>4} {'мат.':>6}  источник")
for name, w, n, last in rows:
    P(f"{w:4.1f} {n:6}  {name}")
if dead:
    P(f"\nМОЛЧАТ: {', '.join(dead)}")

P("\n" + "="*62 + "\n2. КЛАСТЕРИЗАЦИЯ\n" + "="*62)
st = q("SELECT count(*) FROM stories")[0][0]
ri = q("SELECT count(*) FROM raw_items")[0][0]
multi = q("""SELECT s.canonical_title, count(*) n FROM stories s
             JOIN story_items si ON si.story_id=s.id
             GROUP BY s.id,s.canonical_title HAVING count(*)>1
             ORDER BY n DESC LIMIT 8""")
P(f"материалов {ri}, сюжетов {st}, сжатие {ri/max(st,1):.1f}x")
P("\nКрупнейшие сюжеты (проверьте, что внутри одно событие):")
for t, n in multi:
    P(f"  {n:3}  {t[:60]}")

P("\n  Состав самого крупного:")
if multi:
    for (b,) in q("""SELECT r.title FROM raw_items r JOIN story_items si
                     ON si.raw_item_id=r.id JOIN stories s ON s.id=si.story_id
                     WHERE s.canonical_title=:t LIMIT 8""", t=multi[0][0]):
        P(f"    - {b[:66]}")

P("\n" + "="*62 + "\n3. ОТБОР (prefilter на всех сюжетах)\n" + "="*62)
titles = [r[0] for r in q("SELECT canonical_title FROM stories WHERE canonical_title IS NOT NULL")]
reasons = Counter()
passed = []
for t in titles:
    ok, why = prefilter(t)
    if ok:
        passed.append(t)
    else:
        reasons[why] += 1
P(f"всего {len(titles)}, прошло {len(passed)} ({100*len(passed)//max(len(titles),1)}%)")
for why, n in reasons.most_common():
    P(f"  отсеяно {n:4}  {why}")

P("\nПрошли фильтр, но выглядят как речевые (проверьте):")
SPEECH = re.compile(r"(пообеща|анонсирова|предупреди|пригрози|потребова|"
                    r"выступил|поручил|поддержал|раскритикова|усомни)", re.I)
sus = [t for t in passed if SPEECH.search(t)][:10]
for t in sus:
    P(f"  ! {t[:66]}")
if not sus:
    P("  таких нет")

P("\n" + "="*62 + "\n4. ДУБЛИ СРЕДИ ПРОШЕДШИХ\n" + "="*62)
sys.path.insert(0, "/app")
from ranking.text_utils import tokenize, jaccard
pairs = []
toks = [(t, tokenize(t)) for t in passed[:150]]
for i in range(len(toks)):
    for j in range(i+1, len(toks)):
        s = jaccard(toks[i][1], toks[j][1])
        if s > 0.5:
            pairs.append((s, toks[i][0], toks[j][0]))
pairs.sort(reverse=True)
P(f"похожих пар: {len(pairs)}")
for s, a, b in pairs[:5]:
    P(f"  {s:.2f}  {a[:48]}\n        {b[:48]}")

P("\n" + "="*62 + "\nГОТОВО\n" + "="*62)
