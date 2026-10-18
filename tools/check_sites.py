"""参照サイトを読み、変更を見つけて「どのページを直すか」を自動で判定し、data/pending.json に記録する(標準ライブラリのみ)"""
import concurrent.futures, csv, hashlib, heapq, threading, json, os, re, time, difflib, datetime, pathlib, urllib.request, urllib.parse, urllib.robotparser
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"; PENDING = ROOT / "data" / "pending.json"
SNAP.mkdir(parents=True, exist_ok=True)
SKIP = {"admin", "data", "tools", ".github"}

class Text(HTMLParser):  # 参照サイトの文字とリンクを取り出す
    def __init__(s): super().__init__(); s.out = []; s.skip = 0; s.links = []; s.href = None; s.lt = ""
    def handle_starttag(s, t, a):
        if t in ("script", "style", "noscript"): s.skip += 1
        if t == "a": s.href = dict(a).get("href"); s.lt = ""
    def handle_endtag(s, t):
        if t in ("script", "style", "noscript") and s.skip: s.skip -= 1
        if t == "a" and s.href: s.links.append((s.href, s.lt)); s.href = None
        if t in ("p", "li", "tr", "div", "h1", "h2", "h3", "br"): s.out.append("\n")
    def handle_data(s, d):
        if not s.skip: s.out.append(d)
        if s.href is not None: s.lt += d

class Page(HTMLParser):  # 自分のサイトのページ索引用
    def __init__(s): super().__init__(); s.title = s.h1 = ""; s.doms = set(); s.sec = []; s.cur = None; s.id = None
    def handle_starttag(s, t, a):
        a = dict(a)
        if t in ("title", "h1", "h2", "h3", "h4"): s.cur = t
        if a.get("id"): s.id = a["id"]
        if t == "a" and a.get("href", "").startswith("http"): s.doms.add(urllib.parse.urlparse(a["href"]).netloc)
    def handle_endtag(s, t):
        if t == s.cur: s.cur = None
    def handle_data(s, d):
        d = d.strip()
        if not d or not s.cur: return
        if s.cur == "title": s.title += d
        elif s.cur == "h1": s.h1 += d
        elif s.id: s.sec.append((s.id, d)); s.id = None

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AsukaGuideChecker/1.0 (personal site maintenance)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")

def build_index():  # 自分のサイトの全ページ(と、1ページ内の各施設)の一覧
    idx = []
    for f in sorted(ROOT.rglob("*.html")):
        rel = f.relative_to(ROOT).as_posix()
        if rel.split("/")[0] in SKIP: continue
        p = Page(); p.feed(f.read_text("utf-8", errors="replace"))
        idx.append({"path": rel, "name": p.h1 or p.title.split("｜")[0], "doms": p.doms})
        idx += [{"path": f"{rel}#{i}", "name": n, "doms": p.doms} for i, n in p.sec]
    return idx

def rank(idx, url, text):  # AIなしの簡易判定:名前が出てくる/リンク先が同じサイト
    dom = urllib.parse.urlparse(url).netloc; out = []
    for e in idx:
        s = (20 if dom in e["doms"] else 0) + ((50 + len(e["name"])) if e["name"] and e["name"] in text else 0)
        if s: out.append((s, e))
    return sorted(out, key=lambda x: -x[0])[:5]

