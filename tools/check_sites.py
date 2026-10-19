"""参照サイトを読み、変更を見つけて「どのページを直すか」を判定し data/pending.json に記録する(標準ライブラリのみ)
毎日: お知らせ・サイトマップの更新・紐づけ済みの公式ページだけ読む / 週1(日曜): サイト全体を読み、紐づけを更新する"""
import collections, concurrent.futures, csv, datetime, difflib, hashlib, heapq, json, os, pathlib, re, threading, time
import urllib.parse, urllib.request, urllib.robotparser
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"; PENDING = ROOT / "data" / "pending.json"
LINKS = ROOT / "data" / "links.json"; LOG = ROOT / "data" / "crawl-log.json"
SNAP.mkdir(parents=True, exist_ok=True)
SKIP = {"admin", "data", "tools", ".github"}
UA = "AsukaGuideChecker/1.0 (personal site maintenance)"
KEYS = list(dict.fromkeys(["営業", "開館", "開園", "料金", "入場", "入館", "拝観", "アクセス", "交通", "駐車", "イベント", "お知らせ", "新着", "ニュース",
        "休館", "休業", "臨時", "施設", "見どころ", "案内", "観光", "スポット", "利用", "info", "news", "access", "event"]))
NEWSKEYS = ["お知らせ", "新着", "更新", "ニュース", "トピックス", "news", "info", "topics"]
SKIPEXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4", ".doc", ".docx", ".xls", ".xlsx", ".webp", ".svg")
GENERIC = {"ホーム", "観光する", "食べる", "泊まる", "サイトマップ", "お問い合わせ", "駐車場", "トイレ", "古墳・遺跡", "神社・寺院", "お風呂", "お宿"}
DATE = re.compile(r"\d{4}[./年-]\s?\d{1,2}")
MODE = os.environ.get("MODE", "").strip()
if MODE not in ("daily", "weekly"):  # 日本時間の日曜は週1の全体チェック
    MODE = "weekly" if (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).weekday() == 6 else "daily"

class Text(HTMLParser):  # 参照サイトの文字・リンク・題名を取り出す
    def __init__(s): super().__init__(); s.out = []; s.skip = 0; s.links = []; s.href = None; s.lt = ""; s.title = ""; s.cur = None
    def handle_starttag(s, t, a):
        if t in ("script", "style", "noscript"): s.skip += 1
        if t in ("title", "h1"): s.cur = t
        if t == "a": s.href = dict(a).get("href"); s.lt = ""
    def handle_endtag(s, t):
        if t in ("script", "style", "noscript") and s.skip: s.skip -= 1
        if t == s.cur: s.cur = None
        if t == "a" and s.href: s.links.append((s.href, s.lt)); s.href = None
        if t in ("p", "li", "tr", "div", "h1", "h2", "h3", "br"): s.out.append("\n")
    def handle_data(s, d):
        if not s.skip: s.out.append(d)
        if s.href is not None: s.lt += d
        if s.cur and d.strip() and len(s.title) < 200: s.title += d.strip() + " "

class Page(HTMLParser):  # 自分のサイトのページ索引用
    def __init__(s): super().__init__(); s.title = s.h1 = ""; s.sec = []; s.cur = None; s.id = None
    def handle_starttag(s, t, a):
        a = dict(a)
        if t in ("title", "h1", "h2", "h3", "h4"): s.cur = t
        if a.get("id"): s.id = a["id"]
    def handle_endtag(s, t):
        if t == s.cur: s.cur = None
    def handle_data(s, d):
        d = d.strip()
        if not d or not s.cur: return
        if s.cur == "title": s.title += d
        elif s.cur == "h1": s.h1 += d
        elif s.id: s.sec.append((s.id, d)); s.id = None

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")

def parse(html):
    p = Text(); p.feed(html)
    return [l.strip() for l in "".join(p.out).splitlines() if l.strip()], p.links, p.title

