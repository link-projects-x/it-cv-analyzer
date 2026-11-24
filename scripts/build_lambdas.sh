#!/usr/bin/env bash
# Build dist/scraper.zip, dist/parser.zip, dist/cv.zip, dist/indexer.zip and dist/api.zip for the Lambda python3.13
# arm64 runtime. dist/api.zip serves two functions: the matcher and the HTTP API.
# The salary model archive is built separately: ml/salary/package.sh -> dist/model.tar.gz.
# Dependencies are installed as manylinux aarch64 wheels, so the build works on macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
PIP=(python3 -m pip install --quiet --upgrade
     --platform manylinux2014_aarch64 --implementation cp --python-version 3.13
     --only-binary=:all:)

rm -rf "$BUILD" && mkdir -p "$BUILD" "$DIST"

# scraper: stdlib + boto3 from the Lambda runtime, no extra dependencies
mkdir -p "$BUILD/scraper"
cp -R "$ROOT/services/scraper/scraper" "$BUILD/scraper/"

# parser: dependencies + package + contracts copied to parser/contracts_data
mkdir -p "$BUILD/parser"
"${PIP[@]}" --target "$BUILD/parser" -r "$ROOT/services/parser/requirements.txt"
cp -R "$ROOT/services/parser/parser" "$BUILD/parser/"
mkdir -p "$BUILD/parser/parser/contracts_data"
cp "$ROOT"/contracts/*.json "$BUILD/parser/parser/contracts_data/"

# cv: same layout as parser, contracts copied to cv/contracts_data
mkdir -p "$BUILD/cv"
"${PIP[@]}" --target "$BUILD/cv" -r "$ROOT/services/cv/requirements.txt"
cp -R "$ROOT/services/cv/cv" "$BUILD/cv/"
mkdir -p "$BUILD/cv/cv/contracts_data"
cp "$ROOT"/contracts/*.json "$BUILD/cv/cv/contracts_data/"

# indexer and api: same layout, boto3 from the Lambda runtime
for fn in indexer api; do
  mkdir -p "$BUILD/$fn"
  "${PIP[@]}" --target "$BUILD/$fn" -r "$ROOT/services/$fn/requirements.txt"
  cp -R "$ROOT/services/$fn/$fn" "$BUILD/$fn/"
  mkdir -p "$BUILD/$fn/$fn/contracts_data"
  cp "$ROOT"/contracts/*.json "$BUILD/$fn/$fn/contracts_data/"
done

for fn in scraper parser cv indexer api; do
  find "$BUILD/$fn" -name "__pycache__" -type d -prune -exec rm -rf {} +
  rm -f "$DIST/$fn.zip"
  (cd "$BUILD/$fn" && zip -qr "$DIST/$fn.zip" .)
  echo "$DIST/$fn.zip $(du -h "$DIST/$fn.zip" | cut -f1)"
done