def ask_ai(url, diff, idx):  # 無料のGemini APIを使う(GEMINI_API_KEY が無ければ使わない)
    key = os.environ.get("GEMINI_API_KEY")
    if not key: return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    names = "\n".join(f"{e['path']}: {e['name']}" for e in idx[:400])
    prompt = ("あなたは明日香村観光ガイドの保守担当です。参照サイトの変更を見て、更新すべきページを一覧から選んでください。"
              "一覧にない新しい施設なら target を NEW、観光ガイドに関係ない変更(広告・デザイン等)なら NONE。"
              '次のJSONだけを返す: {"target":"","confidence":"高|中|低","reason":"短く","changes":[{"item":"営業時間など","old":"","new":""}]}\n'
              f"参照サイト: {url}\n変更(+追加 -削除):\n" + "\n".join(diff[:60]) + f"\n\nページ一覧:\n{names}")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}).encode()
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                                 body, {"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    time.sleep(5)
    return json.loads(r["candidates"][0]["content"]["parts"][0]["text"])

UA = "AsukaGuideChecker/1.0 (personal site maintenance)"
KEYS = ["営業", "開館", "開園", "料金", "入場", "入館", "拝観", "アクセス", "交通", "駐車", "イベント", "お知らせ", "新着", "ニュース",
        "休館", "休業", "臨時", "施設", "見どころ", "案内", "観光", "スポット", "利用", "営業時間", "料金", "info", "news", "access", "event"]
KEYS = list(dict.fromkeys(KEYS))
SKIPEXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4", ".doc", ".docx", ".xls", ".xlsx", ".webp", ".svg")

def parse(html):
    p = Text(); p.feed(html)
    return [l.strip() for l in "".join(p.out).splitlines() if l.strip()], p.links

def robots(start):
    rp = urllib.robotparser.RobotFileParser()
    try: rp.parse(fetch(urllib.parse.urljoin(start, "/robots.txt")).splitlines())
    except Exception: rp.parse([])
    return rp

def crawl(start, depth, maxp):  # 観光に関係しそうなリンクを、階層に関係なく優先して読む
    rp, host = robots(start), urllib.parse.urlparse(start).netloc.replace("www.", "")
    seen, heap, pages, dep, n = {start}, [(0, 0, start, 0)], {}, {}, 0
    while heap and len(pages) < maxp:
        _, _, u, d = heapq.heappop(heap)
        if not rp.can_fetch(UA, u): continue
        try: lines, links = parse(fetch(u))
        except Exception:
            if d == 0: raise
            continue
        pages[u] = lines; dep[u] = d; time.sleep(2)  # 公式サイトに負担をかけない
        if d >= depth: continue
        for href, text in links:
            v = urllib.parse.urldefrag(urllib.parse.urljoin(u, href))[0]
            q = urllib.parse.urlparse(v)
            if q.scheme in ("http", "https") and q.netloc.replace("www.", "") == host and v not in seen and not q.path.lower().endswith(SKIPEXT):
                seen.add(v); n += 1
                heapq.heappush(heap, (-(sum(k in text + v for k in KEYS) * 3 - d), n, v, d + 1))  # 言葉が近いほど先、深いほど少し後
    return pages, dep

AI_LOCK = threading.Lock()  # AIへの問い合わせは1件ずつ(無料枠の回数制限を守るため)

def judge(url, memo, diff, ai_left):  # 更新先のページを判定する
    res, note = None, ""
    with AI_LOCK:
        if ai_left[0] > 0:
            ai_left[0] -= 1
            try: res = ask_ai(url, diff, idx)
            except Exception as e: note = f"AI判定に失敗したため簡易判定です({e})"
        else: note = "AIの1回あたりの上限に達したため簡易判定です"
    if res: return res.get("target", "UNKNOWN"), res.get("confidence", "低"), res.get("reason", ""), res.get("changes", [])
    c = rank(idx, url, memo + " ".join(diff))
    t, conf = (c[0][1]["path"], "中" if c[0][0] >= 70 else "低") if c else ("UNKNOWN", "低")
    return t, conf, note or "サイト名やリンクが似ているページです(AI未使用)", []

idx = build_index()
pending = json.loads(PENDING.read_text("utf-8")) if PENDING.exists() else []
today = datetime.date.today().isoformat()
ai_left = [int(os.environ.get("MAX_AI_CALLS", "30"))]; ai_start = ai_left[0]
LOG = ROOT / "data" / "crawl-log.json"
runs = json.loads(LOG.read_text("utf-8")) if LOG.exists() else []
run = {"date": today, "sites": []}

def process(row):  # 1サイト分の処理
    start, memo = row["url"], row.get("memo") or ""
    host = re.sub(r"[^A-Za-z0-9.]+", "-", urllib.parse.urlparse(start).netloc)
    sd = SNAP / host; first = not sd.exists(); sd.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); md, mp = int(row.get("depth") or 3), int(row.get("max_pages") or 60); chg = newp = 0; out = []
    try: pages, dep = crawl(start, md, mp)
    except Exception as e:
        print(f"{start}: 読み込みエラー {e}")
        return {"url": start, "error": str(e)}, [{"id": f"{host}-{today}-error", "url": start, "date": today, "kind": "error", "diff": [f"読み込めませんでした: {e}"]}]
    hit = len(pages) >= mp
    base, cfg = sd / "_baseline.json", json.dumps({"depth": md, "max_pages": mp})
    # 新しいページの検出は、前回と同じ設定で、上限に達していないときだけ(読むページの顔ぶれが変わるだけの場合を避けるため)
    newok = (not hit) and base.exists() and base.read_text("utf-8") == cfg
    for u, new in pages.items():
        snap = sd / (hashlib.sha1(u.encode()).hexdigest()[:16] + ".txt")
        old = snap.read_text("utf-8").splitlines()[1:] if snap.exists() else None
        if not first and (old is not None or newok):
            diff = ["+" + l for l in new[:60]] if old is None else [l for l in difflib.unified_diff(old, new, lineterm="", n=0)
                    if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            if diff:
                chg += 1; newp += old is None
                t, conf, reason, ch = judge(u, memo, diff, ai_left)
                if t != "NONE":
                    out.append({"id": f"{host}-{snap.stem}-{today}", "url": u, "date": today, "kind": "change", "target": t,
                                "confidence": conf, "reason": reason, "changes": ch, "diff": diff[:60]})
        snap.write_text(u + "\n" + "\n".join(new), "utf-8")
    base.write_text(cfg, "utf-8")
    by = {str(k): sum(1 for v in dep.values() if v == k) for k in range(max(dep.values(), default=0) + 1)}
    info = {"url": start, "pages": len(pages), "max_pages": mp, "max_depth": md, "depth_reached": max(dep.values(), default=0),
            "pages_by_depth": by, "hit_page_limit": hit, "new_page_detection": newok, "changes": chg, "new_pages": newp, "seconds": round(time.time() - t0), "first_run": first}
    print(f"{start}: {len(pages)}ページ(上限{mp}) 深さ別{by} 変更{chg}件 新規{newp}件 {info['seconds']}秒" + (" ★ページ数の上限に達しました" if hit else "") + ("" if newok or first else " (新規ページの検出は今回は休止)"))
    return info, out

def safe(row):
    try: return process(row)
    except Exception as e:
        print(f"{row.get('url')}: 想定外のエラー {e}"); return {"url": row.get("url"), "error": str(e)}, []

with open(ROOT / "tools" / "sites.csv", encoding="utf-8") as f: rows = list(csv.DictReader(f))
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get("PARALLEL", "4"))) as ex:  # 別々のサイトを同時に読む
    for info, out in ex.map(safe, rows):
        run["sites"].append(info); pending += out
run["ai_calls"] = ai_start - ai_left[0]
LOG.write_text(json.dumps((runs + [run])[-30:], ensure_ascii=False, indent=1), "utf-8")
print(f"AI判定 {run['ai_calls']}回")
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=1), "utf-8")
