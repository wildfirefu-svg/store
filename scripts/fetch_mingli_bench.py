"""MingLi-Bench 数据获取前置（设计 §3.2）。

固定 commit、SHA-256、许可证记录；任何失败记 BLOCKED（退出码 4），不阻塞 BaziQA 线。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_URL = "https://github.com/DestinyLinker/MingLi-Bench"
PINNED_COMMIT = "b7433280fd86d7a7c27debbc47d0303c218f0bfd"
REQUIRED_FILES = ("data/data.json", "data/fortune_api_results.json")
DEST_DIR = Path("data/mingli")
MANIFEST_PATH = Path(".tmp/phase6/mingli_fetch_manifest.json")
LICENSE_DIR = Path("docs/phase7")
BLOCKED_EXIT = 4


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def _copy_required(src_root: Path) -> list[dict]:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for rel in REQUIRED_FILES:
        src = src_root / rel
        if not src.exists():
            raise FileNotFoundError(f"必需文件缺失: {src}")
        dst = DEST_DIR / Path(rel).name
        shutil.copyfile(src, dst)
        entries.append({
            "path": str(dst), "sha256": sha256_file(dst), "bytes": dst.stat().st_size,
        })
    return entries


def _license_info(src_root: Path, license_out: Path) -> dict:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        p = src_root / name
        if p.exists():
            license_out.mkdir(parents=True, exist_ok=True)
            dst = license_out / p.name
            shutil.copyfile(p, dst)
            return {
                "note": f"{name} 存在（{p.stat().st_size} bytes）",
                "license_sha256": sha256_file(p),
                "license_copy_path": str(dst),
            }
    return {
        "note": "未发现 LICENSE 文件；README 声明 MIT（需人工复核）",
        "license_sha256": None,
        "license_copy_path": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MingLi-Bench 数据获取前置")
    parser.add_argument("--source-dir", type=Path, default=None,
                        help="本地已有仓库副本时跳过网络获取（测试/离线用）")
    parser.add_argument("--work-dir", type=Path, default=Path(".tmp/phase6/mingli_src"))
    parser.add_argument("--manifest-out", type=Path, default=MANIFEST_PATH,
                        help="manifest 输出路径")
    parser.add_argument("--license-out", type=Path, default=LICENSE_DIR,
                        help="LICENSE 副本输出目录（文件名保持源文件名）")
    args = parser.parse_args(argv)

    try:
        if args.source_dir is not None:
            src_root = args.source_dir
            if not src_root.exists():
                raise FileNotFoundError(f"--source-dir 不存在: {src_root}")
            if not (src_root / ".git").exists():
                raise RuntimeError(f"--source-dir 不是 git 仓库: {src_root}")
            r = _git(["rev-parse", "HEAD"], cwd=src_root)
            if r.returncode != 0:
                raise RuntimeError(f"git rev-parse HEAD 失败: {r.stderr.strip()[:400]}")
            head = r.stdout.strip()
            if head != PINNED_COMMIT:
                raise RuntimeError(f"HEAD {head} != 钉死 commit {PINNED_COMMIT}")
        else:
            src_root = args.work_dir
            if not (src_root / ".git").exists():
                src_root.parent.mkdir(parents=True, exist_ok=True)
                r = _git(["clone", "--no-checkout", REPO_URL, str(src_root)])
                if r.returncode != 0:
                    raise RuntimeError(f"git clone 失败: {r.stderr.strip()[:400]}")
            r = _git(["checkout", PINNED_COMMIT], cwd=src_root)
            if r.returncode != 0:
                raise RuntimeError(
                    f"git checkout {PINNED_COMMIT} 失败: {r.stderr.strip()[:400]}"
                )
            head = _git(["rev-parse", "HEAD"], cwd=src_root).stdout.strip()
            if head != PINNED_COMMIT:
                raise RuntimeError(f"HEAD {head} != 钉死 commit {PINNED_COMMIT}")

        entries = _copy_required(src_root)
        license_info = _license_info(src_root, args.license_out)
        manifest = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "repo": REPO_URL,
            "pinned_commit": PINNED_COMMIT,
            "license": license_info["note"],
            "license_sha256": license_info["license_sha256"],
            "license_copy_path": license_info["license_copy_path"],
            "files": entries,
        }
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_out.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({"status": "OK", "files": [e["path"] for e in entries]},
                         ensure_ascii=False))
        return 0
    except Exception as exc:  # 任何失败 → BLOCKED（设计 §3.2）
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
