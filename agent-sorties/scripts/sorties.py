#!/usr/bin/env python3
"""Agent sorties — base d'événements au format PlanOut, publication, Telegram, top 10.

Usage :
  python3 sorties.py import-planout   # 1re fois : importe les fichiers existants de PlanOut
  python3 sorties.py merge            # intègre data/inbox/*.json dans data/events.json
  python3 sorties.py planout          # écrit PlanOut/data/*.json + index.json, commit et push
  python3 sorties.py export           # exports locaux (JSON, CSV, ICS) + connus.txt
  python3 sorties.py alertes          # Telegram : événements urgents pas encore alertés
  python3 sorties.py quotidien        # Telegram : nouveautés, cette semaine, billetteries
  python3 sorties.py top10            # Telegram : top 10 de la semaine (+ archive)
  python3 sorties.py stats            # résumé de la base
  python3 sorties.py purge-estimes    # supprime les événements à « date estimée »

Variables : SORTIES_DRY_RUN=1 (affiche au lieu d'envoyer / pousser)
Aucune dépendance : Python 3.9+ standard.
"""
import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # pas de __pycache__ dans le dépôt PlanOut

BASE = Path(__file__).resolve().parent.parent  # .../planout/agent-sorties
PLANOUT_DEFAUT = BASE.parent                    # .../planout
DATA = BASE / "data"
INBOX = DATA / "inbox"
DB = DATA / "events.json"
IMPORT_FLAG = DATA / ".planout_importe"
EXPORTS = BASE / "exports"
RAPPORTS = BASE / "rapports"
TG_ENV = Path.home() / ".claude/channels/telegram/.env"
CFG_TG = BASE / "config/telegram.env"
CFG_PLANOUT = BASE / "config/planout.env"
DRY = bool(os.environ.get("SORTIES_DRY_RUN"))

# Thèmes PlanOut : catégorie -> (emoji, suffixe du fichier PlanOut)
CATS = {
    "concert":   ("🎤", "soirees-concert"),
    "techno":    ("🎧", "soirees-techno"),
    "musee":     ("🖼️", "sorties-musee"),
    "spectacle": ("🎭", "sorties-theatre"),
    "paris":     ("✨", "sorties-paris"),
    "running":   ("🏃", "sport-running"),
    "volley":    ("🏐", "sport-volley"),
    "autre":     ("📌", "sorties-autre"),
}
FILE_TO_CAT = {suffix: cat for cat, (_, suffix) in CATS.items()}
CAT_ALIASES = {"expo": "musee", "exposition": "musee", "musée": "musee", "street-art": "musee",
               "theatre": "spectacle", "théâtre": "spectacle", "opera": "spectacle", "opéra": "spectacle",
               "ballet": "spectacle", "danse": "spectacle", "show": "spectacle",
               "electro": "techno", "club": "techno", "dj": "techno",
               "jeux": "paris", "cuisine": "paris", "food": "paris", "decouverte": "paris",
               "festival": "paris", "marché": "paris", "salon": "paris"}
TAG_EMOJI = {"street-art": "🎨", "jeux": "🎲", "cuisine": "🍽️", "french-touch": "🤖", "opera": "🎼"}
URGENCES = ["haute", "moyenne", "basse"]
STATUTS = {"a_venir": "billetterie pas encore ouverte", "ouverte": "réservation ouverte",
           "presque_complet": "presque complet !", "complet": "complet", "sans_resa": "sans réservation"}
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
REQUIRED = ["title", "cat", "date", "venue"]
MAX_PAR_CAT_TOP10 = 3
PLANOUT_KEYS = ["id", "title", "date", "date_fin", "time", "cat", "venue", "notes", "reminders",
                "deadline", "score", "source", "match_reasons", "image_url", "added",
                "tags", "urgence", "reservation", "prix", "url"]


# ---------- utilitaires ----------
def today():
    return date.today()


def now_iso():
    return datetime.now().isoformat(timespec="minutes")


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:90]


def make_id(e):
    return slug(f'{e["date"]}-{e["title"]}')


def parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def start_date(e):
    return parse_date(e.get("date"))


def end_date(e):
    return parse_date(e.get("date_fin")) or start_date(e)


