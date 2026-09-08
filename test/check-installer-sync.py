#!/usr/bin/env python3
"""Check that the bundled installer matches the upstream getcsound.sh.

The libcsound package bundles a copy of the csound installer
(libcsound/data/getcsound.sh) used to install csound on macOS when it is not
found. This copy must stay in sync with the upstream file served at
https://csound-plugins.github.io/getcsound.sh.

Usage:
    python test/check-installer-sync.py [PATH_TO_UPSTREAM_GETCSOUND_SH]

If PATH is given, it is compared directly against the bundled copy. Otherwise
the upstream script is downloaded from https://csound-plugins.github.io/getcsound.sh
and compared. Exits with a non-zero status if they differ.
"""
import hashlib
import os
import sys
import urllib.request

UPSTREAM_URL = "https://csound-plugins.github.io/getcsound.sh"
BUNDLED = os.path.join(os.path.dirname(__file__), os.pardir, "libcsound", "data", "getcsound.sh")


def sha256(path: str) -> str:
    hashsum = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hashsum.update(chunk)
    return hashsum.hexdigest()


def main() -> int:
    bundled = os.path.abspath(BUNDLED)
    if not os.path.exists(bundled):
        print(f"ERROR: bundled installer not found: {bundled}")
        return 1

    if len(sys.argv) > 1:
        upstream = sys.argv[1]
        if not os.path.exists(upstream):
            print(f"ERROR: upstream installer not found: {upstream}")
            return 1
        print(f"Comparing bundled installer with local file: {upstream}")
    else:
        upstream = None
        print(f"Downloading upstream installer from {UPSTREAM_URL}")
        req = urllib.request.Request(UPSTREAM_URL, headers={"User-Agent": "libcsound"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            upstream_data = resp.read()

    bundled_sha = sha256(bundled)
    if upstream is not None:
        upstream_sha = sha256(upstream)
    else:
        upstream_sha = hashlib.sha256(upstream_data).hexdigest()

    if bundled_sha == upstream_sha:
        print(f"OK: bundled installer matches upstream ({bundled_sha})")
        return 0

    print(f"ERROR: bundled installer is out of sync with the upstream installer\n"
          f"  bundled:  {bundled_sha}\n"
          f"  upstream: {upstream_sha}\n"
          f"Update it by copying the upstream file to {bundled}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
