#!/usr/bin/env python3
"""
extract_races.py - Liste les races d'un client (ex. Esteria) et extrait chaque race
dans son propre dossier : 03-Races/<id>-<nom>/

Pour chaque race on garde :
  - DBFilesClient/*.dbc  : DBC filtrées (uniquement les lignes de cette race)
  - les modèles (.m2/.skin/textures du dossier du modèle) et textures référencées
  - Portraits/*.png      : portraits autonomes (source Esteria-Interface)
  - race.json            : IDs liés (display, modèles, extra...) + fichiers manquants

Usage (depuis D:\\repo\\reforge-allies) :
    python extract_races.py --list                 # liste seulement
    python extract_races.py                        # extrait toutes les races
    python extract_races.py --only 12,24,25        # certaines races
    python extract_races.py --exclude-standard     # ignore les 10 races de base
    python extract_races.py --fallback 02-HD-Clean\\patch-X.mpq   # autre racine pour trouver des fichiers
    python extract_races.py --portraits-only       # complète les extractions sans toucher aux DBC/modèles
"""
import argparse
import json
import re
import shutil
import struct
import sys
from pathlib import Path

from execution_log import run_logged
from race_assets import HIGH_ELF_EYE_TEXTURES, model_dependencies, model_path, player_rows
from race_images import TC_RE, crop_frac, load_blp

HIGH_ELF_ASSETS = Path(__file__).resolve().parent / "Assets"
STANDARD = {1, 2, 3, 4, 5, 6, 7, 8, 10, 11}
FACTION = {0: "Alliance", 1: "Horde", 2: "Neutre"}
NATIVE_PORTRAITS = {
    "HUMAN": (0, 0), "DWARF": (1, 0), "GNOME": (2, 0), "NIGHTELF": (3, 0), "DRAENEI": (4, 0),
    "TAUREN": (0, 1), "UNDEAD": (1, 1), "SCOURGE": (1, 1), "TROLL": (2, 1), "ORC": (3, 1),
    "BLOODELF": (4, 1),
    "WORGEN": (5, 0), "GOBLIN": (5, 1),
}

# (type, argument) : "col" = champ 4 octets n° arg == id de race
#                    "byte" = octet à l'offset arg == id de race
#                    "mask" = champ 4 octets n° arg = masque de races
SPECS = {
    "ChrRaces": ("col", 0),
    "CharBaseInfo": ("byte", 0),
    "CharStartOutfit": ("byte", 4),
    "SkillLineAbility": ("mask", 3),
    "SkillRaceClassInfo": ("mask", 2),
    "CharSections": ("col", 1),
    "CharacterFacialHairStyles": ("col", 0),
    "CharHairGeosets": ("col", 1),
}
# dérivées (filtrées via les IDs trouvés ci-dessus)
DERIVED = ["CreatureDisplayInfo", "CreatureDisplayInfoExtra", "CreatureModelData"]


def norm(p):
    return str(p).replace("\\", "/").strip("/").lower()


class Dbc:
    def __init__(self, path):
        self.path = Path(path)
        d = self.path.read_bytes()
        if len(d) < 20 or d[:4] != b"WDBC":
            raise ValueError(f"{path}: pas un WDBC")
        self.rc, self.fc, self.rs, self.ss = struct.unpack_from("<4I", d, 4)
        if self.rs == 0 or 20 + self.rc * self.rs + self.ss > len(d):
            raise ValueError(f"{path}: fichier DBC invalide ou tronqué")
        self.recs = [d[20 + i * self.rs: 20 + (i + 1) * self.rs] for i in range(self.rc)]
        sb = 20 + self.rc * self.rs
        self.strings = d[sb: sb + self.ss]

    def u32(self, rec, col):
        o = col * 4
        return struct.unpack_from("<I", rec, o)[0] if o + 4 <= len(rec) else 0

    def string(self, rec, col):
        off = self.u32(rec, col)
        if off == 0:
            return ""
        if off >= len(self.strings):
            raise ValueError(f"{self.path}: offset de chaîne hors limites : {off}")
        end = self.strings.find(b"\0", off)
        if end < 0:
            raise ValueError(f"{self.path}: chaîne non terminée à l'offset {off}")
        return self.strings[off:end].decode("utf-8", "replace")

    def write(self, path, recs):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"WDBC" + struct.pack("<4I", len(recs), self.fc, self.rs, self.ss))
            f.write(b"".join(recs))
            f.write(self.strings)


