#!/bin/sh
# On first start, if the data volume is empty and DATA_URL is set, download and unpack the
# data archive (made by scripts/pack_data.sh). Does nothing when data is already present.
set -e
DATA_DIR="${DATA_DIR:-/data}"
if [ -f "$DATA_DIR/judgments/judgments.jsonl" ] && [ -d "$DATA_DIR/chroma_db" ]; then
  echo "[data] present in $DATA_DIR"
  exit 0
fi
if [ -z "$DATA_URL" ]; then
  echo "[data] missing in $DATA_DIR and DATA_URL not set; the app will report status=degraded"
  exit 0
fi
mkdir -p "$DATA_DIR"
echo "[data] downloading archive"
python -c "import urllib.request,os; urllib.request.urlretrieve(os.environ['DATA_URL'], '/tmp/data.tgz')"
tar -xzf /tmp/data.tgz -C "$DATA_DIR"
rm -f /tmp/data.tgz
echo "[data] unpacked into $DATA_DIR"
