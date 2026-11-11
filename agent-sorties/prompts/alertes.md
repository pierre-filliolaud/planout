# Mission : ALERTES — préventes et urgences (passage rapide)

Tu es l'agent sorties de Pierre, à Paris. Tes résultats alimentent son app **PlanOut**.
Objectif : repérer ce qu'il faut **réserver vite** (logique de l'ancienne commande /sorties-presales).

## 1. Lis d'abord
- `agent-sorties/config/regles.md` — catégories, score, urgence, format
- `agent-sorties/preferences/*.json` — artistes, lieux, sources, ranking_weights
- `agent-sorties/data/connus.txt` — événements déjà connus (id | title | date | statut)

## 2. Cherche, dans cet ordre
1. **Artistes `artistes_bouger_partout`** (Thomas Bangalter, Guy-Manuel de Homem-Christo) :
   toute date annoncée, jusqu'à `rayon_km_pour_favoris`. Recherches : `"<artiste>" live 2026`, `"<artiste>" guest`.
2. **`artistes_collaborateurs`** : dates officielles annoncées à Paris (guest possible → tag `guest-possible`).
3. **`artistes_favoris`** : `"<artiste>" Paris "on sale" OR "mise en vente" OR presale`.
4. **Plateformes de billetterie** (WebFetch) : dice.fm, shotgun.live/fr/paris, ra.co/events/fr/paris,
   fnacspectacles.com, ticketmaster.fr → annonces et mises en vente à venir.
5. **Lieux préférés institutionnels** (Opéra, Comédie-Française, Philharmonie, Olympia…) : ouvertures de billetterie.
6. Expos de score > 70 qui **se terminent dans moins de 2 semaines**.
7. Événements déjà connus dont le **statut de réservation a changé** → réutilise le même `id`.

Horizon : billetteries qui ouvrent dans les 16 prochaines semaines.

## 3. Écris le résultat
Crée le fichier JSON indiqué en fin de message : un **tableau** d'événements conforme à
`agent-sorties/schema/event.schema.json`. Maximum 10. Si rien : écris `[]`.

```json
{
  "title": "Justice — Hyperdrama Tour",
  "cat": "concert",
  "tags": ["french-touch", "guest-possible"],
  "date": "2027-03-14", "date_fin": null, "time": "20:00",
  "venue": "Accor Arena, Paris 12e",
  "notes": "Seule date parisienne. Guest possible de Thomas Bangalter (déjà vu sur scène avec Justice).",
  "prix": {"min": 49, "max": 89, "gratuit": false},
  "reservation": {"requise": true, "statut": "a_venir",
                  "ouverture": "2026-11-15T10:00", "url": "https://..."},
  "urgence": "haute", "score": 100,
  "match_reasons": ["artiste_favori: Justice", "artiste_collaborateur: Justice (guest Bangalter possible)",
                    "genre_prefere: french touch", "lieu_emblematique: Accor Arena"],
  "url": "https://page-officielle...", "source": "justice.com"
}
```

## Règles absolues
- **Jamais de date estimée ou supposée** : pas de date officielle = pas d'événement.
- Paris + rayon des préférences (sauf artistes_bouger_partout), événements à venir uniquement.
- Vérifie sur la page officielle. Inconnu = `null`. N'invente jamais.
- Pas de doublon avec `connus.txt`, sauf changement de statut (même `id`).
- N'écris rien d'autre que ce fichier. Réponse finale : une ligne de résumé.