def matches(db, rec, spec, rid):
    kind, arg = spec
    if kind == "col":
        return db.u32(rec, arg) == rid
    if kind == "byte":
        return len(rec) > arg and rec[arg] == rid
    m = db.u32(rec, arg)
    return m not in (0, 0xFFFFFFFF) and ((m >> (rid - 1)) & 1) == 1


class Roots:
    """Index insensible à la casse des fichiers de plusieurs racines (la 1re gagne)."""
    def __init__(self, roots):
        self.idx = {}
        self.dirs = {}
        for r in reversed(roots):  # la 1re racine écrase les suivantes
            for f in r.rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(r)).replace("\\", "/")
                    k = rel.lower()
                    self.idx[k] = (rel, f)
        for k, (rel, f) in self.idx.items():
            self.dirs.setdefault(k.rsplit("/", 1)[0] if "/" in k else "", []).append(k)

    def find(self, rel):
        return self.idx.get(norm(rel))

    def sibling_files(self, reldir):
        return [self.idx[k] for k in self.dirs.get(norm(reldir), [])]


class Portraits:
    def __init__(self, root):
        if not root.is_dir():
            raise FileNotFoundError(f"source des portraits introuvable : {root} (--portraits-src)")
        self.root = root
        self.roots = Roots([root])
        self.icons, self.gender_icons, self.coords = {}, {}, {}
        self.atlases = {}
        for rel in ("Interface/SharedXML/SharedConstants.lua", "Interface/GlueXML/CharacterCreate.lua"):
            hit = self.roots.find(rel)
            if not hit:
                continue
            text = hit[1].read_text(encoding="utf-8-sig")
            table = re.search(r'\bRACE_ICON_TCOORDS\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}', text)
            if table:
                self.coords.update({k.upper(): tuple(float(v) for v in values)
                                    for k, *values in TC_RE.findall(table[1])})
        lua = self.roots.find("Interface/GlueXML/CharacterCreate.lua")
        if lua:
            text = lua[1].read_text(encoding="utf-8-sig")
            assignments = re.compile(
                r'CHAR_CREATE_(EXTRA_RACE_ICONS|COA_GENDER_ICONS)'
                r'(?:\s*=\s*\{([^}]+)\}|\s*\["([^"]+)"\]\s*=\s*"([^"]+)")')
            for match in assignments.finditer(text):
                table, body, key, value = match.groups()
                entries = re.findall(r'\["([^"]+)"\]\s*=\s*"([^"]+)"', body) if body else [(key, value)]
                target = self.icons if table == "EXTRA_RACE_ICONS" else self.gender_icons
                for key, value in entries:
                    target[key.upper()] = value.replace("\\\\", "/")

    def find_icon(self, candidates):
        for candidate in candidates:
            if not candidate:
                continue
            if not Path(candidate).suffix:
                candidate += ".blp"
            hit = self.roots.find(candidate)
            if hit:
                return hit
        return None

    def flat_portrait(self, race_key, gender, faction):
        suffixes = [""] + ([f"_{faction.lower()}"] if faction else [])
        for suffix in suffixes:
            prefix = f"Charactercreate-races_{race_key}-{gender}"
            exact = self.roots.find(f"{prefix}{suffix}.png")
            if exact:
                return exact
            pattern = re.compile(re.escape(prefix) + r"\d+" + re.escape(suffix) + r"\.png", re.I)
            matches = [hit for hit in self.roots.sibling_files("") if pattern.fullmatch(hit[0])]
            if len(matches) > 1:
                raise ValueError(f"{race_key} ({gender}): portraits ambigus : "
                                 + ", ".join(hit[0] for hit in matches))
            if matches:
                return matches[0]
        return None

    def extract(self, race, out):
        token = race["client_file"].upper()
        name = race["name"]
        race_key = re.sub(r"[^A-Za-z0-9]", "", name).upper()
        token_key = re.sub(r"[^A-Za-z0-9]", "", token).upper()
        # A custom race can share a native model token, but not that race's portrait.
        if token_key in NATIVE_PORTRAITS and race_key not in NATIVE_PORTRAITS:
            token = race_key
        names = list(dict.fromkeys((re.sub(r"[^A-Za-z0-9]", "", name), token)))
        dedicated_dir = f"Interface/Glues/CharacterCreate/Portraits/{race_key}"
        dedicated = {g: self.flat_portrait(race_key, g, race.get("faction", ""))
                     for g in ("male", "female")}
        if not any(dedicated.values()):
            dedicated = {g: self.roots.find(f"{dedicated_dir}/{g}.png") for g in ("male", "female")}
        hd_images = {}
        if any(dedicated.values()):
            for gender, hit in dedicated.items():
                if not hit:
                    raise FileNotFoundError(f"{name}: paire HD incomplète, portrait {gender} "
                                            f"introuvable dans {self.root}")
                image = load_blp(hit[1])
                if min(image.size) < 128:
                    raise ValueError(f"{hit[1]}: portrait HD trop petit ({image.width}x{image.height}), "
                                     "128x128 minimum ; ne pas agrandir une icône LD")
                if not image.getchannel("A").getbbox():
                    raise ValueError(f"{hit[1]}: portrait HD vide")
                hd_images[gender] = image
            male, female = hd_images["male"], hd_images["female"]
            if male.size == female.size and male.tobytes() == female.tobytes():
                raise ValueError(f"{name}: les portraits HD male et female sont identiques")
        portraits, missing = {}, []
        for gender in ("male", "female"):
            key = f"{token}_{gender.upper()}"
            candidates = [self.gender_icons.get(key, "")]
            for n in names:
                candidates += [f"Interface/Icons/CoA_Race_{n}_{gender}.blp",
                               f"Interface/Glues/CharacterCreate/UI-CharacterCreate-{n}{gender}.blp"]
            shared_candidates = [self.icons.get(name.upper(), ""),
                                 f"Interface/Icons/CoA_Race_{names[0]}.blp"]
            hit = dedicated[gender] or self.find_icon(candidates)
            coords = None
            shared = False
            if hit:
                image = hd_images[gender] if dedicated[gender] else load_blp(hit[1])
            else:
                if race_key == re.sub(r"[^A-Za-z0-9]", "", token).upper():
                    coords = self.coords.get(key)
                if coords is None and race_key in NATIVE_PORTRAITS:
                    col, row = NATIVE_PORTRAITS[race_key]
                    row += 2 if gender == "female" else 0
                    coords = (col / 8, (col + 1) / 8, row / 4, (row + 1) / 4)
            if not hit and coords is not None:
                if not (0 <= coords[0] < coords[1] <= 1 and 0 <= coords[2] < coords[3] <= 1):
                    raise ValueError(f"{name} ({gender}): coordonnées de portrait invalides : {coords}")
                atlas_names = ["UI-CharacterCreate-Races.blp", "UI-CharacterCreate-RacesRound.blp"]
                # The WotLK _Round atlas has only ten races; edge bleed in column six is not a portrait.
                if key in self.coords or race_key not in ("GOBLIN", "WORGEN"):
                    atlas_names.insert(0, "UI-CharacterCreate-Races_Round.blp")
                for atlas_name in atlas_names:
                    atlas_hit = self.roots.find(f"Interface/Glues/CharacterCreate/{atlas_name}")
                    if not atlas_hit:
                        continue
                    if atlas_hit[0] not in self.atlases:
                        self.atlases[atlas_hit[0]] = load_blp(atlas_hit[1])
                    image = crop_frac(self.atlases[atlas_hit[0]], *coords)
                    if gender == "female" and race_key in ("GOBLIN", "WORGEN"):
                        col, row = NATIVE_PORTRAITS[race_key]
                        male_coords = self.coords.get(f"{token}_MALE",
                                                      (col / 8, (col + 1) / 8, row / 4, (row + 1) / 4))
                        male = crop_frac(self.atlases[atlas_hit[0]], *male_coords)
                        if image.size == male.size and image.tobytes() == male.tobytes():
                            print(f"[warn] {name} (female) : {atlas_hit[0]} duplique le portrait male ; cellule ignorée")
                            continue
                    if image.getchannel("A").getbbox():
                        hit = atlas_hit
                        break
            if not hit:
                coords = None
                hit = self.find_icon(shared_candidates)
                if hit:
                    image = load_blp(hit[1])
                    shared = True
                    print(f"[warn] {name} ({gender}) : portrait commun {hit[0]}, "
                          "aucun portrait propre à ce sexe trouvé")
            if not hit:
                missing.append(gender)
                expected = ", ".join(p for p in candidates + shared_candidates if p)
                print(f"[warn] {name} ({gender}) : portrait introuvable dans la source ; recherché : {expected}")
                stale = out / "Portraits" / f"{gender}.png"
                if stale.is_file():
                    stale.unlink()
                continue
            if not image.getchannel("A").getbbox():
                raise ValueError(f"{hit[1]}: portrait vide pour {name} ({gender})")
            rel = f"Portraits/{gender}.png"
            destination = out / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination)
            portraits[gender] = {"path": rel, "source": hit[0]}
            if shared:
                portraits[gender]["shared"] = True
            if coords is not None:
                portraits[gender]["tex_coords"] = list(coords)
        return {"portraits": portraits, "portraits_missing": missing}


