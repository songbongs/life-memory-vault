#!/usr/bin/env python3
"""A0 tests: enrichment dependency gate (trafilatura) + config keys.

No network, no real vault. The missing-dependency case is simulated via an
injected checker, so this passes whether or not trafilatura is installed.

    python3 tests/test_enrich_dep.py
"""

import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mem  # noqa: E402


def test_dep_present_no_hint():
    s = mem.enrichment_dependency_status(checker=lambda name: True)
    assert s["trafilatura"] is True
    assert s["hint"] == ""


def test_dep_missing_gives_install_hint():
    s = mem.enrichment_dependency_status(checker=lambda name: False)
    assert s["trafilatura"] is False
    assert "trafilatura" in s["hint"] and "pip install" in s["hint"]


def test_dep_checks_trafilatura_by_name():
    seen = []
    mem.enrichment_dependency_status(checker=lambda name: seen.append(name) or True)
    assert seen == ["trafilatura"]


def test_doctor_includes_enrichment_section():
    cfg = {"memoryVault": {"vaultPath": "/tmp"}, "tools": {}}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.doctor(cfg, Path("/tmp/x.json"))
    out = json.loads(buf.getvalue())
    assert "enrichment" in out
    assert "trafilatura" in out["enrichment"]
    # doctor must not crash or exit when the dep section is added.


def test_example_config_has_enrichment_keys():
    cfg = json.loads((ROOT / "memory-config.example.json").read_text(encoding="utf-8"))
    e = cfg.get("enrichment", {})
    assert e.get("enabled") is True
    assert e.get("auto") is True
    assert e.get("maxCandidatesPerRun") == 5
    assert e.get("onDemandNoticeThreshold") == 10
    assert e.get("extractsSubdir") == "Extracts"
    assert "#노요약" in e.get("optOutTags", [])


def test_real_config_enrichment_matches_example_if_present():
    real = ROOT / "memory-config.json"
    if not real.exists():  # gitignored; may be absent in CI
        return
    cfg = json.loads(real.read_text(encoding="utf-8"))
    e = cfg.get("enrichment", {})
    assert e.get("maxCandidatesPerRun") == 5, "real config out of sync with example"
    assert e.get("onDemandNoticeThreshold") == 10


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
