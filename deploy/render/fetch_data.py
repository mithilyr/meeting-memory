"""Download the demo data parts from the GitHub release, join them, check the SHA-256 and unpack (D-037).

    python fetch_data.py RELEASE_URL TARGET_DIR
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import urllib.request

PARTS = [f"memory-bundle.part-{n:02d}" for n in range(5)]


def fetch(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                return response.read()
        except OSError as error:
            if attempt == 2:
                raise
            print(f"retrying {url}: {error}")
    raise RuntimeError("unreachable")


def main(release: str, target: str) -> None:
    blob = b"".join(fetch(f"{release}/{part}") for part in PARTS)
    expected = fetch(f"{release}/memory-bundle.sha256").decode().strip()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise SystemExit(f"bundle checksum mismatch: {actual} != {expected}")
    tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz").extractall(target, filter="data")
    print(f"unpacked {len(blob) / 1e6:.0f} MB into {target}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