def is_past(e):
    d = end_date(e)
    return d is not None and d < today()


def resa(e):
    return e.get("reservation") or {}


def is_estime(e):
    return bool(e.get("estime")) or "date-estimee" in (e.get("tags") or [])


def emoji(e):
    for t in e.get("tags") or []:
        if t in TAG_EMOJI:
            return TAG_EMOJI[t]
    return CATS.get(e.get("cat"), CATS["autre"])[0]


def domain(url):
    try:
        return urllib.parse.urlparse(url).hostname.removeprefix("www.")
    except Exception:
        return ""


def read_env(*paths):
    env = {}
    for p in paths:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, val = line.split("=", 1)
                    env[k.strip()] = os.path.expanduser(val.strip().strip("\"'"))
    return env


def load_db():
    if not DB.exists():
        return []
    events = json.loads(DB.read_text(encoding="utf-8") or "[]")
    for e in events:
        e.setdefault("notifie", {})
        e["notifie"].setdefault("alerte", None)
        e["notifie"].setdefault("quotidien", None)
        e["notifie"].setdefault("top10", [])
    return events


def save_db(events):
    DATA.mkdir(parents=True, exist_ok=True)
    events = sorted(events, key=lambda e: (e["date"], e["title"]))
    tmp = DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB)


def upcoming(events, avec_estimes=False):
    return [e for e in events if not is_past(e) and (avec_estimes or not is_estime(e))]


# ---------- normalisation ----------
def normalize_cat(cat, file_theme=None):
    if file_theme in CATS:
        return file_theme
    c = str(cat or "").lower().strip()
    c = CAT_ALIASES.get(c, c)
    return c if c in CATS else "autre"


def normalize(e, known_ids, file_theme=None):
    # compatibilité : anciens noms de champs
    for old, new in (("titre", "title"), ("date_debut", "date"), ("heure", "time"),
                     ("lieu", "venue"), ("categorie", "cat"), ("description", "notes")):
        if old in e and new not in e:
            e[new] = e.pop(old)
    if isinstance(e.get("venue"), dict):
        v = e["venue"]
        e["venue"] = ", ".join(x for x in [v.get("nom"), v.get("arrondissement")] if x)
    missing = [k for k in REQUIRED if not e.get(k)]
    if missing:
        raise ValueError(f"champs manquants : {missing}")
    if not parse_date(e["date"]):
        raise ValueError(f"date invalide : {e['date']}")
    e["date"] = str(e["date"])[:10]
    e["date_fin"] = str(e["date_fin"])[:10] if parse_date(e.get("date_fin")) else None
    if e.get("time") and not re.match(r"^[0-2]\d:[0-5]\d$", str(e["time"])):
        e["time"] = None
    e["cat"] = normalize_cat(e.get("cat"), file_theme)
    if e.get("urgence") not in URGENCES:
        e["urgence"] = "basse"
    try:
        e["score"] = max(0, min(100, int(e.get("score", 50))))
    except (TypeError, ValueError):
        e["score"] = 50
    e["tags"] = [slug(t) for t in e.get("tags") or [] if t]
    e["match_reasons"] = list(e.get("match_reasons") or [])
    r = dict(e.get("reservation") or {})
    r.setdefault("requise", bool(e.get("deadline")))
    if r.get("statut") not in STATUTS:
        r["statut"] = "ouverte" if r["requise"] else "sans_resa"
    e["reservation"] = r
    if e.get("url") and not e.get("source"):
        e["source"] = domain(e["url"])
    if "date estim" in (e.get("notes") or "").lower() or "(date estim" in e["title"].lower():
        e["estime"] = True
        if "date-estimee" not in e["tags"]:
            e["tags"].append("date-estimee")
    for k in ("notifie", "passe"):
        e.pop(k, None)
    if not (e.get("id") and e["id"] in known_ids):
        e["id"] = make_id(e)
    return e


