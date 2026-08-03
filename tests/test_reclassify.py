#!/usr/bin/env python3
"""Tests for `mem.py reclassify` — full re-filing of an already-structured note.

Temp vault + isolated rules store, no network.  python3 tests/test_reclassify.py
"""

import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402


def setup():
    base = Path(tempfile.mkdtemp())
    vault = base / "vault"
    # 2026-06-23 재설계 반영: save/product/idea는 전부 40_Notes/Saves로 통합됐고
    # MOC는 90_System/Index로 옮겨졌다. 그래서 "폴더가 실제로 바뀌는" 재분류를
    # 검증하려면 save -> task처럼 계통이 다른 타입 쌍을 써야 한다.
    for d in ["00_Inbox/Raw/2026/06", "00_Inbox/Processed", "40_Notes/Saves",
              "30_Actions/Tasks", "90_System/Index", "90_System/Rules"]:
        (vault / d).mkdir(parents=True, exist_ok=True)
    cfg = {"memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed"},
           "learning": {"enabled": True, "promoteThreshold": 2,
                        "rulesPath": "90_System/Rules/learned-rules.json",
                        "mirrorPath": "90_System/Rules/Learned Rules.md"}}
    cfgp = base / "config.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    return base, vault, cfg, cfgp


def write_raw(vault, name):
    p = vault / "00_Inbox/Raw/2026/06" / name
    p.write_text("---\nsource: telegram\n---\n\n프로젝트 메모 내용\n", encoding="utf-8")
    return f"00_Inbox/Raw/2026/06/{name}"


def write_note(vault, relpath, memory_type, raw_rel):
    p = vault / relpath
    link = raw_rel[:-3]
    p.write_text(f'---\nmemory_type: "{memory_type}"\nsource_raw: "[[{link}]]"\n---\n\n'
                 f'# {p.stem}\n\n## 출처\n\n- [[{link}]]\n\n## 내용\n\n프로젝트 메모\n', encoding="utf-8")
    return p


def write_marker(vault, raw_rel, structured, mtype):
    mid = hashlib.sha1(raw_rel.encode("utf-8")).hexdigest()[:16]
    mp = vault / "00_Inbox/Processed" / f"{mid}.json"
    mp.write_text(json.dumps({"raw": raw_rel, "structured": structured, "plan": {"memory_type": mtype}}),
                  encoding="utf-8")
    return mp


def args(note, new_type, signal="", folder="", title="", apply=False):
    return argparse.Namespace(note=note, type=new_type, signal=signal, folder=folder, title=title, apply=apply)


def run(cfg, cfgp, a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.reclassify(a, cfg, cfgp)
    return json.loads(buf.getvalue())


def test_dry_run_reports_and_changes_nothing():
    base, vault, cfg, cfgp = setup()
    raw = write_raw(vault, "r.md")
    write_note(vault, "40_Notes/Saves/x.md", "save", raw)
    write_marker(vault, raw, "40_Notes/Saves/x.md", "save")
    out = run(cfg, cfgp, args("40_Notes/Saves/x.md", "task"))
    assert out["dry_run"] and out["to_folder"] == "30_Actions/Tasks", out
    assert (vault / "40_Notes/Saves/x.md").exists()  # untouched


def test_apply_moves_updates_marker_relinks_and_learns():
    base, vault, cfg, cfgp = setup()
    raw = write_raw(vault, "r.md")
    write_note(vault, "40_Notes/Saves/x.md", "save", raw)
    mp = write_marker(vault, raw, "40_Notes/Saves/x.md", "save")
    moc = vault / "90_System/Index/Saves-MOC.md"
    moc.write_text("## 목록\n- [[40_Notes/Saves/x]] — 설명 (2026-06-01)\n", encoding="utf-8")

    out = run(cfg, cfgp, args("40_Notes/Saves/x.md", "task", signal="프로젝트", apply=True))

    assert out["memory_type"] == "task"
    assert (vault / "30_Actions/Tasks/x.md").exists()           # moved into task folder
    assert not (vault / "40_Notes/Saves/x.md").exists()         # old removed
    d = json.loads(mp.read_text())
    assert d["structured"] == "30_Actions/Tasks/x.md"           # marker re-pointed
    assert d["plan"]["memory_type"] == "task"
    assert "[[30_Actions/Tasks/x]]" in moc.read_text()          # MOC wikilink rewritten
    assert out["links_updated"] >= 1
    assert out["decision"]["recorded"] is True                  # learning recorded
    assert Path(out["backup"]).exists()


def test_apply_preserves_raw():
    base, vault, cfg, cfgp = setup()
    raw = write_raw(vault, "r.md")
    write_note(vault, "40_Notes/Saves/x.md", "save", raw)
    write_marker(vault, raw, "40_Notes/Saves/x.md", "save")
    run(cfg, cfgp, args("40_Notes/Saves/x.md", "task", apply=True))
    assert (vault / raw).exists()  # raw is sacred


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
