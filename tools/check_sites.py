"""参照サイトを読み、変更を見つけて「どのページを直すか」を自動で判定し、data/pending.json に記録する(標準ライブラリのみ)"""
import csv, json, os, re, time, difflib, datetime, pathlib, urllib.request, urllib.parse
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"; PENDING = ROOT / "data" / "pending.json"
SNAP.mkdir(parents=True, exist_ok=True)
SKIP = {"admin", "data", "tools", ".github"}

class Text(HTMLParser):  # 参照サイトの文字だけを取り出す
    def __init__(s): super().__init__(); s.out = []; s.skip = 0
    def handle_starttag(s, t, a):
        if t in ("script", "style", "noscript"): s.skip += 1
    def handle_endtag(s, t):
        if t in ("script", "style", "noscript") and s.skip: s.skip -= 1
        if t in ("p", "li", "tr", "div", "h1", "h2", "h3", "br"): s.out.append("\n")
    def handle_data(s, d):
        if not s.skip: s.out.append(d)

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

idx = build_index()
pending = json.loads(PENDING.read_text("utf-8")) if PENDING.exists() else []
today = datetime.date.today().isoformat()
with open(ROOT / "tools" / "sites.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        url = row["url"]; name = re.sub(r"[^A-Za-z0-9]+", "-", url).strip("-")[:80]; snap = SNAP / (name + ".txt")
        try:
            p = Text(); p.feed(fetch(url)); new = [l.strip() for l in "".join(p.out).splitlines() if l.strip()]
        except Exception as e:
            pending.append({"id": f"{name}-{today}-error", "url": url, "date": today, "kind": "error", "diff": [f"読み込めませんでした: {e}"]}); continue
        if snap.exists():
            diff = [l for l in difflib.unified_diff(snap.read_text("utf-8").splitlines(), new, lineterm="", n=0)
                    if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            if diff:
                res, note = None, ""
                try: res = ask_ai(url, diff, idx)
                except Exception as e: note = f"AI判定に失敗したため簡易判定です({e})"
                if res:
                    target, conf, reason, changes = res.get("target", "UNKNOWN"), res.get("confidence", "低"), res.get("reason", ""), res.get("changes", [])
                else:
                    c = rank(idx, url, row.get("memo", "") + " ".join(diff))
                    target, conf, changes = (c[0][1]["path"], "中" if c[0][0] >= 70 else "低", []) if c else ("UNKNOWN", "低", [])
                    reason = note or "サイト名やリンクが似ているページです(AI未使用)"
                if target != "NONE":
                    pending.append({"id": f"{name}-{today}", "url": url, "date": today, "kind": "change", "target": target,
                                    "confidence": conf, "reason": reason, "changes": changes, "diff": diff[:60]})
        snap.write_text("\n".join(new), "utf-8"); time.sleep(3)  # 公式サイトに負担をかけない
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=1), "utf-8")
