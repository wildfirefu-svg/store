"""Phase 8 provenance 生成（Task 8.1）：从 manifest 生成全量 SHA + 四策略分列 + 对账入口。"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"


def main() -> None:
    manifest = json.loads((P8_DIR / "phase8_freeze_manifest.json").read_text(encoding="utf-8"))
    # 排除 provenance.json 自身条目，避免自引用（provenance 是 manifest 的派生投影）
    self_path = "docs/phase8/marriage-capability/provenance.json"
    entries = [e for e in manifest["entries"] if e["path"] != self_path]
    by_strategy: dict[str, list[dict]] = {}
    for e in entries:
        by_strategy.setdefault(e["strategy"], []).append(e)
    payload = {
        "schema_version": "1.0",
        "generated_from": "docs/phase8/marriage-capability/phase8_freeze_manifest.json",
        "sha_strategies": manifest["sha_strategies"],
        "entries_by_strategy": {k: sorted(v, key=lambda x: x["path"]) for k, v in sorted(by_strategy.items())},
        "reconcile_entry": "python docs/phase8/marriage-capability/p8_reconcile.py",
        "total_entries": len(entries),
        "note": "total_entries 为冻结产物数（不含 provenance.json 自身，避免自引用）",
    }
    out = P8_DIR / "provenance.json"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"provenance written: {len(entries)} entries, strategies={sorted(by_strategy)}")


if __name__ == "__main__":
    main()
