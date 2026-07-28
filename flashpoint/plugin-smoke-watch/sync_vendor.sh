#!/bin/bash
# Vendor the agent-side smoke-watch code into the build context (run before
# pluginctl build / ECR submission — Docker cannot COPY from outside the
# context). Sources of truth live in ../agent/; do not edit vendored/ here.
set -e
cd "$(dirname "$0")"
rm -rf vendored
mkdir vendored
cp ../agent/skills/holdover_smoke_watch.py \
   ../agent/skills/strike_sectors.py \
   ../agent/evidence.py \
   vendored/
printf '"""Vendored from flashpoint/agent by sync_vendor.sh - do not edit."""\n' \
  > vendored/__init__.py
echo "vendored $(ls vendored | wc -l) files ($(du -sh vendored | cut -f1))"
