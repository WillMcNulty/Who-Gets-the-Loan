"""Download the raw files into data/raw/ (not committed), resuming where a download stopped, and record each file's
size and SHA-256 in data/manifest.json (committed), so a later run can tell if a publisher changed a file.

    python -m hmda.fetch                 # every year
    python -m hmda.fetch 2004 2018       # some years
"""

import hashlib
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from . import sources

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.json"
UA = {"User-Agent": "Who-Gets-the-Loan research (github.com/WillMcNulty/Who-Gets-the-Loan)"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, tries=5):
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, tries + 1):
        have = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers={**UA, **({"Range": f"bytes={have}-"} if have else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if have and r.status != 206:  # server ignored the range: start over
                    have = 0
                total = expected_size(r, have)
                with open(part, "ab" if have else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
            got = part.stat().st_size
            if total is not None and got != total:  # the connection ended early: resume on the next attempt
                raise IOError(f"got {got:,} of {total:,} bytes")
            if dest.suffix == ".zip" and not zipfile.is_zipfile(part):
                part.unlink()
                raise IOError("not a valid zip; starting over")
            part.replace(dest)
            return
        except Exception as e:  # network hiccup: wait and resume
            print(f"  {dest.name}: attempt {attempt} failed ({e}); retrying", flush=True)
            time.sleep(5 * attempt)
    raise SystemExit(f"could not download {url}")


def expected_size(r, have):
    """Full file size from Content-Range (resumed) or Content-Length (fresh); None when the server doesn't say."""
    cr = r.headers.get("Content-Range")
    if cr and "/" in cr and cr.rsplit("/", 1)[1].isdigit():
        return int(cr.rsplit("/", 1)[1])
    cl = r.headers.get("Content-Length")
    return have + int(cl) if cl and cl.isdigit() else None


def load_manifest():
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def fetch(years):
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    for y in years:
        url, name, publisher = sources.source(y)
        dest = RAW / name
        if not dest.exists():
            print(f"{y}: downloading {name}", flush=True)
            download(url, dest)
        entry = {"year": y, "file": name, "url": url, "publisher": publisher, "bytes": dest.stat().st_size,
                 "sha256": sha256(dest)}
        old = manifest.get(str(y))
        if old and old["sha256"] != entry["sha256"]:
            print(f"{y}: NOTE the file differs from the one recorded on {old.get('fetched')}")
        entry["fetched"] = old["fetched"] if old and old["sha256"] == entry["sha256"] else time.strftime("%Y-%m-%d")
        manifest[str(y)] = entry
        MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n")
        print(f"{y}: {entry['bytes']:,} bytes  {entry['sha256'][:12]}", flush=True)


if __name__ == "__main__":
    ys = [int(a) for a in sys.argv[1:]] or list(range(sources.FIRST_YEAR, sources.LAST_YEAR + 1))
    fetch(ys)
