#!/usr/bin/env python3
"""Probe which Sage nodes your credentials can download protected files from.

For each node: find its most recent upload record (public metadata), then attempt an
authenticated ranged GET (first KB only — no full downloads). Reports an access map.

    SAGE_USER=scwatson SAGE_TOKEN=... python scripts/access_probe.py [VSN ...]
"""
import base64, os, sys, urllib.request
import sage_data_client

DEFAULT_NODES = [
    # Tier 1 — case studies & flagship
    "W06C", "W067", "W084", "W06F",
    # Camp dev arrays (samples: Loop, Argonne, South Side, UIC-area)
    "W026", "W02C", "W079", "W023", "W0A4", "W0B1", "W096", "W099", "W015", "W080", "W072",
    # Tier 3 — sentinels & regional
    "W070", "W02B", "W045", "W069", "W097",
]

def main(nodes):
    user, tok = os.environ.get("SAGE_USER"), os.environ.get("SAGE_TOKEN")
    if not (user and tok):
        sys.exit("Set SAGE_USER and SAGE_TOKEN first.")
    auth = "Basic " + base64.b64encode(f"{user}:{tok}".encode()).decode()
    print(f"{'node':<6} {'upload found':<26} access")
    ok, denied, quiet = [], [], []
    for vsn in nodes:
        url = None
        for window in ("-2d", "-14d"):
            try:
                df = sage_data_client.query(start=window, filter={"name": "upload", "vsn": vsn})
                if len(df):
                    row = df.sort_values("timestamp").iloc[-1]
                    url = row["value"]
                    stamp = str(row["timestamp"])[:16] + " " + str(row["meta.task"])[:12]
                    break
            except Exception:
                continue
        if not url:
            print(f"{vsn:<6} {'(no uploads <=14d)':<26} —"); quiet.append(vsn); continue
        req = urllib.request.Request(url, headers={"Authorization": auth,
                                                   "Range": "bytes=0-1023",
                                                   "User-Agent": "flashpoint-probe"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read(1024)
                print(f"{vsn:<6} {stamp:<26} OK ({r.status})"); ok.append(vsn)
        except urllib.error.HTTPError as e:
            print(f"{vsn:<6} {stamp:<26} DENIED ({e.code})"); denied.append(vsn)
        except Exception as e:
            print(f"{vsn:<6} {stamp:<26} ERROR {str(e)[:40]}")
    print(f"\ngranted ({len(ok)}): {', '.join(ok) or '-'}")
    print(f"denied  ({len(denied)}): {', '.join(denied) or '-'}")
    print(f"quiet   ({len(quiet)}): {', '.join(quiet) or '-'}  (no recent uploads to test — retry with older window)")

if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_NODES)
