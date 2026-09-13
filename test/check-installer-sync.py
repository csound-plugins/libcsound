#!/usr/bin/env python3
"""Check that the bundled installers match the upstream getcsound scripts.

The libcsound package bundles copies of the csound installers
(libcsound/data/getcsound.sh and libcsound/data/getcsound.ps1) used to install
csound on macOS and Windows when it is not found. These copies must stay in
sync with the upstream files served at
https://csound-plugins.github.io/getcsound.{sh,ps1}.

Usage:
    python test/check-installer-sync.py [--sh PATH] [--ps1 PATH]

If PATH is given for a script, it is compared directly against the bundled
copy. Otherwise the upstream script is downloaded from
https://csound-plugins.github.io/ and compared. Exits with a non-zero status
if any of them differ.
"""
import argparse
import hashlib
import os
import sys
import urllib.request

INSTALLERS = {
    "sh": {
        "upstream": "https://csound-plugins.github.io/getcsound.sh",
        "bundled": os.path.join("libcsound", "data", "getcsound.sh"),
    },
    "ps1": {
        "upstream": "https://csound-plugins.github.io/getcsound.ps1",
        "bundled": os.path.join("libcsound", "data", "getcsound.ps1"),
    },
}


def sha256(path: str) -> str:
    hashsum = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hashsum.update(chunk)
    return hashsum.hexdigest()


def check(name: str, local: str | None) -> bool:
    bundled = os.path.join(os.path.dirname(__file__), os.pardir,
                           INSTALLERS[name]["bundled"])
    bundled = os.path.abspath(bundled)
    if not os.path.exists(bundled):
        print(f"ERROR: bundled installer not found: {bundled}")
        return False

    if local is not None:
        if not os.path.exists(local):
            print(f"ERROR: upstream installer not found: {local}")
            return False
        print(f"[{name}] Comparing bundled installer with local file: {local}")
        upstream_sha = sha256(local)
    else:
        url = INSTALLERS[name]["upstream"]
        print(f"[{name}] Downloading upstream installer from {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "libcsound"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            upstream_data = resp.read()
        upstream_sha = hashlib.sha256(upstream_data).hexdigest()

    bundled_sha = sha256(bundled)
    if bundled_sha == upstream_sha:
        print(f"[{name}] OK: bundled installer matches upstream ({bundled_sha})")
        return True

    print(f"[{name}] ERROR: bundled installer is out of sync with the upstream installer\n"
          f"  bundled:  {bundled_sha}\n"
          f"  upstream: {upstream_sha}\n"
          f"Update it by copying the upstream file to {bundled}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sh", metavar="PATH",
                        help="compare the bundled getcsound.sh against PATH "
                             "instead of downloading the upstream script")
    parser.add_argument("--ps1", metavar="PATH",
                        help="compare the bundled getcsound.ps1 against PATH "
                             "instead of downloading the upstream script")
    args = parser.parse_args()

    ok = True
    for name, local in (("sh", args.sh), ("ps1", args.ps1)):
        ok = check(name, local) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
