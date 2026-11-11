# Agent sorties — intégré à PlanOut

Veille automatique des sorties à Paris selon les préférences de Pierre. L'agent alimente
l'app PlanOut (`../data/`, publiée sur GitHub Pages) et envoie sur Telegram : alertes de
réservation, digest quotidien, top 10 du lundi.

## Organisation

```
planout/                         ← dépôt GitHub (GitHub Pages)
├── index.html, serve.py…        l'app PlanOut
├── data/                        ← GÉNÉRÉ par l'agent : AAAA-MM-<thème>.json + index.json
└── agent-sorties/
    ├── preferences/             ← TES PRÉFÉRENCES (ex-commandes /sorties, /soirees, /sport)
    │   ├── soirees.json           techno / clubs
    │   ├── soirees-concert.json   concerts live
    │   ├── sorties.json           expos, Paris, street art, jeux, cuisine
    │   ├── sorties-theatre.json   théâtre, opéra, ballet
    │   └── sport.json             running, volley
    ├── config/
    │   ├── regles.md              thèmes PlanOut, score (ranking_weights), urgence
    │   ├── planout.env            push auto, URL de l'app
    │   └── telegram.env           ton CHAT_ID (non versionné)
    ├── prompts/                   missions de Claude : alertes, quotidien
    ├── schema/event.schema.json   format d'un événement (PlanOut étendu)
    ├── claude/agent-sorties.md    sous-agent (lié dans ~/agents/assistant/.claude/agents/)
    ├── data/events.json           base de référence (versionnée)
    ├── rapports/                  top 10 hebdomadaires (versionnés)
    ├── scripts/                   install.sh, run.sh, sorties.py
    ├── launchd/                   planifications macOS
    └── logs/, exports/, data/inbox/   fichiers de travail (non versionnés)
```

## Fonctionnement

```
launchd → agent-sorties/scripts/run.sh MODE
   ├─ claude -p (lit preferences/ + regles.md + connus.txt, cherche, écrit data/inbox/*.json)
   ├─ sorties.py merge    → agent-sorties/data/events.json (anti-doublon, mises à jour)
   ├─ sorties.py planout  → planout/data/*.json + index.json → git commit + push
   └─ sorties.py MODE     → Telegram (seulement ce qui n'a pas déjà été envoyé)
```

| Quand | Mode | Telegram |
|---|---|---|
| 8h13, 11h13, 14h13, 17h13, 20h13 | `alertes` | 🚨 préventes < 72 h, artiste « à suivre partout », presque complet, expo qui se termine |
| Tous les jours 7h47 | `quotidien` | ☀️ nouveautés + cette semaine + billetteries à venir |
| Lundi 8h37 | `top10` | 🏆 top 10 des 14 prochains jours |

## Installation

```bash
zsh /Volumes/DEV/github-projects/planout/agent-sorties/scripts/install.sh
```

## Commandes

```bash
cd /Volumes/DEV/github-projects/planout
python3 agent-sorties/scripts/sorties.py stats            # état de la base
zsh agent-sorties/scripts/run.sh quotidien                # lancer un passage maintenant
python3 agent-sorties/scripts/sorties.py planout          # republier PlanOut
SORTIES_DRY_RUN=1 python3 agent-sorties/scripts/sorties.py top10   # aperçu sans envoi
python3 agent-sorties/scripts/sorties.py purge-estimes    # supprimer les anciennes « dates estimées »
tail -f agent-sorties/logs/$(date +%Y-%m).log
```

Depuis Telegram : « ajoute Air à mes artistes favoris », « j'ai vu l'expo X »,
« quelles expos à réserver ce mois-ci ? ».

## À savoir

- Les fichiers `planout/data/20*.json` sont **générés** depuis `agent-sorties/data/events.json` :
  ne les modifie plus à la main. Pour ajouter un événement : un JSON dans `data/inbox/`,
  puis `sorties.py merge && sorties.py planout`.
- **Jamais de date estimée** : les anciennes sont exclues des notifications
  (`purge-estimes` pour les retirer de l'app).
- ⚠️ GitHub Pages publie tout le dépôt : `agent-sorties/preferences/` et `data/events.json`
  sont donc visibles publiquement. Les secrets (`telegram.env`, journaux) ne sont jamais versionnés.

## Amélioration conseillée dans PlanOut (index.html)

`loadDataFile()` n'ajoute que les nouveaux événements : une mise à jour (statut, deadline)
n'apparaît qu'après « ↺ Reload all data ». Pour l'appliquer automatiquement, remplacer :

```js
      const existing = events.find(x => x.title === e.title && x.date === e.date);
      if (existing) {
        if (existing.cat !== e.cat) { existing.cat = e.cat; fixed++; }
      } else {
```

par :

```js
      const existing = events.find(x => (e.id && x.id === e.id) || (x.title === e.title && x.date === e.date));
      if (existing) {
        const before = JSON.stringify(existing);
        Object.assign(existing, e, { id: existing.id, added: existing.added });
        if (JSON.stringify(existing) !== before) fixed++;
      } else {
```
