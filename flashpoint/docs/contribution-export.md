# Camp knowledge contribution — exporting Claude Code sessions safely

The organizers accept session history/memory as the end-of-camp contribution
(in lieu of, or alongside, a `hermes-profile/` skill bundle). That knowledge
gets merged into the shared profile for future campers — so it lands in a
**public** place. These sessions contain live secrets (Sage token, the UIC
camera password, internal 10.107.x IPs, NIM/Slack keys). **Three scrub layers,
in order — never skip a layer:**

## 1. Export the raw sessions

In each Claude Code session: `/export` (writes a markdown transcript), or copy
the JSONL under `~/.claude/projects/<project>/`. Collect them into one folder,
e.g. `raw-sessions/`. Do this for every FlashPoint session worth sharing.

## 2. Deterministic scrub (`scripts/scrub_transcript.py`)

```bash
# put every LITERAL secret you know, one per line, in the gitignored file:
printf '%s\n' '<sage-token>' '<camera-password>' '<slack-webhook>' \
  '<nvidia-key>' > flashpoint/.scrub-secrets      # gitignored, never commit

python scripts/scrub_transcript.py raw-sessions/*.md raw-sessions/*.jsonl \
  -o scrubbed/
```

It redacts (a) every exact string from `.scrub-secrets`, and (b) pattern
classes — hex tokens, api keys, Bearer/Basic auth, Slack webhooks, RTSP
credentials, `?token=`/`password=` URL params, and known `KEY=value` env
secrets. It then **prints every remaining line that mentions a secret-ish word
but matched no pattern** — those need your eyes (step 3 catches the rest).
Output goes to `scrubbed/` (gitignored).

Verify it works before trusting it — the committed self-test:
`printf 'token 6094...\nrtsp://admin:pw@10.107.0.231/...\n' | ...` redacts both.

## 3. LLM proofread pass (contextual leaks patterns can't see)

Open the `scrubbed/` files in a FRESH Claude Code (or Hermes) session and run:

> Read every file in scrubbed/. This is a Claude Code session history that will
> be published to a PUBLIC repository as a camp knowledge contribution. Find
> anything that should NOT be public, that the automated scrubber missed:
> - any remaining credential, token, password, key, or webhook in any format
>   (including described in prose, e.g. "the password is X", partial secrets,
>   base64/hex blobs);
> - internal hostnames or IPs (10.107.x, 10.31.x, node LAN addresses),
>   SSH configs, private URLs, or camera stream paths with embedded auth;
> - personal data beyond the author's already-public name/email/Sage user;
> - anything a security reviewer would flag before a public push.
> For each: file, line, the exact text, why it's sensitive, and a suggested
> redaction. DO NOT modify files — output a findings list only; I will apply
> and re-run the deterministic scrubber. Be exhaustive; false positives are
> cheap, a leaked secret is not.

Apply its findings by adding any newly found literal secrets to
`.scrub-secrets` and re-running step 2, or editing the scrubbed copy directly.

## 4. Final human gate

`grep -riE 'password|token|secret|api.?key|webhook|10\.107|10\.31|ssh-rsa|BEGIN.*PRIVATE' scrubbed/`
should return only `[REDACTED:...]` hits. Skim the result yourself — you are
the last layer. Only then share `scrubbed/` with the organizers.

## Rotate afterward regardless

Assume anything that was ever in a session is compromised: **regenerate the
Sage portal token, and ask camp IT to rotate the UIC camera password**, after
contributing. Scrubbing reduces exposure; rotation ends it.

---

*Alternative/complement — the skill bundle:* the `controller` / `fusion` /
`risk` CLIs also make a clean `hermes-profile/` skill contribution (each is a
one-line `python -m ...` entrypoint with a `--help`). If you go that route,
wrap each as a profile skill, verify it loads in one Hermes session, and push
to `hermes-profile/` — no transcript export, no secrets to scrub. The session
export is richer (it carries the reasoning and dead-ends); the skill bundle is
safer (nothing sensitive by construction). Doing both is ideal.
