"""Download the demo data bundle, check its SHA-256 and unpack it (D-037).

    python fetch_data.py TARGET_DIR

The bundle (prebuilt memory store, saved model replies, transcripts) lives in a public Hugging Face
dataset: GitHub release uploads kept failing on a slow connection, and the dataset upload resumes.
"""

from __future__ import annotations

import hashlib
import sys
import tarfile
import urllib.request

URL = "https://huggingface.co/datasets/mithilyr/meeting-memory-demo-data/resolve/main/memory-bundle.tar.gz"
SHA256 = "8a2dfa2bbdc081ebfb1017e527b609fb2da61005a72bf39f69433ba2ea6b7a4a"


def main(target: str) -> None:
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(URL, "/tmp/bundle.tgz")
            break
        except OSError as error:
            if attempt == 2:
                raise
            print(f"retrying: {error}")
    digest = hashlib.sha256(open("/tmp/bundle.tgz", "rb").read()).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"bundle checksum mismatch: {digest}")
    tarfile.open("/tmp/bundle.tgz", "r:gz").extractall(target, filter="data")
    print(f"unpacked into {target}")


if __name__ == "__main__":
    main(sys.argv[1])
