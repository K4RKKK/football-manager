#!/usr/bin/env bash
# Test de bout en bout : service Python réel + client C# du plugin, sur une carrière SYNTHÉTIQUE.
# Prérequis : uv, dotnet (SDK 8). Usage : scripts/e2e_plugin_backend.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
export CLUBDIRECTOR_HOME="$TMP/home"
export CLUBDIRECTOR_SAVE_DIRS="$TMP/games"
export CLUBDIRECTOR_E2E_PORT="${CLUBDIRECTOR_E2E_PORT:-18765}"
mkdir -p "$CLUBDIRECTOR_SAVE_DIRS"
cp "$ROOT/backend/tests/fixtures/saves/synthetic-career-scored.fm" "$CLUBDIRECTOR_SAVE_DIRS/"

cd "$ROOT/backend"
uv run clubdirector sync "$CLUBDIRECTOR_SAVE_DIRS/synthetic-career-scored.fm" >/dev/null
uv run clubdirector serve --port "$CLUBDIRECTOR_E2E_PORT" >"$TMP/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; rm -rf "$TMP"' EXIT
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$CLUBDIRECTOR_E2E_PORT/api/health" >/dev/null && break
  sleep 0.2
done
cd "$ROOT/plugin"
dotnet test tests/ClubDirector.Core.Tests --filter "FullyQualifiedName~EndToEnd" --logger "console;verbosity=normal"
