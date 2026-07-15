#!/usr/bin/env python3
"""Tests for `mem.py prune-orphans` — removing orphan/ghost structured notes.

Temp vault, no network. Runs without pytest:  python3 tests/test_prune_orphans.py
"""

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402


def setup():
    vault = Path(tempfile.mkdtemp()) / "vault"
    for d in ["00_Inbox/Raw/2026/06", "00_Inbox/Processed", "40_Entities/Songs",
              "40_Entities/Artists", "30_Actions/Tasks", "60_Ideas/Products",
              "60_Ideas/Playlists", "10_Timeline/Daily"]:
        (vault / d).mkdir(parents=True, exist_ok=True)
    return vault, {"memoryVault": {"vaultPath": str(vault)}}


def raw(vault, name, body):
    p = vault / "00_Inbox/Raw/2026/06" / name
    p.write_text(f"---\nsource: \"telegram\"\n---\n\n{body}\n", encoding="utf-8")
    return f"00_Inbox/Raw/2026/06/{name}"


def note(vault, relpath, source_raw, mtype="journal", body="content"):
    p = vault / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    src = f'source_raw: "[[{source_raw[:-3]}]]"\n' if source_raw else ""
    p.write_text(f"---\nmemory_type: \"{mtype}\"\n{src}---\n\n# x\n\n{body}\n", encoding="utf-8")
    return relpath


def marker(vault, raw_rel, structured, mtype, entities=None, dup_of=None):
    import hashlib
    rid = hashlib.sha1(raw_rel.encode()).hexdigest()[:16]
    d = {"raw": raw_rel, "processed_at": "x", "lint_method": "rule_based",
         "plan": {"memory_type": mtype}, "entities_updated": entities or []}
    if dup_of:
        d["duplicate_of"] = dup_of
    else:
        d["structured"] = structured
    (vault / "00_Inbox/Processed" / f"{rid}.json").write_text(json.dumps(d), encoding="utf-8")


def run(config, apply=False):
    args = argparse.Namespace(apply=apply)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.prune_orphans(args, config)
    return json.loads(buf.getvalue())


def build_scenario():
    """A vault mirroring the real situation: ghosts + legit notes + a manual note."""
    vault, cfg = setup()
    # task raw, correctly classified to Tasks (referenced)
    r_task = raw(vault, "task1.md", "* 할일: 프로젝트 진행 - 카카오톡 요약봇 추가")
    note(vault, "30_Actions/Tasks/task1.md", r_task, "task")
    marker(vault, r_task, "30_Actions/Tasks/task1.md", "task")
    # GHOST music entities pointing at the task raw (should be deleted)
    note(vault, "40_Entities/Songs/카카오톡 요약봇.md", r_task, "song")
    note(vault, "40_Entities/Artists/할일 프로젝트.md", r_task, "artist")
    note(vault, "60_Ideas/Playlists/카카오톡 요약봇.md", r_task, "playlist")
    # GHOST journal duplicate of a github note now in Products
    r_gh = raw(vault, "gh.md", "https://github.com/x/y 라이브러리")
    note(vault, "60_Ideas/Products/github x y.md", r_gh, "product")
    marker(vault, r_gh, "60_Ideas/Products/github x y.md", "product")
    note(vault, "10_Timeline/Daily/github x y.md", r_gh, "journal")  # ghost
    # LEGIT song entity (raw classifies song) — unreferenced but must survive
    r_song = raw(vault, "song.md", "노래저장: 좋아하는 곡 #음악")
    note(vault, "40_Entities/Songs/노래저장 곡.md", r_song, "song")
    marker(vault, r_song, "60_Ideas/Playlists/노래저장 곡.md", "song")  # main note elsewhere
    # PURE manual note (unreferenced, no source) — report only, keep
    note(vault, "10_Timeline/Daily/내 수동 메모.md", "", "journal")
    return vault, cfg


def test_dryrun_finds_ghosts_but_deletes_nothing():
    vault, cfg = build_scenario()
    out = run(cfg, apply=False)
    paths = {o["path"] for o in out["orphans"]}
    assert "40_Entities/Songs/카카오톡 요약봇.md" in paths
    assert "40_Entities/Artists/할일 프로젝트.md" in paths
    assert "60_Ideas/Playlists/카카오톡 요약봇.md" in paths
    assert "10_Timeline/Daily/github x y.md" in paths
    assert out["would_delete"] == 4, out
    # nothing deleted in dry-run
    assert (vault / "40_Entities/Songs/카카오톡 요약봇.md").exists()


