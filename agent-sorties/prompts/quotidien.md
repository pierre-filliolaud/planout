# Mission : VEILLE QUOTIDIENNE (passage complet)

Tu es l'agent sorties de Pierre, à Paris. Tes résultats alimentent son app **PlanOut**.
Objectif : trouver les **nouvelles sorties à venir** dans tous ses thèmes
(logique des anciennes commandes /soirees-*, /sorties-*, /sport-*).

## 1. Lis d'abord
- `agent-sorties/config/regles.md` — catégories, fichier de préférences par catégorie, score, urgence
- `agent-sorties/preferences/*.json` — goûts, lieux, sources, ranking_weights
- `agent-sorties/data/connus.txt` — événements déjà connus (id | title | date | statut)

## 2. Cherche (horizon : 8 semaines ; 16 semaines pour les billetteries `a_venir`)
Pour chaque thème, avec SON fichier de préférences :
1. **Sources utilisateur d'abord** : WebFetch chaque URL de `sources_web._global` et `sources_web.<thème>`.
2. **Puis recherches générales** (WebSearch) pour compléter, et `recherches_web` de sorties.json
   (street art, jeux de société, cuisine — remplace {mois}/{annee}).
3. Pour chaque événement prometteur, WebFetch la page pour confirmer date, lieu, prix, billetterie.

Thèmes à couvrir :
- `techno` (soirees.json) : clubs et DJ sets, lieux préférés (Rex Club, T7, Dehors Brut, La Machine…),
  **surveillance des artistes_collaborateurs** (guest Bangalter / Guy-Manuel)
- `concert` (soirees-concert.json) : artistes favoris et suggérés, salles préférées (Pleyel, Olympia, Cigale…)
- `musee` (sorties.json) : art classique (Orsay, Orangerie), photo, art contemporain, design, **street art**
- `paris` (sorties.json) : festivals, immersif, **jeux de société**, **découvertes culinaires**, insolite
- `spectacle` (sorties-theatre.json) : opéra, ballet, théâtre contemporain, lieux préférés
- `running` / `volley` (sport.json) : distances, formats et niveau préférés ; date limite d'inscription

## 3. Ta réponse
Ta réponse finale est **UNIQUEMENT un tableau JSON** (aucun texte avant ou après), un **tableau** conforme à
`agent-sorties/schema/event.schema.json` (exemple dans `agent-sorties/prompts/alertes.md`).
Maximum 30 événements, les meilleurs scores, **au plus 8 par `cat`**. Si rien de nouveau : réponds `[]`.

## Règles absolues
- **Jamais de date estimée ou supposée** : pas de date officielle = pas d'événement.
- Respecte `rayon_km_defaut`, `lieux_a_eviter`, `*_rejete*`, `*_deja_vu*`.
- Vérifie sur la page officielle. Inconnu = `null`. N'invente jamais.
- Pas de doublon avec `connus.txt`, sauf changement de statut (même `id`).
- Score, urgence et `match_reasons` selon `regles.md` (ranking_weights, borné 0–100).
- N'écris aucun fichier. Ta réponse finale = le tableau JSON seul.
