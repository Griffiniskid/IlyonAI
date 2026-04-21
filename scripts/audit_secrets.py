"""Fails CI if any known-compromised secret appears in tracked files.

Blocks by SHA-256 of whole files (catches the old Moralis JWT wherever it
lands) and flags JWT-looking prefixes for manual review.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BLOCKED_SHA256 = {
    "bf7fff4fcc82c3ac243ba7bd3ebcac5318c7cbd5f605c7f8b1ed9ff956c9510c",
}

BLOCKED_PREFIXES = (
    "eyJhbGciOiJIUzI1NiIs",
)

ALLOW_PATH_SUBSTRINGS = (
    "test_fixtures",
    "scripts/audit_secrets.py",
    "docs/superpowers/plans/",
    "docs/superpowers/specs/",
)


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [Path(p) for p in out if p]


def main() -> int:
    bad: list[str] = []
    for path in tracked_files():
        if not path.is_file():
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        text = blob.decode("utf-8", errors="ignore")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        path_str = str(path)
        is_allowed = any(s in path_str for s in ALLOW_PATH_SUBSTRINGS)
        if digest in BLOCKED_SHA256 and not is_allowed:
            bad.append(f"{path}: blocklisted by content hash")
        for prefix in BLOCKED_PREFIXES:
            if prefix in text and not is_allowed:
                bad.append(f"{path}: contains suspected JWT prefix {prefix}")
    if bad:
        print("SECRET AUDIT FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 1
    print("secret audit: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
