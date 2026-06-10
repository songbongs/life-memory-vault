#!/usr/bin/env python3
"""Learned-rules store for the Life Memory learning loop (③d-1).

Captures Review-resolution decisions (signal -> memory_type) and derives rules.
A signal confirmed >= promoteThreshold times with no contradicting type becomes
`active` and is then applied deterministically by mem.classify (③d-2), so the
same pattern no longer needs Review.

Store: vault 90_System/Rules/learned-rules.json (SSOT) + Learned Rules.md mirror.
Writes are atomic. The module is pure/injectable for tests (RuleStore takes paths).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "memory-config.json"
DEFAULT_THRESHOLD = 2
EMPTY: dict[str, Any] = {"version": 1, "decisions": [], "rules": []}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_signal(signal: str) -> str:
    return " ".join((signal or "").lower().split())


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


class RuleStore:
    def __init__(self, json_path: str | Path, mirror_path: str | Path | None = None, threshold: int = DEFAULT_THRESHOLD) -> None:
        self.json_path = Path(json_path)
        self.mirror_path = Path(mirror_path) if mirror_path else None
        self.threshold = max(1, int(threshold))

    # --- persistence ---
    def load(self) -> dict[str, Any]:
        if not self.json_path.exists():
            return json.loads(json.dumps(EMPTY))
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return json.loads(json.dumps(EMPTY))
        data.setdefault("version", 1)
        data.setdefault("decisions", [])
        data.setdefault("rules", [])
        return data

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        data["rules"] = self.derive(data["decisions"])
        _atomic_write(self.json_path, json.dumps(data, ensure_ascii=False, indent=2))
        if self.mirror_path:
            _atomic_write(self.mirror_path, self._mirror(data["rules"]))
        return data

    # --- mutations ---
    def add_decision(self, signal: str, memory_type: str, folder: str = "", source_raw: str = "", by: str = "cli") -> dict[str, Any]:
        sig = normalize_signal(signal)
        if not sig or not memory_type:
            raise ValueError("signal and memory_type are required")
        data = self.load()
        data["decisions"].append({
            "signal": sig, "type": memory_type, "folder": folder,
            "source_raw": source_raw, "decided_at": now_iso(), "by": by,
        })
        return self.save(data)

    def remove(self, signal: str) -> int:
        sig = normalize_signal(signal)
        data = self.load()
        before = len(data["decisions"])
        data["decisions"] = [d for d in data["decisions"] if d.get("signal") != sig]
        removed = before - len(data["decisions"])
        if removed:
            self.save(data)
        return removed

    # --- derivation ---
    def derive(self, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_sig: dict[str, list[dict[str, Any]]] = {}
        for d in decisions:
            by_sig.setdefault(d.get("signal", ""), []).append(d)

        rules: list[dict[str, Any]] = []
        for sig, ds in sorted(by_sig.items()):
            if not sig:
                continue
            types = sorted({d.get("type") for d in ds if d.get("type")})
            # confirmations: distinct non-empty source_raw + each source-less decision
            sources = [d.get("source_raw", "") for d in ds]
            unique_sources = sorted({s for s in sources if s})
            confirmations = len(unique_sources) + sum(1 for s in sources if not s)
            decided = [d.get("decided_at", "") for d in ds if d.get("decided_at")]
            contradicted = len(types) > 1
            if contradicted:
                status, mtype, folder = "blocked", None, ""
            else:
                mtype = types[0] if types else None
                folder = next((d.get("folder", "") for d in ds if d.get("folder")), "")
                status = "active" if confirmations >= self.threshold else "candidate"
            rules.append({
                "signal": sig, "type": mtype, "folder": folder, "status": status,
                "confirmations": confirmations, "examples": unique_sources[:5],
                "contradicted": contradicted, "types": types,
                "created_at": min(decided) if decided else "", "updated_at": max(decided) if decided else "",
            })
        return rules

    def rules(self) -> list[dict[str, Any]]:
        return self.derive(self.load()["decisions"])

    def active_rules(self) -> list[dict[str, Any]]:
        """Minimal shape consumed by mem.classify (③d-2)."""
        return [{"signal": r["signal"], "type": r["type"], "folder": r["folder"]}
                for r in self.rules() if r["status"] == "active"]

    # --- human-readable mirror ---
    def _mirror(self, rules: list[dict[str, Any]]) -> str:
        lines = ["# Learned Rules", "",
                 "자동 생성 파일 — 직접 편집하지 말 것. 규칙 취소는 `python3 scripts/rules.py remove \"<signal>\"`.", ""]
        groups = [("Active (자동분류 적용 중)", "active"),
                  ("Candidate (확인 부족)", "candidate"),
                  ("Blocked (모순 — 자동분류 안 함)", "blocked")]
        for title, status in groups:
            items = [r for r in rules if r["status"] == status]
            lines.append(f"## {title}")
            if not items:
                lines.append("- (없음)")
            for r in items:
                if status == "blocked":
                    lines.append(f"- `{r['signal']}` → ? (충돌: {', '.join(r['types'])})")
                else:
                    lines.append(f"- `{r['signal']}` → {r['type']} (확인 {r['confirmations']}/{self.threshold})")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def from_config(config_path: str | Path, rules_file: str = "") -> RuleStore:
    cfg = json.loads(Path(config_path).expanduser().read_text(encoding="utf-8"))
    learning = cfg.get("learning", {})
    threshold = int(learning.get("promoteThreshold", DEFAULT_THRESHOLD))
    if rules_file:
        return RuleStore(rules_file, None, threshold)
    vault = Path(cfg["memoryVault"]["vaultPath"]).expanduser()
    rules_rel = learning.get("rulesPath", "90_System/Rules/learned-rules.json")
    mirror_rel = learning.get("mirrorPath", "90_System/Rules/Learned Rules.md")
    return RuleStore(vault / rules_rel, vault / mirror_rel, threshold)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Life Memory learned-rules store")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--rules-file", default="", help="Override store path (testing/isolation)")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add-decision", help="Record a Review-resolution decision")
    add.add_argument("--signal", required=True)
    add.add_argument("--type", required=True, dest="memory_type")
    add.add_argument("--folder", default="")
    add.add_argument("--source", default="", dest="source_raw")
    add.add_argument("--by", default="cli")

    lst = sub.add_parser("list", help="List derived rules")
    lst.add_argument("--status", default="", help="active | candidate | blocked")

    sub.add_parser("active", help="List active rules (consumer view)")

    rm = sub.add_parser("remove", help="Revoke all decisions for a signal")
    rm.add_argument("signal")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = from_config(args.config, args.rules_file)
    if args.command == "add-decision":
        store.add_decision(args.signal, args.memory_type, args.folder, args.source_raw, args.by)
        print(json.dumps({"added": normalize_signal(args.signal), "type": args.memory_type}, ensure_ascii=False, indent=2))
    elif args.command == "list":
        rules = store.rules()
        if args.status:
            rules = [r for r in rules if r["status"] == args.status]
        print(json.dumps({"rules": rules, "count": len(rules)}, ensure_ascii=False, indent=2))
    elif args.command == "active":
        print(json.dumps({"active": store.active_rules()}, ensure_ascii=False, indent=2))
    elif args.command == "remove":
        n = store.remove(args.signal)
        print(json.dumps({"removed_decisions": n, "signal": normalize_signal(args.signal)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
