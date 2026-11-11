#!/bin/zsh
# Agent sorties — lancement planifié
# Usage : run.sh alertes | quotidien | top10
set -u
MODE="${1:?mode requis : alertes | quotidien | top10}"
export PATH="$HOME/.local/bin:$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

S="$(cd "$(dirname "$0")/.." && pwd)"   # .../planout/agent-sorties
ROOT="$(dirname "$S")"                  # .../planout
LOG="$S/logs/$(date +%Y-%m).log"
mkdir -p "$S/logs" "$S/data/inbox"
cd "$ROOT" || exit 1
log() { echo "$(date '+%F %T') [$MODE] $*" >> "$LOG"; }

# Verrou : une seule exécution à la fois (attend jusqu'à 15 min)
LOCK="$S/data/.lock"
GOT=0
for i in {1..90}; do
  if mkdir "$LOCK" 2>/dev/null; then GOT=1; break; fi
  sleep 10
done
[[ $GOT == 1 ]] || { log "verrou occupé depuis 15 min, abandon (supprimer $LOCK si bloqué)"; exit 0; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

log "début"
if [[ ! -e "$S/preferences/sorties.json" ]]; then
  log "préférences introuvables (disque /Volumes/DEV monté ?), abandon"
  exit 1
fi

# 1. Recherche web par Claude (alertes et quotidien seulement)
if [[ "$MODE" == "alertes" || "$MODE" == "quotidien" ]]; then
  RAW="$S/data/inbox/$(date +%Y%m%d-%H%M)-$MODE.raw"
  PROMPT="$(cat "$S/prompts/$MODE.md")

Date et heure actuelles : $(date '+%Y-%m-%d %H:%M') (Europe/Paris)."
  # Claude ne fait que lire et chercher : sa réponse (le tableau JSON) est capturée ici
  claude -p "$PROMPT" --model sonnet --allowedTools "WebSearch" "WebFetch" "Read" \
    > "$RAW" 2>> "$LOG" || log "erreur claude (code $?)"
  log "réponse de Claude : $(wc -c < "$RAW" | tr -d ' ') octets → $(basename "$RAW")"
  python3 "$S/scripts/sorties.py" merge >> "$LOG" 2>&1
  # Publication dans PlanOut (fichiers data/ + git push vers GitHub Pages)
  python3 "$S/scripts/sorties.py" planout >> "$LOG" 2>&1 || log "erreur publication PlanOut"
fi

# 2. Notification Telegram
python3 "$S/scripts/sorties.py" "$MODE" >> "$LOG" 2>&1 || log "erreur notification"
log "fin"
