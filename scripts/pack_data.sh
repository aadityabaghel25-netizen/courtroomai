#!/bin/sh
# Pack the runtime data (search index, judgment texts, statute tables) into one archive
# for upload to the host's volume. Raw Indian Kanoon JSON is not needed at runtime.
set -e
cd "$(dirname "$0")/.."
mkdir -p dist
tar -czf dist/courtroomai-data.tgz -C data chroma_db judgments statutes/ipc_bns_map.csv statutes/sections.jsonl
ls -lh dist/courtroomai-data.tgz
