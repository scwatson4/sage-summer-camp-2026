#!/usr/bin/env python3
"""Scrub secrets from Claude Code session exports before sharing them
(e.g., as the camp knowledge contribution — that repo is PUBLIC).

Two layers, use BOTH:
1. THIS SCRIPT — deterministic: exact known secrets (from a local,
   gitignored .scrub-secrets file) + pattern classes (hex tokens, api keys,
   webhook URLs, basic-auth, rtsp credentials, KEY=value env lines). Never
   put real secrets in this file or anywhere committed.
2. An LLM proofread pass afterward for contextual leaks the patterns can't
   see (see docs/contribution-export.md for the prompt).

Usage:
  python scripts/scrub_transcript.py session1.md session2.jsonl ... -o scrubbed/
  # exact secrets file (one string per line, gitignored):
  #   flashpoint/.scrub-secrets

Output: scrubbed copies + a report of what was redacted and lines that
still LOOK sensitive and need human eyes.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

PATTERNS = [
    # order matters: most specific first
    ("slack-webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+")),
    ("rtsp-credential", re.compile(r"rtsps?://[^/\s:@]+:[^/\s@]+@")),
    ("basic-auth", re.compile(r"(Authorization:\s*Basic\s+)[A-Za-z0-9+/=]+", re.I)),
    ("bearer", re.compile(r"(Bearer\s+)[A-Za-z0-9._-]{20,}")),
    ("api-key-ish", re.compile(r"\b(sk|nvapi|xai|ghp|gho|glpat)[-_][A-Za-z0-9_-]{16,}\b")),
    ("hex-token", re.compile(r"\b[0-9a-f]{32,64}\b")),
    ("env-secret", re.compile(
        r"^(\s*(?:export\s+)?(?:SAGE_TOKEN|SLACK_WEBHOOK_URL|XWEATHER_CLIENT_SECRET|"
        r"XWEATHER_CLIENT_ID|EDL_TOKEN|NVIDIA_API_KEY|NRP_LLM_API_KEY|"
        r"OPENROUTER_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY)\s*=\s*)\S+",
        re.M)),
    ("url-token-param", re.compile(r"([?&](?:token|api_key|apikey|client_secret|password)=)[^&\s\"']+", re.I)),
    ("password-assign", re.compile(r"((?:password|passwd|pwd)\s*[:=]\s*)['\"]?[^\s'\",;]+", re.I)),
]

# lines that survive scrubbing but deserve human review
SUSPICIOUS = re.compile(
    r"password|secret|token|credential|api[_ ]?key|webhook|ssh-rsa|BEGIN [A-Z ]*PRIVATE KEY",
    re.I)


def load_exact_secrets():
    f = ROOT / ".scrub-secrets"
    if not f.exists():
        return []
    vals = [ln.strip() for ln in f.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    # longest first so substrings don't shadow
    return sorted(set(vals), key=len, reverse=True)


def scrub_text(text, exact):
    counts = {}
    for s in exact:
        n = text.count(s)
        if n:
            counts["exact-secret"] = counts.get("exact-secret", 0) + n
            text = text.replace(s, "[REDACTED:exact]")
    for name, rx in PATTERNS:
        def sub(m):
            counts[name] = counts.get(name, 0) + 1
            keep = m.group(1) if m.groups() else ""
            return f"{keep}[REDACTED:{name}]"
        text = rx.sub(sub, text)
    return text, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--outdir", default="scrubbed")
    args = ap.parse_args()

    exact = load_exact_secrets()
    if not exact:
        print("NOTE: no flashpoint/.scrub-secrets file — only pattern-based "
              "scrubbing will run. Add your literal token/password strings "
              "there (it is gitignored) for guaranteed removal.\n",
              file=sys.stderr)
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    grand = {}
    review = []
    for f in args.files:
        p = pathlib.Path(f)
        text = p.read_text(errors="replace")
        scrubbed, counts = scrub_text(text, exact)
        (outdir / p.name).write_text(scrubbed)
        for k, v in counts.items():
            grand[k] = grand.get(k, 0) + v
        for i, line in enumerate(scrubbed.splitlines(), 1):
            if SUSPICIOUS.search(line) and "[REDACTED" not in line:
                review.append(f"{p.name}:{i}: {line.strip()[:120]}")

    print(f"scrubbed {len(args.files)} file(s) -> {outdir}/")
    print("redactions:", grand or "none")
    if review:
        print(f"\n{len(review)} line(s) mention secret-ish words but matched "
              "no pattern — HUMAN REVIEW REQUIRED:")
        for r in review[:60]:
            print("  " + r)
        if len(review) > 60:
            print(f"  ... and {len(review) - 60} more")
    print("\nNext: run the LLM proofread pass (docs/contribution-export.md) "
          "before sharing anything.")


if __name__ == "__main__":
    main()
