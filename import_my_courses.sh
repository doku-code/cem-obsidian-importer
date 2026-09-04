#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /chemin/vers/Vault/School/Cégep Édouard-Montpetit"
  exit 2
fi

ROOT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$SCRIPT_DIR/cem_to_obsidian.py"

import_course() {
  local repo="$1"
  local folder="$2"
  echo
  echo "==> $folder"
  python3 "$PY" "$repo" \
    -o "$ROOT/$folder" \
    --course-name "Notes de cours" \
    --copy-all-static \
    --force
}

import_course "https://github.com/departement-info-cem/3M5-Intro-Mobile.git" \
  "3M5 - Programmation Mobile"

import_course "https://github.com/departement-info-cem/3W6-Web-Transactionelle.git" \
  "3W6 - Programmation Web Transactionnelle"

import_course "https://github.com/departement-info-cem/4W6-WebServices.git" \
  "4W6 - Programmation Web Orienté Services"

echo
echo "✅ Les trois copies locales ont été reconstruites dans: $ROOT"
echo "   Chaque cours garde son dossier Notes de cours séparé de tes notes personnelles."
