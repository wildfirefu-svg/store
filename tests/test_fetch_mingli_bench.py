from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.fetch_mingli_bench as fetcher


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
    )


def _git_init_commit(src: Path) -> str:
    """repo-local 身份提交全部文件，返回 HEAD sha（不得依赖全局 git 配置）。"""
    _git(["init"], src)
    _git(["config", "user.name", "test"], src)
    _git(["config", "user.email", "test@example.com"], src)
    _git(["add", "-A"], src)
    _git(["commit", "--allow-empty", "-m", "fixture"], src)
    return _git(["rev-parse", "HEAD"], src).stdout.strip()


def make_source(tmp_path: Path) -> tuple[Path, str]:
    """初始化临时 Git 仓库夹具，返回 (repo 路径, HEAD sha)。"""
    src = tmp_path / "src"
    (src / "data").mkdir(parents=True)
    (src / "data" / "data.json").write_text(
        json.dumps([{"case_id": "m1"}], ensure_ascii=False), encoding="utf-8"
    )
    (src / "data" / "fortune_api_results.json").write_text(
        json.dumps({"m1": {"bazi": {}}}, ensure_ascii=False), encoding="utf-8"
    )
    (src / "LICENSE").write_text("MIT License", encoding="utf-8")
    return src, _git_init_commit(src)


def test_fetch_from_source_dir(tmp_path, monkeypatch):
    src, head = make_source(tmp_path)
    monkeypatch.setattr(fetcher, "PINNED_COMMIT", head)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main([
        "--source-dir", str(src),
        "--manifest-out", str(tmp_path / "manifest.json"),
        "--license-out", str(tmp_path / "lic"),
    ]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pinned_commit"] == fetcher.PINNED_COMMIT
    assert [Path(f["path"]).name for f in manifest["files"]] == [
        "data.json", "fortune_api_results.json",
    ]
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])
    assert "LICENSE" in manifest["license"]


def test_missing_required_file_blocked(tmp_path, monkeypatch):
    # 目录先 Git 化且 HEAD 匹配——确保测的是"缺文件"，而非提前被"非 Git 来源"阻断
    src = tmp_path / "src"
    src.mkdir()
    head = _git_init_commit(src)
    monkeypatch.setattr(fetcher, "PINNED_COMMIT", head)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == fetcher.BLOCKED_EXIT


def test_missing_source_dir_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(tmp_path / "nope")]) == fetcher.BLOCKED_EXIT
    assert "BLOCKED" in capsys.readouterr().out


def test_manifest_out_and_license_out(tmp_path, monkeypatch):
    src, head = make_source(tmp_path)
    monkeypatch.setattr(fetcher, "PINNED_COMMIT", head)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    manifest_out = tmp_path / "out" / "manifest.json"
    license_out = tmp_path / "lic"
    assert fetcher.main([
        "--source-dir", str(src),
        "--manifest-out", str(manifest_out),
        "--license-out", str(license_out),
    ]) == 0
    manifest = json.loads(manifest_out.read_text(encoding="utf-8"))
    license_copy = license_out / "LICENSE"
    assert license_copy.exists()
    assert license_copy.read_text(encoding="utf-8") == "MIT License"
    assert manifest["license_sha256"] == fetcher.sha256_file(license_copy)
    assert manifest["license_copy_path"] == str(license_copy)


def test_source_dir_non_git_blocked(tmp_path, monkeypatch, capsys):
    # 普通非 Git 目录（有必需文件但无 .git）→ 拒绝
    src = tmp_path / "plain"
    (src / "data").mkdir(parents=True)
    (src / "data" / "data.json").write_text("[]", encoding="utf-8")
    (src / "data" / "fortune_api_results.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == fetcher.BLOCKED_EXIT
    assert "BLOCKED" in capsys.readouterr().out


def test_source_dir_head_mismatch_blocked(tmp_path, monkeypatch, capsys):
    src, _head = make_source(tmp_path)
    monkeypatch.setattr(fetcher, "PINNED_COMMIT", "0" * 40)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert fetcher.main(["--source-dir", str(src)]) == fetcher.BLOCKED_EXIT
    assert "BLOCKED" in capsys.readouterr().out


def test_source_dir_head_match_ok(tmp_path, monkeypatch):
    """HEAD == pinned 时放行（红绿两阶段都应通过的回归锁）。"""
    src, head = make_source(tmp_path)
    monkeypatch.setattr(fetcher, "PINNED_COMMIT", head)
    monkeypatch.setattr(fetcher, "DEST_DIR", tmp_path / "dest")
    monkeypatch.setattr(fetcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(fetcher, "LICENSE_DIR", tmp_path / "lic", raising=False)
    assert fetcher.main(["--source-dir", str(src)]) == 0
