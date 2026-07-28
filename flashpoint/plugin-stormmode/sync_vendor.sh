#!/bin/bash
# Vendor the controller and its cross-package deps into the build context
# (run before pluginctl build / ECR submission — Docker cannot COPY from
# outside the context). The tree MIRRORS the repo layout so the
# Path(__file__).parents[1] sibling lookups in controller code (agent/skills,
# scripts, detectors/data) resolve unchanged.
set -e
cd "$(dirname "$0")"
rm -rf controller agent scripts detectors
cp -r ../controller controller
rm -rf controller/tests controller/__pycache__
mkdir -p agent/skills scripts detectors/data
cp ../agent/skills/strike_sectors.py agent/skills/
cp ../scripts/xweather_lightning.py scripts/
cp ../detectors/data/kitten_glm.json detectors/data/
echo "vendored: controller/ agent/skills/strike_sectors.py scripts/xweather_lightning.py detectors/data/kitten_glm.json"