def build_index():  # 自分のサイトの全ページ(と、1ページ内の各施設)の一覧
    idx = []
    for f in sorted(ROOT.rglob("*.html")):
        rel = f.relative_to(ROOT).as_posix()
        if rel.split("/")[0] in SKIP: continue
        p = Page(); p.feed(f.read_text("utf-8", errors="replace"))
        idx.append({"path": rel, "name": p.h1 or p.title.split("｜")[0]})
        idx += [{"path": f"{rel}#{i}", "name": n} for i, n in p.sec]
    return idx

def robots(start):
    rp = urllib.robotparser.RobotFileParser()
    try: rp.parse(fetch(urllib.parse.urljoin(start, "/robots.txt")).splitlines())
    except Exception: rp.parse([])
    return rp

def dom_of(u): return urllib.parse.urlparse(u).netloc.replace("www.", "")
def spath(sd, u): return sd / (hashlib.sha1(u.encode()).hexdigest()[:16] + ".txt")

def clean(u, href, dom):  # 同じサイトの、読んでよいリンクだけ返す
    v = urllib.parse.urldefrag(urllib.parse.urljoin(u, href))[0]; q = urllib.parse.urlparse(v)
    return v if q.scheme in ("http", "https") and dom_of(v) == dom and not q.path.lower().endswith(SKIPEXT) else None

def crawl(start, depth, maxp, dom):  # 週1: 関係の深いページを優先して全体を読む
    rp = robots(start); seen, heap, pages, dep, titles, n = {start}, [(0, 0, start, 0)], {}, {}, {}, 0
    while heap and len(pages) < maxp:
        _, _, u, d = heapq.heappop(heap)
        if not rp.can_fetch(UA, u): continue
        try: lines, links, title = parse(fetch(u))
        except Exception:
            if d == 0: raise
            continue
        pages[u], dep[u], titles[u] = lines, d, title; time.sleep(2)  # 公式サイトに負担をかけない
        if d >= depth: continue
        for href, text in links:
            v = clean(u, href, dom)
            if v and v not in seen:
                seen.add(v); n += 1; heapq.heappush(heap, (-(sum(k in text + v for k in KEYS) * 3 - d), n, v, d + 1))
    return pages, dep, titles