def race_name(db, rec, rid):
    for c in range(14, 30):
        s = db.string(rec, c)
        if s:
            return s
    return db.string(rec, 11) or db.string(rec, 6) or f"race{rid}"


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "race"


def extract_appearance_textures(race, out):
    if re.sub(r"[^a-z]", "", race["name"].lower()) != "highelf":
        return []
    assets = Roots([HIGH_ELF_ASSETS])
    sources = []
    for relative in HIGH_ELF_EYE_TEXTURES:
        hit = assets.find(relative)
        if hit is None:
            raise FileNotFoundError(
                f"{race['name']}: texture yeux bleus absente : {relative} ; "
                f"restaurer les fichiers de {HIGH_ELF_ASSETS}")
        sources.append((relative, hit[1]))
    for relative, source in sources:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return list(HIGH_ELF_EYE_TEXTURES)


def normalize_naga_skin(path):
    data = bytearray(path.read_bytes())
    if len(data) < 48 or data[:4] != b"SKIN":
        raise ValueError(f"{path}: en-tête SKIN invalide ou tronqué")
    count, offset = struct.unpack_from("<II", data, 28)
    if not count or offset < 48 or offset + count * 48 > len(data):
        raise ValueError(f"{path}: tableau de sous-maillages SKIN invalide ou tronqué")
    positions = [offset + i * 48 for i in range(count)]
    ids = [struct.unpack_from("<H", data, p)[0] for p in positions]
    if 0 in ids:
        return 0
    if 10000 not in ids:
        raise ValueError(f"{path}: aucun sous-maillage de base Naga reconnu (0 ou 10000)")
    changed = 0
    for position, geoset in zip(positions, ids):
        if geoset == 10000:
            struct.pack_into("<H", data, position, 0)
            changed += 1
    path.write_bytes(data)
    return changed


