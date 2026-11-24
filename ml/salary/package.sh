#!/usr/bin/env bash
# Build dist/model.tar.gz for the SageMaker scikit-learn 1.9-0 inference container (see README.md -> SageMaker).
#
#   ml/salary/package.sh [model_dir]      model_dir defaults to ml/salary/model (written by train.py)
#
# Layout inside the archive (SageMaker extracts it to /opt/ml/model):
#   salary-model.joblib, metadata.json    read by inference.model_fn("/opt/ml/model")
#   code/inference.py, code/features.py   SAGEMAKER_PROGRAM=inference.py, SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code
#   code/requirements.txt                 installed by the container before importing inference.py
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MODEL_DIR="${1:-$HERE/model}"
ARTIFACT="salary-model.joblib"
STAGE="$ROOT/build/salary"
OUT="$ROOT/dist/model.tar.gz"

if [[ ! -f "$MODEL_DIR/$ARTIFACT" || ! -f "$MODEL_DIR/metadata.json" ]]; then
  echo "no $ARTIFACT and metadata.json in $MODEL_DIR; run ml/salary/train.py first" >&2
  exit 1
fi

# A joblib file from another scikit-learn version may not load in the container, so refuse to package one.
pinned="$(sed -n 's/^scikit-learn==//p' "$HERE/requirements.txt")"
trained="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["sklearn_version"])' "$MODEL_DIR/metadata.json")"
if [[ "$pinned" != "$trained" ]]; then
  echo "model trained with scikit-learn $trained, requirements.txt pins $pinned; retrain in a matching venv" >&2
  exit 1
fi

rm -rf "$STAGE" && mkdir -p "$STAGE/code" "$(dirname "$OUT")"
cp "$MODEL_DIR/$ARTIFACT" "$MODEL_DIR/metadata.json" "$STAGE/"
cp "$HERE/inference.py" "$HERE/features.py" "$HERE/requirements.txt" "$STAGE/code/"

# COPYFILE_DISABLE keeps macOS tar from adding ._* metadata files
(cd "$STAGE" && COPYFILE_DISABLE=1 tar -czf "$OUT" "$ARTIFACT" metadata.json code)
echo "$OUT $(du -h "$OUT" | cut -f1) (scikit-learn $trained)"
tar -tzf "$OUT"
