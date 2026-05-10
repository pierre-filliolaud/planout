# 🎟️ Paris Sortie Planner

Application mobile-first PWA pour gérer ses concerts, restaurants, voyages et spectacles à Paris.

## Features

- **Ajout manuel** d'événements avec catégorie, date, lieu, deadline de réservation et rappels
- **Import de fichiers** : `.ics` / iCal, `.csv`, `.json`, texte libre
- **Vue liste** triée par date avec filtres par catégorie
- **Indicateurs urgence** : rouge (< 14j), orange (< 45j), vert (OK)
- **Stats en temps réel** : total, à réserver, ce mois
- **PWA** : installable sur iPhone via Safari → "Ajouter à l'écran d'accueil"
- **Dark mode** natif, optimisé iOS

## Installation iPhone

1. Ouvrir `index.html` dans Safari (via serveur local ou GitHub Pages)
2. Partager → "Sur l'écran d'accueil"
3. L'app s'ouvre en plein écran comme une app native

## Formats d'import

### iCal (.ics)
Export standard depuis Ticketmaster, FNAC Spectacles, Google Calendar, etc.

### CSV
```
titre,date,categorie,lieu,notes
Coldplay,2026-07-15,concert,Stade de France,Réserver sur ticketmaster.fr
```

### JSON
```json
[
  {
    "title": "Coldplay",
    "date": "2026-07-15",
    "cat": "concert",
    "venue": "Stade de France",
    "notes": "Réserver sur ticketmaster.fr"
  }
]
```

## Stack

- HTML / CSS / Vanilla JS
- PWA (manifest + mobile meta)
- `localStorage` pour la persistance
- Zero dépendance, zero build step

## Lancer en local

```bash
npx serve .
# ou
python3 -m http.server 8080
```

Puis ouvrir `http://localhost:8080`
