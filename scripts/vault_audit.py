#!/usr/bin/env python3
"""볼트 종합 점검 — 읽기 전용. 아무것도 바꾸지 않는다.

사용:
    python3 -B scripts/vault_audit.py                 # 요약만
    python3 -B scripts/vault_audit.py report.json     # 상세를 파일로
    python3 -B scripts/vault_audit.py --full          # 상세를 화면에

점검 항목: 폴더/타입 불일치 · 파일명≠H1 · 제목 규칙 위반 · 태그 없음 ·
프론트매터 중복 키 · 깨진 위키링크 · 중복 노트 · MOC 색인 커버리지
(2026-08-16 볼트 전수 정리 때 만든 스크립트. 자동화에는 아직 안 붙였다)
"""
import json, os, re, sys, unicodedata as ud
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "memory-config.json"), encoding="utf-8") as _fh:
    V = json.load(_fh)["memoryVault"]["vaultPath"]
N = lambda s: ud.normalize("NFC", s or "")

STRUCT_DIRS = ["10_Daily", "10_Timeline", "20_Records", "30_Actions", "40_Entities",
               "40_Notes", "50_Experiences", "60_Ideas"]
SKIP_DIRS = ["00_Inbox/Raw", "00_Inbox/Processed", "80_Assets", "90_System/Logs",
             ".trash", ".smart-env", ".obsidian"]

FOLDER_BY_TYPE = {
    "task": "30_Actions/Tasks", "appointment": "30_Actions/Appointments",
    "reminder": "30_Actions/Reminders", "maintenance": "20_Records/Maintenance",
    "ledger": "20_Records/Ledger", "health": "20_Records/Health",
    "person": "40_Notes/People", "place": "40_Notes/Places", "thing": "40_Notes/Things",
    "song": "40_Notes/Music", "playlist": "40_Notes/Music",
    "food_drink": "40_Notes/Experiences", "trip": "40_Notes/Experiences",
    "save": "40_Notes/Saves", "project": "40_Notes/Saves", "product": "40_Notes/Saves",
    "idea": "40_Notes/Saves", "journal": "10_Daily",
}

BANNED = ["AI 프로젝트", "AI design", "AI plugins", "AI util", "AI tts", "AI RAG",
          "AI investment", "LLMWIKI", "적용후보", "관심 프로젝트", "공부대상", "추천대상",
          "노래저장", "메모저장"]
URLPAT = re.compile(r"(github\.com|https?://|\.com/|\.app/|vercel\.app|duckdns)", re.I)


def all_md():
    out = []
    for root, dirs, files in os.walk(V):
        rel_root = N(os.path.relpath(root, V))
        if any(rel_root == s or rel_root.startswith(s + "/") for s in SKIP_DIRS):
            dirs[:] = []
            continue
        for f in files:
            if f.endswith(".md"):
                out.append(os.path.join(root, f))
    return sorted(out)


def parse(p):
    try:
        t = open(p, encoding="utf-8", errors="ignore").read()
    except OSError:
        return None, "", ""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", t, re.S)
    fm, body = (m.group(1), m.group(2)) if m else ("", t)
    return fm, body, t


def fm_get(fm, key):
    m = re.search(rf'^{key}:[ \t]*(.+)$', fm, re.M)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def fm_list(fm, key):
    m = re.search(rf'^{key}:[ \t]*(.*)$((?:\n[ \t]+-.*)*)', fm, re.M)
    if not m:
        return []
    inline = m.group(1).strip()
    if inline.startswith("["):
        return [x.strip().strip('"').strip("'") for x in inline.strip("[]").split(",") if x.strip()]
    items = re.findall(r'^[ \t]+-\s*(.+)$', m.group(2) or "", re.M)
    return [i.strip().strip('"').strip("'") for i in items]


notes = []
for p in all_md():
    rel = N(os.path.relpath(p, V))
    fm, body, raw = parse(p)
    h1 = ""
    mh = re.search(r"^#\s+(.+)$", body, re.M)
    if mh:
        h1 = mh.group(1).strip()
    notes.append(dict(
        rel=rel, stem=N(os.path.basename(rel)[:-3]), folder=N(os.path.dirname(rel)),
        mtype=fm_get(fm, "memory_type"), h1=N(h1),
        tags=[N(x) for x in fm_list(fm, "tags")],
        source_raw=fm_get(fm, "source_raw"),
        has_fm=bool(fm), body=body, text=raw,
    ))

by_rel = {n["rel"]: n for n in notes}
stems = defaultdict(list)
for n in notes:
    stems[n["stem"]].append(n["rel"])

report = {}

# --- 1. 폴더/타입 불일치 -------------------------------------------------
mism = []
for n in notes:
    if n["folder"].startswith("90_System") or n["folder"] == "00_Inbox/Review":
        continue
    t = n["mtype"]
    if not t:
        continue
    want = FOLDER_BY_TYPE.get(t)
    if want and n["folder"] != want:
        mism.append({"note": n["rel"], "type": t, "expected": want})
report["folder_type_mismatch"] = mism

# --- 2. 파일명 != H1 ------------------------------------------------------
h1bad = [{"note": n["rel"], "h1": n["h1"]} for n in notes
         if n["h1"] and n["h1"] != n["stem"] and not n["folder"].startswith("90_System")
         and n["folder"] != "00_Inbox/Review"]
