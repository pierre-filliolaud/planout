#!/bin/zsh
# Installation de l'agent sorties (dans le dépôt PlanOut)
# Usage : zsh /Volumes/DEV/github-projects/planout/agent-sorties/scripts/install.sh
set -e
S="$(cd "$(dirname "$0")/.." && pwd)"        # .../planout/agent-sorties
PLANOUT="$(dirname "$S")"                     # .../planout
ASSISTANT="$HOME/agents/assistant"            # dossier de la session Telegram
LA="$HOME/Library/LaunchAgents"

echo "→ Dossiers"
mkdir -p "$S"/{data/inbox,exports,rapports,logs} "$LA"
[[ -f "$S/data/events.json" ]] || echo "[]" > "$S/data/events.json"
chmod +x "$S/scripts/run.sh" "$S/scripts/sorties.py"

echo "→ Configuration Telegram"
if [[ ! -f "$S/config/telegram.env" ]]; then
  echo "CHAT_ID=A_REMPLACER" > "$S/config/telegram.env"
  echo "   ⚠️  Mets ton chat ID dans $S/config/telegram.env (demande-le à @userinfobot)"
fi

echo "→ Ancienne installation dans ~/agents/assistant (si présente)"
if [[ -d "$ASSISTANT/agent-sorties" && ! -L "$ASSISTANT/agent-sorties" ]]; then
  mv "$ASSISTANT/agent-sorties" "$ASSISTANT/agent-sorties.ancien-$(date +%Y%m%d%H%M)"
  echo "   déplacée dans $ASSISTANT/agent-sorties.ancien-… (tu pourras la supprimer)"
fi
for OLD in "$ASSISTANT/.claude/agents/sorties.md"; do
  [[ -f "$OLD" ]] && mv "$OLD" "$S/logs/$(basename "$OLD").bak" && echo "   ancien sous-agent sorties.md retiré"
done

echo "→ Sous-agent pour la session Telegram"
mkdir -p "$ASSISTANT/.claude/agents"
ln -sfn "$S/claude/agent-sorties.md" "$ASSISTANT/.claude/agents/agent-sorties.md"
echo "   ✓ $ASSISTANT/.claude/agents/agent-sorties.md → planout"
# autoriser la session Telegram à lire/modifier le dépôt PlanOut sans demande de permission
python3 - "$ASSISTANT/.claude/settings.local.json" "$PLANOUT" <<'PY'
import json, sys, os
f, d = sys.argv[1], sys.argv[2]
cfg = json.load(open(f)) if os.path.exists(f) else {}
dirs = cfg.setdefault("permissions", {}).setdefault("additionalDirectories", [])
dirs[:] = [x for x in dirs if not x.endswith("/preferences")]  # ancien réglage
if d not in dirs:
    dirs.append(d)
json.dump(cfg, open(f, "w"), indent=2)
print("   ✓ dépôt PlanOut autorisé dans .claude/settings.local.json")
PY

echo "→ Import des données PlanOut existantes"
if [[ ! -f "$S/data/.planout_importe" ]]; then
  python3 "$S/scripts/sorties.py" import-planout
else
  echo "   ✓ déjà importé"
fi

echo "→ Planification (launchd)"
[[ -f "$LA/com.pierre.veille-sorties.plist" ]] && { launchctl unload "$LA/com.pierre.veille-sorties.plist" 2>/dev/null || true; mv "$LA/com.pierre.veille-sorties.plist" "$S/logs/ancienne-veille.plist.bak"; }
for m in alertes quotidien top10; do
  P="com.pierre.sorties-$m.plist"
  launchctl unload "$LA/$P" 2>/dev/null || true
  sed "s#__RUN__#$S/scripts/run.sh#" "$S/launchd/$P" > "$LA/$P"
  launchctl load "$LA/$P"
  echo "   ✓ $m"
done

echo "→ Premier export"
python3 "$S/scripts/sorties.py" export

echo ""
echo "✅ Installé."
echo "   Test : zsh $S/scripts/run.sh quotidien"
echo "   Journal : tail -f $S/logs/\$(date +%Y-%m).log"
echo "   Pense à redémarrer la session Telegram : tmux kill-session -t assistant && ~/agents/start-assistant.sh"
