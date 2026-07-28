#!/bin/bash
# Vendor the detectors package into the build context (run before pluginctl
# build / ECR submission — Docker cannot COPY from outside the context).
set -e
cd "$(dirname "$0")"
rm -rf detectors
cp -r ../detectors detectors
rm -rf detectors/tests detectors/data/eval_kitten_summary.json detectors/__pycache__
echo "vendored detectors/ ($(du -sh detectors | cut -f1))"