def sitemap_updated(start, rp, dom, since):  # サイトマップで、最近更新されたページ
    q = list(rp.site_maps() or []) or [urllib.parse.urljoin(start, "/sitemap.xml")]; out, n = [], 0
    while q and n < 10:
        sm = q.pop(0); n += 1
        try: txt = fetch(sm)
        except Exception: continue
        for blk in re.findall(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", txt, re.S):
            loc = re.search(r"<loc>\s*(.*?)\s*</loc>", blk, re.S); lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", blk, re.S)
            if not loc: continue
            u = loc.group(1)
            if u.endswith(".xml"): q.append(u)
            elif lm and lm.group(1)[:10] >= since and dom_of(u) == dom: out.append(u)
        time.sleep(1)
    return out[:50]

def daily(start, dom, mapped, sd, single=False):  # 毎日: トップ、お知らせ、サイトマップの更新、紐づけ済みのページだけ
    rp = robots(start); pages, dep, titles = {}, {}, {}
    since = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    todo = [(start, 0)] + [(u, 1) for u in mapped]
    try:
        if not single: todo += [(u, 1) for u in sitemap_updated(start, rp, dom, since)]
    except Exception: pass
    seen, news, newn = set(), set(), 0
    while todo and len(pages) < 150:
        u, d = todo.pop(0)
        if u in seen or not rp.can_fetch(UA, u): continue
        seen.add(u)
        try: lines, links, title = parse(fetch(u))
        except Exception:
            if u == start: raise
            continue
        pages[u], dep[u], titles[u] = lines, d, title; time.sleep(2)
        if not single and (u == start or u in news):  # お知らせ欄から、新しい日付つきのお知らせを探す
            for href, text in links:
                v = clean(u, href, dom)
                if not v or v in seen: continue
                if u == start and any(k in text.lower() for k in NEWSKEYS) and len(news) < 3 and not DATE.search(text): news.add(v); todo.append((v, 1))
                elif DATE.search(text + v) and not spath(sd, v).exists() and newn < 15: newn += 1; todo.append((v, 2))
    return pages, dep, titles

def rank(idx, text):  # AIなしの簡易判定:ガイドのページ名が出てくるか
    return sorted([(50 + len(e["name"]), e) for e in idx if e["name"] and e["name"] in text], key=lambda x: -x[0])[:5]

def ask_ai(url, diff, idx, hint):  # 無料のGemini API(GEMINI_API_KEY が無ければ使わない)
    key = os.environ.get("GEMINI_API_KEY")
    if not key: return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    names = "\n".join(f"{e['path']}: {e['name']}" for e in idx[:400])
    prompt = ("あなたは明日香村観光ガイドの保守担当です。参照サイトの変更を見て、更新すべきページを一覧から選んでください。"
              "一覧にない新しい施設なら target を NEW、観光ガイドに関係ない変更(広告・デザイン等)なら NONE。"
              '次のJSONだけを返す: {"target":"","confidence":"高|中|低","reason":"短く","changes":[{"item":"営業時間など","old":"","new":""}]}\n'
              f"参照サイト: {url}\n" + (f"このページは {hint} に対応済みです(特別な理由がなければ、これを選ぶ)。\n" if hint else "")
              + "変更(+追加 -削除):\n" + "\n".join(diff[:60]) + f"\n\nページ一覧:\n{names}")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}).encode()
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                                 body, {"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60)); time.sleep(5)
    return json.loads(r["candidates"][0]["content"]["parts"][0]["text"])

AI_LOCK = threading.Lock(); LINK_LOCK = threading.Lock()  # AIへの問い合わせは1件ずつ(無料枠の回数制限を守るため)

def judge(url, memo, diff, ai_left):  # 更新先のページを判定する
    res, note = None, ""; hint = (LINKS_DB.get(url) or {}).get("target")
    with AI_LOCK:
        if not os.environ.get("GEMINI_API_KEY"): note = "AIのキーが未設定のため簡易判定です"
        elif ai_left[0] > 0:
            ai_left[0] -= 1
            try: res = ask_ai(url, diff, idx, hint)
            except Exception as e: note = f"AI判定に失敗したため簡易判定です({e})"
        else: note = "AIの1回あたりの上限に達したため簡易判定です"
    if res: return res.get("target", "UNKNOWN"), res.get("confidence", "低"), res.get("reason", ""), res.get("changes", [])
    if hint: return hint, ("高" if LINKS_DB[url].get("manual") else "中"), note or "紐づけ済みのページです(AI未使用)", []
    c = rank(idx, memo + " ".join(diff))
    t, conf = (c[0][1]["path"], "低") if c else ("UNKNOWN", "低")
    return t, conf, note or "ガイドのページ名が出ているページです(AI未使用)", []

SEP = re.compile(r"\s*[｜|]\s*|\s+[-–—]\s+")

def match_links(titles, start, dom):  # 公式ページの題名の先頭が、ガイドのページ名とほぼ同じなら紐づける(週1)
    names = [(e["name"], e["path"]) for e in idx if len(e["name"]) >= 3 and e["name"] not in GENERIC and not e["path"].endswith("index.html")]
    total = len(titles)  # ほとんどのページの題名に出る名前は「サイト名」なので、トップページにだけ紐づける
    brand = {nm for nm, _ in names if total >= 10 and sum(nm in t for t in titles.values()) / total >= 0.3}
    found = {}
    for u, t in titles.items():
        if u in LINKS_DB or u in IGN: continue
        lead = SEP.split(t.strip())[0]
        c = [(len(nm) / max(len(lead), 1), p) for nm, p in names if nm in lead and (nm not in brand or u == start)]
        c = [x for x in c if x[0] >= 0.5]
        if c: sc, pth = max(c); found.setdefault(pth, []).append((sc, u, t))
    n = 0
    with LINK_LOCK:
        for pth, lst in found.items():
            for sc, u, t in sorted(lst, reverse=True)[:5]:  # 1つのガイドのページに、自動で紐づけるのは最大5件
                AUTO[u] = LINKS_DB[u] = {"target": pth, "title": t.strip()[:80]}; n += 1
    return n

idx = build_index()
pending = json.loads(PENDING.read_text("utf-8")) if PENDING.exists() else []
AUTO = {u: v for u, v in (json.loads(LINKS.read_text("utf-8")) if LINKS.exists() else {}).items() if not v.get("manual")}  # 自動の紐づけ
MANUAL = {}  # 手動の紐づけ(tools/links-manual.csv)。1つのガイドのページに、公式ページを何件でも結びつけられる
mf = ROOT / "tools" / "links-manual.csv"
if mf.exists():
    with open(mf, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            g, u = (r.get("guide_page") or "").strip(), (r.get("official_url") or "").strip()
            if not g or g.startswith("#") or not u: continue
            if g not in {e["path"] for e in idx}: print(f"紐づけ先のページが見つかりません(無視します): {g}"); continue
            MANUAL[u] = {"target": g, "title": (r.get("memo") or "").strip() or u, "manual": True}
if MODE == "weekly": AUTO.clear()  # 週1は、自動の紐づけを作り直す
LINKS_DB = {**AUTO, **MANUAL}
ign = ROOT / "tools" / "links-ignore.txt"
HIST_F = ROOT / "data" / "changes-history.json"
HIST = json.loads(HIST_F.read_text("utf-8")) if HIST_F.exists() else {}
nz = ROOT / "tools" / "ignore-text.txt"
NOISE = [l.strip() for l in nz.read_text("utf-8").splitlines() if l.strip() and not l.startswith("#")] if nz.exists() else []
IGN = {l.strip() for l in ign.read_text("utf-8").splitlines() if l.strip() and not l.startswith("#")} if ign.exists() else set()
today = datetime.date.today().isoformat()
ai_left = [int(os.environ.get("MAX_AI_CALLS", "30"))]; ai_start = ai_left[0]
runs = json.loads(LOG.read_text("utf-8")) if LOG.exists() else []
run = {"date": today, "mode": MODE, "sites": []}

def process(row):  # 1サイト分の処理
    start, memo = row["url"], row.get("memo") or ""; dom = dom_of(start)
    host = re.sub(r"[^A-Za-z0-9.]+", "-", urllib.parse.urlparse(start).netloc)
    sd = SNAP / host; first = not sd.exists(); sd.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); md, mp = int(row.get("depth") or 3), int(row.get("max_pages") or 60); chg = newp = 0; out = []
    try:
        if MODE == "weekly": pages, dep, titles = crawl(start, md, mp, dom)
        else: pages, dep, titles = daily(start, dom, [u for u in list(LINKS_DB) if dom_of(u) == dom and u not in IGN], sd, row.get("single"))
    except Exception as e:
        print(f"{start}: 読み込みエラー {e}")
        return {"url": start, "error": str(e)}, [{"id": f"{host}-{today}-error", "url": start, "date": today, "kind": "error", "diff": [f"読み込めませんでした: {e}"]}]
    hit = MODE == "weekly" and len(pages) >= mp and not row.get("single")
    base, cfg = sd / "_baseline.json", json.dumps({"depth": md, "max_pages": mp})
    # 新しいページの検出は、週1では「前回と同じ設定で上限に達していない」とき、毎日では「全体の記録がある」ときだけ
    newok = base.exists() and (MODE == "daily" or (not hit and base.read_text("utf-8") == cfg))
    cand = []
    for u, new in pages.items():
        snap = spath(sd, u); old = snap.read_text("utf-8").splitlines()[1:] if snap.exists() else None
        if not first and (old is not None or (newok and u not in LINKS_DB)):  # 紐づけ済みで初めて読むページは、記録だけ
            diff = ["+" + l for l in new[:60]] if old is None else [l for l in difflib.unified_diff(old, new, lineterm="", n=0)
                    if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            diff = [l for l in diff if not any(w in l for w in NOISE)]  # 手動の無視ワード
            if diff: cand.append((u, snap, diff, old is None))
        snap.write_text(u + "\n" + "\n".join(new), "utf-8")
    cnt = collections.Counter()
    for _, _, d, _ in cand: cnt.update({l[1:] for l in d})
    common = {t for t, c in cnt.items() if c >= 3}  # 3ページ以上に同じ行が出る変更は、サイト共通の部分(自動で入れ替わる欄など)
    cutoff = (datetime.date.today() - datetime.timedelta(days=14)).isoformat(); hist = HIST.setdefault(host, {}); res = []
    for u, snap, d, isnew in cand:
        recent = [x for x in hist.get(snap.stem, []) if x >= cutoff]; hist[snap.stem] = recent + [today]
        d2 = [l for l in d if l[1:] not in common]
        if len(recent) >= 3 and not isnew: d2 = [l for l in d2 if any(k in l for k in KEYS)]  # 頻繁に変わるページは、重要そうな言葉を含む行だけ
        if d2: res.append((u, snap, d2, isnew))
    filt = len(cand) - len(res); chg = len(res); newp = sum(r[3] for r in res)
    guard = len(res) > max(25, len(pages) // 10)  # 一度に大量のページが変わったら、サイト全体の変更とみなして1件にまとめる
    ck = [t for t in common if any(k in t for k in KEYS)]
    if ck: out.append({"id": f"{host}-common-{today}", "url": start, "date": today, "kind": "change", "target": "UNKNOWN", "confidence": "低",
                       "reason": "サイト共通の部分で、重要そうな言葉を含む変更です(複数のページに出ています)", "changes": [], "diff": ["+" + t for t in ck[:20]]})
    if guard:
        out.append({"id": f"{host}-mass-{today}", "url": start, "date": today, "kind": "change", "target": "UNKNOWN", "confidence": "低",
                    "reason": f"{len(res)}ページが一斉に変わりました。模様替えや、自動で入れ替わる欄の可能性があるので、1件にまとめました。", "changes": [],
                    "diff": ["+" + r[0] for r in res[:30]]})
    else:
        for u, snap, d2, isnew in res:
            t, conf, reason, ch = judge(u, memo, d2, ai_left)
            if t != "NONE":
                out.append({"id": f"{host}-{snap.stem}-{today}", "url": u, "date": today, "kind": "change", "target": t,
                            "confidence": conf, "reason": reason, "changes": ch, "diff": d2[:60]})
    nl = 0
    if MODE == "weekly": base.write_text(cfg, "utf-8"); nl = match_links(titles, start, dom)
    info = {"url": start, "pages": len(pages), "max_pages": mp, "max_depth": md, "depth_reached": max(dep.values(), default=0), "hit_page_limit": hit,
            "new_page_detection": newok, "filtered": filt, "common_lines": len(common), "mass_guard": guard, "changes": chg, "new_pages": newp, "new_links": nl, "seconds": round(time.time() - t0), "first_run": first}
    print(f"[{MODE}] {start}: {len(pages)}ページ 変更{chg}件 新規{newp}件 新しい紐づけ{nl}件 {info['seconds']}秒" + (" ★上限に達しました" if hit else ""))
    return info, out

def safe(row):
    try: return process(row)
    except Exception as e:
        print(f"{row.get('url')}: 想定外のエラー {e}"); return {"url": row.get("url"), "error": str(e)}, []

with open(ROOT / "tools" / "sites.csv", encoding="utf-8") as f: rows = list(csv.DictReader(f))
covered = {dom_of(r["url"]) for r in rows}; extra = {}
for u in MANUAL:  # sites.csv にないサイトの手動登録ページも、毎日読む
    if dom_of(u) not in covered: extra.setdefault(dom_of(u), u)
rows += [{"url": u, "memo": "手動登録", "depth": "0", "max_pages": "1", "single": True} for u in extra.values()]
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get("PARALLEL", "4"))) as ex:  # 別々のサイトを同時に読む
    for info, out in ex.map(safe, rows):
        run["sites"].append(info); pending += out
run["ai_calls"] = ai_start - ai_left[0]
LOG.write_text(json.dumps((runs + [run])[-30:], ensure_ascii=False, indent=1), "utf-8")
LINKS.write_text(json.dumps({**AUTO, **MANUAL}, ensure_ascii=False, indent=1), "utf-8")
print(f"AI判定 {run['ai_calls']}回")
HIST_F.write_text(json.dumps(HIST, ensure_ascii=False), "utf-8")
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=1), "utf-8")