def upsert(db, e, notifie_par_defaut=None):
    """Ajoute ou met à jour un événement. Retourne 'ajout' ou 'maj'."""
    if e["id"] in db:
        old = db[e["id"]]
        keep = {k: old[k] for k in ("added", "notifie") if k in old}
        for k, val in e.items():
            if val is None or val == [] or val == "":
                continue
            if isinstance(val, dict) and isinstance(old.get(k), dict):
                old[k].update({sk: sv for sk, sv in val.items() if sv is not None})
            else:
                old[k] = val
        old.update(keep)
        old["mis_a_jour_le"] = now_iso()
        return "maj"
    e.setdefault("added", now_iso())
    e["mis_a_jour_le"] = now_iso()
    e["notifie"] = notifie_par_defaut or {"alerte": None, "quotidien": None, "top10": []}
    db[e["id"]] = e
    return "ajout"


# ---------- import / merge ----------
def planout_dir():
    env = read_env(CFG_PLANOUT)
    d = os.environ.get("PLANOUT_DIR") or env.get("PLANOUT_DIR")
    return (Path(d) if d else PLANOUT_DEFAUT), env


def cmd_import_planout():
    pdir, _ = planout_dir()
    if not pdir or not (pdir / "data").is_dir():
        sys.exit(f"[!] Dossier PlanOut introuvable : {pdir} (voir config/planout.env)")
    db = {e["id"]: e for e in load_db()}
    deja = {"alerte": "import", "quotidien": "import", "top10": []}  # pas de spam Telegram
    stats = {"ajout": 0, "maj": 0, "ignorés": 0, "estimés": 0}
    for f in sorted((pdir / "data").glob("20??-??-*.json")):
        theme = FILE_TO_CAT.get(f.stem[8:])
        for raw in json.loads(f.read_text(encoding="utf-8") or "[]"):
            try:
                e = normalize(dict(raw), db.keys(), theme)
            except ValueError:
                stats["ignorés"] += 1
                continue
            stats["estimés"] += is_estime(e)
            stats[upsert(db, e, dict(deja))] += 1
    save_db(list(db.values()))
    IMPORT_FLAG.write_text(now_iso())
    print(f"import PlanOut : {stats['ajout']} ajoutés, {stats['maj']} mis à jour, "
          f"{stats['ignorés']} ignorés, dont {stats['estimés']} à date estimée")
    cmd_export()


def cmd_merge():
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / "traites").mkdir(exist_ok=True)
    (INBOX / "erreurs").mkdir(exist_ok=True)
    db = {e["id"]: e for e in load_db()}
    stats = {"ajout": 0, "maj": 0, "ignorés": 0}
    for f in sorted(INBOX.glob("*.json")):
        try:
            items = json.loads(f.read_text(encoding="utf-8") or "[]")
            if isinstance(items, dict):
                items = items.get("events", [])
            for raw in items:
                try:
                    e = normalize(dict(raw), db.keys())
                except ValueError as err:
                    stats["ignorés"] += 1
                    print(f"[ignoré] {raw.get('title', '?')} : {err}", file=sys.stderr)
                    continue
                if is_estime(e):  # règle : jamais de date inventée
                    stats["ignorés"] += 1
                    print(f"[ignoré] {e['title']} : date estimée", file=sys.stderr)
                    continue
                stats[upsert(db, e)] += 1
            f.rename(INBOX / "traites" / f.name)
        except Exception as err:
            print(f"[erreur] {f.name} : {err}", file=sys.stderr)
            f.rename(INBOX / "erreurs" / f.name)
    save_db(list(db.values()))
    print(f"merge : {stats['ajout']} ajoutés, {stats['maj']} mis à jour, {stats['ignorés']} ignorés")
    cmd_export()


def cmd_purge_estimes():
    db = load_db()
    garde = [e for e in db if not is_estime(e)]
    save_db(garde)
    print(f"purge : {len(db) - len(garde)} événements à date estimée supprimés")
    cmd_export()


# ---------- format PlanOut ----------
def deadline_for(e):
    """Date limite de réservation (« Book by » dans PlanOut)."""
    if e.get("deadline"):
        return e["deadline"]
    r = resa(e)
    st = r.get("statut")
    debut, fin, t = start_date(e), end_date(e), today()
    if st == "a_venir" and parse_date(r.get("ouverture")):
        return str(parse_date(r["ouverture"]))
    if st == "presque_complet" or (st == "ouverte" and e.get("urgence") == "haute"):
        d = max(t, min(debut - timedelta(days=1), (parse_date(e.get("added")) or t) + timedelta(days=2)))
        return str(min(d, fin))
    if st == "ouverte" and r.get("requise"):
        return str(min(max(t, fin - timedelta(days=7)), fin))
    return None


