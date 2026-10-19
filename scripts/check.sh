#!/usr/bin/env sh
set -eu
python scripts/tasks.py lint
python scripts/tasks.py test
npm run test:e2e
npm run test:visual
