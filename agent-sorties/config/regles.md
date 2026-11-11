# Règles — agent sorties (format PlanOut)

## Préférences : `agent-sorties/preferences/*.json`
Ce sont tes préférences d'origine (celles des commandes /sorties, /soirees, /sport), complétées,
versionnées dans le dépôt PlanOut.

| `cat` PlanOut | Fichier PlanOut | Préférences à appliquer |
|---|---|---|
| `concert` | `AAAA-MM-soirees-concert.json` | `preferences/soirees-concert.json` |
| `techno` | `AAAA-MM-soirees-techno.json` | `preferences/soirees.json` |
| `musee` | `AAAA-MM-sorties-musee.json` | `preferences/sorties.json` (sources `musee`) |
| `paris` | `AAAA-MM-sorties-paris.json` | `preferences/sorties.json` (sources `paris`, `cuisine`, `recherches_web`) |
| `spectacle` | `AAAA-MM-sorties-theatre.json` | `preferences/sorties-theatre.json` |
| `running` / `volley` | `AAAA-MM-sport-*.json` | `preferences/sport.json` |
| `autre` | `AAAA-MM-sorties-autre.json` | — |

Tags (changent l'emoji Telegram) : `street-art` 🎨 · `jeux` 🎲 · `cuisine` 🍽️ · `french-touch` 🤖 · `opera` 🎼,
et librement `gratuit`, `nocturne`, `guest-possible`, `insolite`…

## Score
Additionne les `ranking_weights` du fichier de préférences de la catégorie
(ex. soirées : `artiste_bouger_partout` +60, `artiste_favori` +40, `genre_prefere` +15…).
- Un artiste de `artistes_suggeres` compte comme `genre_prefere`.
- Un artiste de `artistes_collaborateurs` compte comme `artiste_favori` (+40) : guest possible
  de Thomas Bangalter / Guy-Manuel → tag `guest-possible` et mention dans `notes`.
- Un élément de `*_deja_vu*` → -100. Un sujet/genre/lieu rejeté → pénalité du fichier.
- **Score final PlanOut = borné entre 0 et 100.**
- `match_reasons` = les critères appliqués, au format `critere: valeur`
  (ex. `artiste_favori: Justice`, `lieu_prefere: Rex Club`, `budget_ok`).

## Urgence (`urgence`)
- `haute` → alerte Telegram immédiate :
  - un artiste de `artistes_bouger_partout` joue (même hors Paris, dans `rayon_km_pour_favoris`)
  - billetterie qui ouvre dans les 72 h (🔴 presale imminente) pour un événement de score ≥ 40
  - `presque_complet` / sold-out probable sur un événement de score ≥ 60
  - expo de score > 70 qui se termine dans moins de 2 semaines
- `moyenne` : billetterie qui ouvre plus tard (🟡) ou réservation obligatoire
- `basse` : déjà en vente sans tension (🟢), ou entrée libre

## Réservation (`reservation`)
- `statut` : `a_venir` (🟡, renseigner `ouverture` = AAAA-MM-JJTHH:MM) · `ouverte` (🟢) ·
  `presque_complet` · `complet` · `sans_resa`
- `url` : lien DIRECT de la page d'achat de CET événement (pas l'accueil du lieu)
- Pour le sport : `ouverture` = date limite d'inscription si elle est connue
- `deadline` (« Book by » de PlanOut) et `reminders` sont calculés automatiquement.

## Fiabilité — règle absolue
- **Jamais de date estimée, supposée ou « récurrente probable ».** Pas de date officielle = pas d'événement.
  Les artistes à surveiller sont dans les préférences : ils sont recherchés à chaque passage.
- Information inconnue = `null`. Toujours un `url` vers la page officielle consultée.
- Les événements contenant « date estimée » sont rejetés automatiquement.