def test_legit_music_entity_survives():
    vault, cfg = build_scenario()
    out = run(cfg, apply=False)
    paths = {o["path"] for o in out["orphans"]}
    assert "40_Entities/Songs/노래저장 곡.md" not in paths  # raw classifies song -> keep


def test_manual_note_is_report_only():
    vault, cfg = build_scenario()
    out = run(cfg, apply=False)
    assert "10_Timeline/Daily/내 수동 메모.md" in out["report_only"]
    assert "10_Timeline/Daily/내 수동 메모.md" not in {o["path"] for o in out["orphans"]}


def test_apply_deletes_ghosts_keeps_rest():
    vault, cfg = build_scenario()
    out = run(cfg, apply=True)
    assert out["deleted"] == 4
    assert not (vault / "40_Entities/Songs/카카오톡 요약봇.md").exists()
    assert not (vault / "40_Entities/Artists/할일 프로젝트.md").exists()
    assert not (vault / "10_Timeline/Daily/github x y.md").exists()
    # legit + manual + correct notes remain
    assert (vault / "40_Entities/Songs/노래저장 곡.md").exists()
    assert (vault / "10_Timeline/Daily/내 수동 메모.md").exists()
    assert (vault / "30_Actions/Tasks/task1.md").exists()
    assert (vault / "60_Ideas/Products/github x y.md").exists()
    assert Path(out["backup"]).exists()  # backup made


def test_idempotent_second_run_finds_none():
    vault, cfg = build_scenario()
    run(cfg, apply=True)
    out2 = run(cfg, apply=False)
    assert out2["would_delete"] == 0, out2


def test_entities_updated_keeps_referenced_entity():
    # an entity recorded in a marker's entities_updated must never be flagged
    vault, cfg = setup()
    r = raw(vault, "s.md", "IU - 밤편지 https://music.youtube.com/x")
    note(vault, "40_Entities/Artists/IU.md", r, "artist")
    note(vault, "60_Ideas/Playlists/IU 밤편지.md", r, "song")
    marker(vault, r, "60_Ideas/Playlists/IU 밤편지.md", "song", entities=["40_Entities/Artists/IU.md"])
    out = run(cfg, apply=False)
    assert "40_Entities/Artists/IU.md" not in {o["path"] for o in out["orphans"]}


def test_nfc_nfd_referenced_note_not_flagged():
    # macOS stores filenames NFD; marker JSON holds NFC. A referenced note must
    # NOT be flagged as a ghost just because of the normalization mismatch.
    import unicodedata
    vault, cfg = setup()
    base = "60_Ideas/Products/노래 서비스 메모.md"
    nfd = unicodedata.normalize("NFD", base)
    nfc = unicodedata.normalize("NFC", base)
    r = raw(vault, "x.md", "서비스 메모 https://x.com 사용해볼 서비스")
    p = vault / nfd                       # file on disk with NFD name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\nmemory_type: "product"\nsource_raw: "[[{r[:-3]}]]"\n---\n# x\n', encoding="utf-8")
    marker(vault, r, nfc, "product")      # marker references NFC path
    out = run(cfg, apply=False)
    flagged = {unicodedata.normalize("NFC", o["path"]) for o in out["orphans"]}
    assert nfc not in flagged, out


def test_stale_canonical_target_is_not_deleted():
    # A marker can claim a "canonical" structured note that was itself since
    # deleted/renamed without the marker being updated. If prune-orphans trusted
    # that claim blindly it would delete the only surviving copy (real incident,
    # 2026-07-15: 13/32 flagged notes had a nonexistent "canonical" target).
    vault, cfg = setup()
    r = raw(vault, "x.md", "관심 프로젝트 메모 https://example.com")
    note(vault, "40_Notes/Saves/real-note.md", r, "save")
    # marker claims the canonical is this path, but that file is never created
    marker(vault, r, "60_Ideas/Products/이미 삭제된 정식본.md", "product")
    out = run(cfg, apply=False)
    assert "40_Notes/Saves/real-note.md" not in {o["path"] for o in out["orphans"]}
    assert (vault / "40_Notes/Saves/real-note.md").exists()
    assert any("stale_marker" in r for r in out["report_only"])


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