def prix_txt(e):
    p = e.get("prix") or {}
    if p.get("gratuit"):
        return "gratuit"
    if p.get("min") is not None:
        if p.get("max") not in (None, p["min"]):
            return f"{p['min']:g}–{p['max']:g} €"
        return f"{p['min']:g} €"
    return ""


def to_planout(e):
    r = resa(e)
    lines = [e.get("notes") or ""]
    infos = []
    if prix_txt(e):
        infos.append(f"💶 {prix_txt(e)}")
    if r.get("requise") or r.get("statut") not in (None, "sans_resa"):
        st = STATUTS.get(r.get("statut"), "")
        if r.get("statut") == "a_venir" and r.get("ouverture"):
            st += f" — ouverture le {str(r['ouverture']).replace('T', ' à ')}"
        infos.append(f"🎟️ {st}")
    if infos:
        lines.append(" · ".join(infos))
    notes_urls = set(re.findall(r"https?://\S+", e.get("notes") or ""))
    for u in (r.get("url"), e.get("url")):
        if u and u not in notes_urls:
            lines.append(u)  # PlanOut affiche en lien une ligne qui est une URL
            notes_urls.add(u)
    out = {
        "id": e["id"], "title": e["title"], "date": e["date"], "date_fin": e.get("date_fin"),
        "time": e.get("time"), "cat": e["cat"], "venue": e["venue"],
        "notes": "\n".join(x for x in lines if x).strip(),
        "reminders": e.get("reminders") or (["2w", "1w"] if r.get("requise") else ["1w", "1d"]),
        "deadline": deadline_for(e), "score": e["score"],
        "source": e.get("source") or domain(e.get("url") or ""),
        "match_reasons": e.get("match_reasons") or [], "image_url": e.get("image_url"),
        "added": e.get("added"), "tags": e.get("tags") or [], "urgence": e.get("urgence"),
        "reservation": r or None, "prix": e.get("prix"), "url": e.get("url"),
    }
    return {k: out[k] for k in PLANOUT_KEYS}


