#!/usr/bin/env bash
# Pasang (sekali) & jalankan RSSHub lokal di port 1200 tanpa Docker.
# Butuh: node >= 22, git, npm. Dipanggil otomatis oleh run_all.py bila RSSHUB_AUTOSTART=1.
set -u
cd "$(dirname "$0")"
DIR=rsshub
PORT="${RSSHUB_PORT:-1200}"

if ! command -v node >/dev/null 2>&1; then echo "[rsshub] node tidak ditemukan, dilewati"; exit 1; fi
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if [ "$NODE_MAJOR" -lt 22 ]; then echo "[rsshub] butuh node >= 22 (ada: $(node -v)), dilewati"; exit 1; fi

PNPM="npx --yes pnpm@10"

if [ ! -f "$DIR/dist/index.mjs" ]; then
  echo "[rsshub] instalasi pertama (beberapa menit)..."
  [ -d "$DIR/.git" ] || git clone --depth 1 https://github.com/DIYgod/RSSHub.git "$DIR" || exit 1
  cd "$DIR" || exit 1
  $PNPM install --frozen-lockfile || exit 1
  $PNPM build || exit 1
  cd ..
fi

cd "$DIR" || exit 1
echo "[rsshub] start di port $PORT"
NODE_ENV=production PORT="$PORT" CACHE_TYPE=memory CACHE_EXPIRE=300 exec node dist/index.mjs
