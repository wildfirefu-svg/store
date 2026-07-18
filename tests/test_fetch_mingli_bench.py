from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.fetch_mingli_bench as fetcher


def make_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "data").mkdir(parents=True)
    (src / "data" / "data.json").write_text(
        json.dumps([{"case_id": "m1"}], ensure_ascii=False), encoding="utf-8"
    )
    (src / "data" / "fortune_api_results.json").write_text(
        json.dumps({"m1": {"bazi": {}}}, ensure_ascii=False), encoding="utf-8"
    )
    (src / "LICENSE").write_text("MIT License", encoding="utf-8")
    return src


def test_fetch_from_source_dir(tmp_path, monkeypatch):
    src = make_source(tmp_path)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pinned_commit"] == fetcher.PINNED_COMMIT
    assert [Path(f["path"]).name for f in manifest["files"]] == [
        "data.json", "fortune_api_results.json",
    ]
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])
    assert "LICENSE" in manifest["license"]


def test_missing_required_file_blocked(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == fetcher.BLOCKED_EXIT


def test_missing_source_dir_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(tmp_path / "nope")]) == fetcher.BLOCKED_EXIT
    assert "BLOCKED" in capsys.readouterr().out