NAGA_PLACEHOLDER_TEXTURE = "character/human/male/humanmaleskin00_00.blp"


def clear_naga_placeholder_textures(db, recs):
    """Sirus remplit les emplacements de texture inutilisés avec une peau humaine opaque.

    Le client 3.3.5 la compose pour de bon (cuir chevelu par-dessus le visage,
    sous-vêtements), ce qui recouvre les textures de visage : on vide ces champs.
    """
    cleaned, count = [], 0
    for rec in recs:
        rec = bytearray(rec)
        for col in (4, 5, 6):
            if norm(db.string(rec, col)) == NAGA_PLACEHOLDER_TEXTURE:
                struct.pack_into("<I", rec, col * 4, 0)
                count += 1
        cleaned.append(bytes(rec))
    return cleaned, count


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(here / "01-CoA"))
    ap.add_argument("--dst", default=str(here / "03-Races"))
    ap.add_argument("--only", default="", help="IDs de races, ex: 12,24")
    ap.add_argument("--exclude-standard", action="store_true")
    ap.add_argument("--fallback", action="append", default=[], help="racines supplémentaires pour trouver modèles/textures")
    ap.add_argument("--portraits-src", default=str(here / "Icons"),
                    help="dossier des PNG de portraits (Icons par défaut), ou racine Interface")
    ap.add_argument("--portraits-only", action="store_true",
                    help="met à jour seulement les portraits et race.json des extractions existantes")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.portraits_only:
        if a.list:
            ap.error("--portraits-only et --list sont incompatibles")
        dst = Path(a.dst)
        wanted = {int(x) for x in a.only.split(",") if x.strip()} if a.only else None
        portraits = Portraits(Path(a.portraits_src))
        paths = sorted(dst.glob("[0-9]*-*/race.json"))
        updated = 0
        for path in paths:
            original = path.read_bytes()
            meta = json.loads(original)
            if (wanted is not None and meta["id"] not in wanted
                    or a.exclude_standard and meta["id"] in STANDARD):
                continue
            meta.update(portraits.extract(meta, path.parent))
            text = json.dumps(meta, indent=2, ensure_ascii=False)
            if b"\r\n" in original:
                text = text.replace("\n", "\r\n")
            path.write_bytes(text.encode("utf-8"))
            print(f"[{meta['id']:02d}] {meta['name']} : {len(meta['portraits'])} portraits, "
                  f"{len(meta['portraits_missing'])} manquants")
            updated += 1
        if not updated:
            sys.exit(f"Aucune extraction sélectionnée dans {dst}")
        return

    src = Path(a.src)
    dbc_dir = next((p for p in src.iterdir() if p.is_dir() and p.name.lower() == "dbfilesclient"), None) if src.is_dir() else None
    if not dbc_dir:
        sys.exit(f"DBFilesClient introuvable dans {src}")

    def load(name):
        f = next((p for p in dbc_dir.iterdir() if p.name.lower() == name.lower() + ".dbc"), None)
        return Dbc(f) if f else None

    dbs = {n: load(n) for n in list(SPECS) + DERIVED}
    races = dbs["ChrRaces"]
    if not races:
        sys.exit("ChrRaces.dbc introuvable")

    # --- liste des races ---
    info = {}
    for rec in races.recs:
        rid = races.u32(rec, 0)
        info[rid] = {
            "id": rid,
            "name": race_name(races, rec, rid),
            "client_file": races.string(rec, 11),
            "faction": FACTION.get(races.u32(rec, 13), "?"),
            "male_display": races.u32(rec, 4),
            "female_display": races.u32(rec, 5),
        }
    cbi = dbs["CharBaseInfo"]
    for rid, r in info.items():
        r["classes"] = sorted({c[1] for c in cbi.recs if c[0] == rid}) if cbi else []
        cs = dbs["CharSections"]
        r["char_sections"] = sum(1 for x in cs.recs if cs.u32(x, 1) == rid) if cs else 0

    print(f"{'ID':>3}  {'Nom':22s} {'Faction':9s} {'Classes':>7} {'Sections':>8}  Base")
    for rid in sorted(info):
        r = info[rid]
        print(f"{rid:>3}  {r['name'][:22]:22s} {r['faction']:9s} {len(r['classes']):>7} "
              f"{r['char_sections']:>8}  {'standard' if rid in STANDARD else ''}")
    print(f"\n{len(info)} races dans ChrRaces ({sum(1 for r in info.values() if r['classes'])} jouables via CharBaseInfo)")
    if a.list:
        return

    # --- sélection ---
    ids = sorted(info)
    if a.only:
        want = {int(x) for x in a.only.split(",") if x.strip()}
        ids = [i for i in ids if i in want]
    if a.exclude_standard:
        ids = [i for i in ids if i not in STANDARD]
    if not ids:
        sys.exit("Aucune race à extraire")

    portraits = Portraits(Path(a.portraits_src))
    roots = Roots([src] + [Path(p) for p in a.fallback])
    dst = Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    cdi, cmd, cdie = dbs["CreatureDisplayInfo"], dbs["CreatureModelData"], dbs["CreatureDisplayInfoExtra"]
    index = []

    for rid in ids:
        r = info[rid]
        cdi_recs, cmd_recs, extra_recs = player_rows(dbs, r["male_display"], r["female_display"])
        out = dst / f"{rid:02d}-{slug(r['name'])}"
        sources = [src, HIGH_ELF_ASSETS, Path(a.portraits_src), *(Path(p) for p in a.fallback)]
        if any(out.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(out.resolve())
               for source in sources):
            raise ValueError(f"Sources et destination {out} doivent être distinctes et non imbriquées")
        if out.exists():
            shutil.rmtree(out)
        counts = {}
        placeholders_cleared = 0

        # DBC "directes"
        selected = {}
        for name, spec in SPECS.items():
            db = dbs[name]
            if not db:
                continue
            recs = [x for x in db.recs if matches(db, x, spec, rid)]
            if name == "CharSections" and re.sub(r"[^a-z]", "", r["name"].lower()) == "naga":
                recs, cleared = clear_naga_placeholder_textures(db, recs)
                print(f"[info] Naga : {cleared} textures de remplissage CharSections vidées")
                placeholders_cleared = cleared
            selected[name] = recs
            if recs:
                db.write(out / "DBFilesClient" / f"{name}.dbc", recs)
                counts[name] = len(recs)

        # Suivre les displays joueur, pas les PNJ qui partagent le même ID de race.
        disp_ids = {r["male_display"], r["female_display"]}
        if cdi:
            if cdi_recs:
                cdi.write(out / "DBFilesClient" / "CreatureDisplayInfo.dbc", cdi_recs)
                counts["CreatureDisplayInfo"] = len(cdi_recs)
        extra_ids = {cdi.u32(x, 3) for x in cdi_recs if cdi.u32(x, 3)}
        if cdie:
            recs = extra_recs
            selected["CreatureDisplayInfoExtra"] = recs
            if recs:
                cdie.write(out / "DBFilesClient" / "CreatureDisplayInfoExtra.dbc", recs)
                counts["CreatureDisplayInfoExtra"] = len(recs)
        model_ids = {cdi.u32(x, 1) for x in cdi_recs} if cdi else set()
        if cmd_recs:
            cmd.write(out / "DBFilesClient" / "CreatureModelData.dbc", cmd_recs)
            counts["CreatureModelData"] = len(cmd_recs)

        # --- fichiers : modèles + textures ---
        wanted = {}  # clé normalisée -> chemin relatif voulu
        player_skins = set()
        model_dir_of = {}
        for x in cmd_recs:
            mp = model_path(cmd.string(x, 2))
            if not mp:
                continue
            d = mp.rsplit("/", 1)[0] if "/" in mp else ""
            model_dir_of[cmd.u32(x, 0)] = d
            wanted[norm(mp)] = mp
            hit = roots.find(mp)
            if hit:
                for dep in model_dependencies(hit[1], mp):
                    wanted[norm(dep)] = dep
                    if dep.lower().endswith(".skin"):
                        player_skins.add(norm(dep))
            for rel, _ in roots.sibling_files(d):
                wanted[norm(rel)] = rel
        for x in cdi_recs:  # textures relatives au dossier du modèle
            d = model_dir_of.get(cdi.u32(x, 1), "")
            for c in (6, 7, 8, 9):
                s = cdi.string(x, c)
                if s:
                    p = f"{d}/{s}" if d else s
                    wanted.setdefault(norm(p), p)
        for x in selected.get("CharSections", []):
            cs = dbs["CharSections"]
            for c in (4, 5, 6):  # TextureName[3] ; 7/8 = flags/variation (pas des chaînes)
                s = cs.string(x, c).replace("\\", "/")
                if s:
                    wanted.setdefault(norm(s), s)
        for x in selected.get("CreatureDisplayInfoExtra", []):
            s = cdie.string(x, 20)
            if s:
                p = f"Textures/BakedNpcTextures/{s}"
                wanted.setdefault(norm(p), p)

        copied, missing = [], []
        for k, rel in sorted(wanted.items()):
            hit = roots.find(rel)
            if not hit:
                missing.append(rel)
                continue
            real_rel, f = hit
            t = out / real_rel
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
            copied.append(real_rel)

        appearance_textures = extract_appearance_textures(r, out)
        copied = sorted(set(copied) | set(appearance_textures))
        skin_fixes = []
        if re.sub(r"[^a-z]", "", r["name"].lower()) == "naga":
            for relative in copied:
                if norm(relative) not in player_skins:
                    continue
                changed = normalize_naga_skin(out / relative)
                if changed:
                    skin_fixes.append({"path": relative, "from": 10000, "to": 0, "sections": changed})
                    print(f"[info] Naga : {relative}, {changed} sous-maillages de base 10000 -> 0")
        meta = {
            **r,
            "dbc_rows": counts,
            "display_ids": sorted(disp_ids),
            "extra_display_ids": sorted(extra_ids),
            "model_ids": sorted(model_ids),
            "models": sorted(model_dir_of.values()),
            "files_copied": len(copied),
            "files_missing": missing,
            "appearance_textures": appearance_textures,
            "skin_geoset_fixes": skin_fixes,
            "placeholder_textures_cleared": placeholders_cleared,
            **portraits.extract(r, out),
        }
        (out / "race.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        index.append({k: meta[k] for k in ("id", "name", "faction", "classes", "dbc_rows", "files_copied")}
                     | {"missing": len(missing), "folder": out.name})
        print(f"[{rid:02d}] {r['name']:20s} -> {out.name}  "
              f"({sum(counts.values())} lignes DBC, {len(copied)} fichiers, {len(missing)} manquants)")

    (dst / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nOK -> {dst}")


if __name__ == "__main__":
    run_logged(main, __file__)
