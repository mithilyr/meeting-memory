"""Stage (and optionally push) the hosted read-only demo for Hugging Face Spaces (D-037).

    python deploy/build_space.py                         # stage into deploy/hf-space/build/
    python deploy/build_space.py --push USER/meeting-memory    # stage, then upload (needs `hf auth login`)

The Space gets the code, the 138 transcripts, the prebuilt memory store (so it starts in seconds, with no
re-extraction or re-embedding) and the saved model replies (so the demo questions answer at once). It does
not get .env: the API keys are added as Space secrets by the account owner.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
BUILD = HERE / "hf-space" / "build"


def stage() -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    shutil.copytree(ROOT / "src", BUILD / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.before-ai-signs.*"))
    for name in ("Dockerfile", "README.md"):
        shutil.copy2(HERE / "hf-space" / name, BUILD / name)
    (BUILD / "requirements.txt").write_text("numpy==2.4.6\npython-dotenv==1.0.1\n", encoding="utf-8")
    data = ROOT.parent / "Catalist_AI_Intern_Build_Test_Data" / "transcripts"
    shutil.copytree(data, BUILD / "data" / "transcripts")
    (BUILD / ".cache").mkdir()
    # copy the store through SQLite's backup API, so a half-written page can't end up in the image
    source = sqlite3.connect(ROOT / ".cache" / "memory.sqlite")
    target = sqlite3.connect(BUILD / ".cache" / "memory.sqlite")
    source.backup(target)
    target.execute("VACUUM")
    source.close(), target.close()
    shutil.copytree(ROOT / ".cache" / "responses_openrouter", BUILD / ".cache" / "responses_openrouter")
    leaked = [p for p in BUILD.rglob("*") if p.name in (".env", ".env.local")]
    assert not leaked, f"secrets must not ship: {leaked}"
    size = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file()) / 1e6
    print(f"staged {BUILD} ({size:.0f} MB)")
    return BUILD


def push(repo_id: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(folder_path=str(BUILD), repo_id=repo_id, repo_type="space",
                      commit_message="Deploy Meeting Memory read-only demo")
    print(f"pushed: https://huggingface.co/spaces/{repo_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage or push the Hugging Face Space.")
    parser.add_argument("--push", metavar="USER/SPACE")
    args = parser.parse_args()
    stage()
    if args.push:
        push(args.push)