def build_index(pdir):
    """Réutilise build_index() de PlanOut/serve.py pour rester 100 % compatible."""
    try:
        spec = importlib.util.spec_from_file_location("planout_serve", pdir / "serve.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.build_index()
    except Exception as err:
        print(f"[!] serve.py non utilisable ({err}), index simplifié", file=sys.stderr)
        files = sorted(f.name for f in (pdir / "data").glob("20??-??-*.json"))
        return {"files": [{"file": f, "label": f[:7], "theme": FILE_TO_CAT.get(f[8:-5], "autre"),
                           "month": f[:7]} for f in files]}


def git(pdir, *args, check=True):
    return subprocess.run(["git", "-C", str(pdir), *args], capture_output=True, text=True, check=check)


def cmd_planout():
    pdir, env = planout_dir()
    if not pdir or not (pdir / "data").is_dir():
        print(f"[!] PlanOut introuvable ({pdir}) : disque /Volumes/DEV monté ? Publication ignorée.")
        return
    if not IMPORT_FLAG.exists():
        sys.exit("[!] Lance d'abord : python3 sorties.py import-planout (sinon les données existantes seraient écrasées)")
    push = env.get("PLANOUT_GIT_PUSH", "1") == "1" and not DRY
    if push and (pdir / ".git").exists():
        r = git(pdir, "pull", "--rebase", "--autostash", check=False)
        if r.returncode != 0:
            print(f"[!] git pull : {r.stderr.strip()}", file=sys.stderr)

    # regrouper par mois de début + thème
    fichiers = {}
    for e in load_db():
        nom = f'{e["date"][:7]}-{CATS.get(e["cat"], CATS["autre"])[1]}.json'
        fichiers.setdefault(nom, []).append(to_planout(e))
    data_dir = pdir / "data"
    ecrits = 0
    for nom, evs in sorted(fichiers.items()):
        evs.sort(key=lambda x: (-x["score"], x["date"]))
        contenu = json.dumps(evs, ensure_ascii=False, indent=2) + "\n"
        f = data_dir / nom
        if not f.exists() or f.read_text(encoding="utf-8") != contenu:
            if not DRY:
                f.write_text(contenu, encoding="utf-8")
            ecrits += 1
    # fichiers devenus vides (ex. après purge)
    for f in data_dir.glob("20??-??-*.json"):
        if f.name not in fichiers and f.stem[8:] in FILE_TO_CAT and not DRY:
            f.unlink()
            ecrits += 1
    if not DRY:
        (data_dir / "index.json").write_text(
            json.dumps(build_index(pdir), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"planout : {len(fichiers)} fichiers, {ecrits} modifiés → {data_dir}")

    if push and (pdir / ".git").exists():
        rel = BASE.relative_to(pdir) if BASE.is_relative_to(pdir) else None
        a_versionner = ["data"] + ([f"{rel}/data/events.json", f"{rel}/rapports"] if rel else [])
        git(pdir, "add", *a_versionner)
        if git(pdir, "diff", "--cached", "--quiet", check=False).returncode != 0:
            git(pdir, "commit", "-m", f"agent-sorties : mise à jour {now_iso()}")
            r = git(pdir, "push", check=False)
            print("planout : publié sur GitHub" if r.returncode == 0 else f"[!] git push : {r.stderr.strip()}")
        else:
            print("planout : rien à publier")


# ---------- exports locaux ----------
def v(x):
    return "" if x is None else x


def ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def write_ics(events):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pierre//Agent Sorties//FR",
           "CALSCALE:GREGORIAN", "X-WR-CALNAME:Sorties Paris", "X-WR-TIMEZONE:Europe/Paris"]
    for e in events:
        if is_past(e) or is_estime(e):
            continue
        d, fin = start_date(e), end_date(e)
        out += ["BEGIN:VEVENT", f"UID:{e['id']}@agent-sorties", f"DTSTAMP:{stamp}"]
        if e.get("time") and fin == d:
            start = datetime.combine(d, datetime.strptime(e["time"], "%H:%M").time())
            out += [f"DTSTART;TZID=Europe/Paris:{start:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID=Europe/Paris:{start + timedelta(hours=2):%Y%m%dT%H%M%S}"]
        else:
            out += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{fin + timedelta(days=1):%Y%m%d}"]
        p = to_planout(e)
        out += [f"SUMMARY:{ics_text(emoji(e) + ' ' + e['title'])}", f"LOCATION:{ics_text(e['venue'])}",
                f"DESCRIPTION:{ics_text(p['notes'])}", f"CATEGORIES:{e['cat']}"]
        if e.get("url"):
            out.append(f"URL:{e['url']}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    (EXPORTS / "events.ics").write_text("\r\n".join(out) + "\r\n", encoding="utf-8")


def cmd_export():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    db = load_db()
    events = [to_planout(e) | {"passe": is_past(e), "estime": is_estime(e)} for e in db]
    (EXPORTS / "events.json").write_text(json.dumps(
        {"genere_le": datetime.now().isoformat(timespec="seconds"), "nombre": len(events), "events": events},
        ensure_ascii=False, indent=2), encoding="utf-8")
    cols = ["id", "title", "cat", "tags", "date", "date_fin", "time", "venue", "prix", "resa_statut",
            "ouverture", "deadline", "urgence", "score", "url", "passe", "estime"]
    with open(EXPORTS / "events.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(cols)
        for e, p in zip(db, events):
            w.writerow([e["id"], e["title"], e["cat"], ",".join(e.get("tags") or []), e["date"],
                        v(e.get("date_fin")), v(e.get("time")), e["venue"], prix_txt(e),
                        v(resa(e).get("statut")), v(resa(e).get("ouverture")), v(p["deadline"]),
                        e["urgence"], e["score"], v(e.get("url")), p["passe"], p["estime"]])
    write_ics(db)
    (DATA / "connus.txt").write_text("\n".join(
        f'{e["id"]} | {e["title"]} | {e["date"]} | {resa(e).get("statut", "")}'
        for e in upcoming(db, avec_estimes=True)) + "\n", encoding="utf-8")
    print(f"export : {len(db)} événements ({len(upcoming(db))} à venir, hors dates estimées)")


# ---------- Telegram ----------
def send(text):
    env = read_env(TG_ENV, CFG_TG)
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("CHAT_ID") or env.get("CHAT_ID")
    url_app = read_env(CFG_PLANOUT).get("PLANOUT_URL")
    if url_app and not text.startswith("🚨"):
        text += f"\n\n📱 PlanOut : {url_app}"
    if DRY or not token or not chat or chat == "A_REMPLACER":
        print(text)
        if not DRY:
            print("[!] TELEGRAM_BOT_TOKEN ou CHAT_ID manquant : message non envoyé", file=sys.stderr)
        return DRY
    chunks, cur = [], ""
    for block in text.split("\n\n"):
        block = block[:3900]
        if cur and len(cur) + len(block) + 2 > 3900:
            chunks.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + block
    if cur:
        chunks.append(cur)
    for c in chunks:
        data = urllib.parse.urlencode({"chat_id": chat, "text": c, "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30)
    return True


def fmt(e, numero=None, court=False):
    r = resa(e)
    d, fin = start_date(e), end_date(e)
    if fin != d:
        quand = f"jusqu'au {fin:%d/%m}" if d <= today() else f"du {d:%d/%m} au {fin:%d/%m}"
    else:
        quand = f"{JOURS[d.weekday()]} {d:%d/%m}"
    if e.get("time"):
        quand += f" {e['time']}"
    ligne2 = f"📅 {quand} · 📍 {e['venue']}"
    if prix_txt(e):
        ligne2 += f" · 💶 {prix_txt(e)}"
    lines = [f"{f'{numero}. ' if numero else ''}{emoji(e)} {e['title']}", ligne2]
    if r.get("requise"):
        st = STATUTS.get(r.get("statut"), "")
        if r.get("statut") == "a_venir" and r.get("ouverture"):
            st += f" — ouverture le {str(r['ouverture']).replace('T', ' à ')}"
        lines.append(f"🎟️ {st}")
    if not court and e.get("notes"):
        lines.append(re.sub(r"\s*https?://\S+", "", e["notes"]).strip()[:300])
    url = r.get("url") or e.get("url")
    if url:
        lines.append(f"🔗 {url}")
    return "\n".join(lines)


def cmd_alertes():
    db = load_db()
    todo = [e for e in upcoming(db) if e["urgence"] == "haute" and not e["notifie"]["alerte"]
            and resa(e).get("statut") != "complet"]
    if not todo:
        print("alertes : rien à envoyer")
        return
    todo.sort(key=lambda e: -e["score"])
    if send("🚨 À RÉSERVER VITE\n\n" + "\n\n".join(fmt(e) for e in todo)):
        for e in todo:
            e["notifie"]["alerte"] = now_iso()
        save_db(db)
        print(f"alertes : {len(todo)} envoyées")


def cmd_quotidien():
    db = load_db()
    up, t = upcoming(db), today()
    nouveaux = sorted([e for e in up if not e["notifie"]["quotidien"] and not e["notifie"]["alerte"]],
                      key=lambda e: -e["score"])
    montres = {e["id"] for e in nouveaux[:8]}
    semaine = sorted([e for e in up if start_date(e) <= t + timedelta(days=7) and e["score"] >= 60
                      and e["id"] not in montres and resa(e).get("statut") != "complet"],
                     key=lambda e: -e["score"])[:5]
    billetteries = sorted([e for e in up if resa(e).get("statut") == "a_venir"
                           and parse_date(resa(e).get("ouverture"))
                           and t <= parse_date(resa(e)["ouverture"]) <= t + timedelta(days=14)],
                          key=lambda e: str(resa(e)["ouverture"]))
    if not (nouveaux or semaine or billetteries):
        print("quotidien : rien à envoyer")
        return
    parts = [f"☀️ Sorties — {JOURS[t.weekday()]} {t:%d/%m}"]
    if nouveaux:
        parts.append(f"🆕 NOUVEAUTÉS ({len(nouveaux)})")
        parts += [fmt(e, court=True) for e in nouveaux[:8]]
        if len(nouveaux) > 8:
            parts.append(f"… et {len(nouveaux) - 8} autres dans PlanOut.")
    if semaine:
        parts.append("📆 CETTE SEMAINE")
        parts += [fmt(e, court=True) for e in semaine]
    if billetteries:
        parts.append("⏳ BILLETTERIES QUI OUVRENT BIENTÔT")
        parts += [f"• {str(resa(e)['ouverture']).replace('T', ' à ')} — {e['title']}" for e in billetteries]
    if send("\n\n".join(parts)):
        for e in nouveaux:
            e["notifie"]["quotidien"] = now_iso()
        save_db(db)
        print(f"quotidien : {len(nouveaux)} nouveautés envoyées")


def cmd_top10():
    db = load_db()
    t = today()
    lundi = t - timedelta(days=t.weekday())
    dimanche = lundi + timedelta(days=6)
    iso = t.isocalendar()
    semaine_id = f"{iso[0]}-S{iso[1]:02d}"
    fenetre = sorted([e for e in upcoming(db) if start_date(e) <= t + timedelta(days=14)
                      and resa(e).get("statut") != "complet"], key=lambda e: (-e["score"], e["date"]))
    top, par_cat = [], {}
    for e in fenetre:
        if par_cat.get(e["cat"], 0) >= MAX_PAR_CAT_TOP10:
            continue
        top.append(e)
        par_cat[e["cat"]] = par_cat.get(e["cat"], 0) + 1
        if len(top) == 10:
            break
    anticiper = sorted([e for e in upcoming(db) if resa(e).get("statut") == "a_venir" and e["score"] >= 60],
                       key=lambda e: str(resa(e).get("ouverture") or "9999"))[:5]
    stats = {}
    for e in upcoming(db):
        stats[e["cat"]] = stats.get(e["cat"], 0) + 1

    parts = [f"🏆 TOP 10 DE LA SEMAINE — {lundi:%d/%m} → {dimanche:%d/%m}"]
    parts += [fmt(e, numero=i) for i, e in enumerate(top, 1)] or ["Rien dans les 14 prochains jours."]
    if anticiper:
        parts.append("📌 À ANTICIPER (billetteries à venir)")
        parts += [f"• {e['title']} ({e['date']}) — ouverture "
                  f"{str(resa(e).get('ouverture') or 'date inconnue').replace('T', ' à ')}" for e in anticiper]
    parts.append("📊 À venir : " + " · ".join(f"{CATS[c][0]} {n}" for c, n in
                                              sorted(stats.items(), key=lambda x: -x[1])))
    msg = "\n\n".join(parts)
    RAPPORTS.mkdir(parents=True, exist_ok=True)
    (RAPPORTS / f"top10-{semaine_id}.md").write_text(msg + "\n", encoding="utf-8")
    (RAPPORTS / f"top10-{semaine_id}.json").write_text(json.dumps(
        {"semaine": semaine_id, "du": str(lundi), "au": str(dimanche), "top10": [to_planout(e) for e in top]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    if send(msg):
        for e in top:
            if semaine_id not in e["notifie"]["top10"]:
                e["notifie"]["top10"].append(semaine_id)
        save_db(db)
        print(f"top10 : {len(top)} événements ({semaine_id})")


def cmd_stats():
    db = load_db()
    up = upcoming(db)
    print(f"{len(db)} événements, {len(up)} à venir (+ {len(upcoming(db, True)) - len(up)} à date estimée)")
    for c, (emo, _) in CATS.items():
        n = sum(1 for e in up if e["cat"] == c)
        if n:
            print(f"  {emo} {c:<10} {n}")
    print(f"  urgents non alertés : {sum(1 for e in up if e['urgence'] == 'haute' and not e['notifie']['alerte'])}")
    print(f"  import PlanOut fait : {'oui' if IMPORT_FLAG.exists() else 'NON'}")


COMMANDS = {"import-planout": cmd_import_planout, "merge": cmd_merge, "planout": cmd_planout,
            "export": cmd_export, "alertes": cmd_alertes, "quotidien": cmd_quotidien,
            "top10": cmd_top10, "stats": cmd_stats, "purge-estimes": cmd_purge_estimes}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
