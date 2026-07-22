#!/usr/bin/env python3
"""M1: download the Kitten Fire window media from W06C (and Selma images from W067).

Requires portal credentials (files are protected):
    SAGE_USER=scwatson SAGE_TOKEN=<access token>  python scripts/fetch_case_media.py

Downloads into data/<vsn>/<task>/ preserving timestamps in filenames.
Start with audio (779 clips ~ a few GB max); pass --limit for a smoke test.
"""
import base64, os, pathlib, sys, urllib.request
import sage_data_client

USER = os.environ.get("SAGE_USER", "")
TOKEN = os.environ.get("SAGE_TOKEN", "")
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0

JOBS = [
    # vsn, task regex, start, end
    ("W06C", "audio-sampler", "2025-07-01T00:00:00Z", "2025-07-04T00:00:00Z"),
    ("W06C", "imagesampler-.*|.*mobotix.*", "2025-07-02T18:00:00Z", "2025-07-03T23:59:00Z"),
    ("W067", "imagesampler-.*", "2025-07-06T00:00:00Z", "2025-07-09T00:00:00Z"),
]

def auth_opener():
    if not (USER and TOKEN):
        sys.exit("Set SAGE_USER and SAGE_TOKEN (portal access token) first.")
    tok = base64.b64encode(f"{USER}:{TOKEN}".encode()).decode()
    op = urllib.request.build_opener()
    op.addheaders = [("Authorization", "Basic " + tok), ("User-Agent", "flashpoint")]
    return op

def main():
    op = auth_opener()
    root = pathlib.Path(__file__).resolve().parent.parent / "data"
    for vsn, task, s, e in JOBS:
        df = sage_data_client.query(start=s, end=e, filter={"name": "upload", "vsn": vsn, "task": task})
        df = df.sort_values("timestamp")
        if LIMIT:
            df = df.head(LIMIT)
        print(f"{vsn} {task}: {len(df)} files")
        for _, row in df.iterrows():
            url = row["value"]
            tdir = root / vsn / row["meta.task"]
            tdir.mkdir(parents=True, exist_ok=True)
            dest = tdir / url.rsplit("/", 1)[-1]
            if dest.exists():
                continue
            try:
                with op.open(url, timeout=90) as r, open(dest, "wb") as f:
                    f.write(r.read())
            except Exception as ex:
                print("  FAIL", dest.name, str(ex)[:60])
        print(f"  -> {tdir if len(df) else 'nothing'}")

if __name__ == "__main__":
    main()