report["filename_h1_mismatch"] = h1bad

# --- 3. 제목 규칙 위반 ----------------------------------------------------
tbad = []
for n in notes:
    if n["folder"].startswith("90_System") or n["folder"].startswith("10_Daily") and re.match(r"^\d{4}-\d{2}-\d{2}$", n["stem"]):
        continue
    if n["folder"] == "00_Inbox/Review":
        continue
    reasons = []
    s = n["stem"]
    for b in BANNED:
        if b.lower() in s.lower():
            reasons.append(f"금지어 '{b}'")
    if URLPAT.search(s):
        reasons.append("URL/도메인 포함")
    if len(s) > 40:
        reasons.append(f"{len(s)}자 (40자 초과)")
    if reasons:
        tbad.append({"note": n["rel"], "reasons": reasons})
report["title_violations"] = tbad

# --- 4. 태그 없음 ---------------------------------------------------------
notag = [n["rel"] for n in notes
         if not n["tags"] and n["mtype"]
         and not n["folder"].startswith("90_System")
         and n["folder"] != "00_Inbox/Review"]
report["no_tags"] = notag

# --- 4-2. 프론트매터 중복 키 -------------------------------------------------
dupkey = []
for n in notes:
    fm, _, _ = parse(os.path.join(V, n["rel"]))
    if not fm:
        continue
    keys = re.findall(r"^([A-Za-z_]+):", fm, re.M)
    seen = set()
    d = sorted({k for k in keys if k in seen or seen.add(k)})
    if d:
        dupkey.append({"note": n["rel"], "keys": d})
report["duplicate_fm_keys"] = dupkey

# --- 5. 깨진 위키링크 -----------------------------------------------------
targets = set(by_rel) | {r[:-3] for r in by_rel}
basenames = defaultdict(list)
for r in by_rel:
    basenames[N(os.path.basename(r)[:-3])].append(r)
# raw/asset 도 링크 대상이 될 수 있으므로 추가
extra = set()
for sub in ["00_Inbox/Raw", "80_Assets", "90_System"]:
    for root, _, fs in os.walk(os.path.join(V, sub)):
        for f in fs:
            rr = N(os.path.relpath(os.path.join(root, f), V))
            extra.add(rr)
            extra.add(rr.rsplit(".", 1)[0])
            basenames[N(os.path.splitext(f)[0])].append(rr)
targets |= extra

broken = []
LINK = re.compile(r"\[\[([^\]\|#\^]+)")
for n in notes:
    if n["folder"].startswith("90_System/Logs"):
        continue
    for m in LINK.finditer(N(n["text"])):
        tgt = m.group(1).strip()
        if not tgt or tgt.startswith("http"):
            continue
        base = N(os.path.basename(tgt))
        base_noext = base[:-3] if base.endswith(".md") else base
        if tgt in targets or tgt.rstrip(".md") in targets:
            continue
        if "/" not in tgt and base_noext in basenames:
            continue
        broken.append({"in": n["rel"], "link": tgt})
report["broken_links"] = broken

# --- 6. 중복 후보 ---------------------------------------------------------
dupname = {k: v for k, v in stems.items() if len(v) > 1}
report["duplicate_stems"] = dupname
marked_dup = [n["rel"] for n in notes if re.search(r"\(중복\d*\)", n["stem"])]
report["marked_duplicate_files"] = marked_dup

# 같은 source_raw 를 가리키는 노트
by_src = defaultdict(list)
for n in notes:
    if n["source_raw"]:
        by_src[N(n["source_raw"])].append(n["rel"])
report["same_source_raw"] = {k: v for k, v in by_src.items() if len(v) > 1}

# --- 7. MOC 색인 커버리지 --------------------------------------------------
moc_text = ""
for f in ["Ideas-MOC.md", "Life-Memory-MOC.md", "Maintenance-MOC.md", "Music-MOC.md"]:
    p = os.path.join(V, "90_System/Index", f)
    if os.path.exists(p):
        moc_text += N(open(p, encoding="utf-8").read())
missing_moc = []
for n in notes:
    if n["folder"] in ("40_Notes/Saves",) or n["mtype"] in ("save", "project", "product", "idea"):
        if n["stem"] not in moc_text:
            missing_moc.append({"note": n["rel"], "type": n["mtype"], "tags": n["tags"]})
report["missing_from_moc"] = missing_moc

report["totals"] = {
    "notes_scanned": len(notes),
    "folder_type_mismatch": len(mism),
    "filename_h1_mismatch": len(h1bad),
    "title_violations": len(tbad),
    "no_tags": len(notag),
    "duplicate_fm_keys": len(dupkey),
    "broken_links": len(broken),
    "duplicate_stems": len(dupname),
    "marked_duplicate_files": len(marked_dup),
    "same_source_raw": len(report["same_source_raw"]),
    "missing_from_moc": len(missing_moc),
}

out = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
if out:
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
if "--full" in sys.argv:
    print(json.dumps(report, ensure_ascii=False, indent=2))
else:
    print(json.dumps(report["totals"], ensure_ascii=False, indent=2))
    if out:
        print("\n상세 ->", out)
