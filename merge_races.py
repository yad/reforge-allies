#!/usr/bin/env python3
"""
merge_races.py - Patch différentiel de races (03-Races) au-dessus de 02-HD-Clean.

Tout est piloté par merge-config.json (voir ce fichier).

Ce que fait le script :
  1. prépare une copie de travail de 02-HD-Clean/patch-X.mpq
  2. DBC : pour chaque race choisie, importe ses lignes dans les DBC de base avec
       - renumérotation de la race (source -> target, <= 32 à cause des masques 32 bits)
       - déplacement ("relocate") de la race de base qui occupe déjà l'ID cible
         (ex. GoblinOld en 9) vers un ID libre, dans toutes les DBC
       - renumérotation des IDs de lignes en cas de collision (CMD / CDI / CDIE / CharSections...)
       - noms frFR/enUS, faction (Alliance/Horde), langue de base, classes autorisées,
         masques de races des skills (langue commune / orc)
  3. copie les modèles / textures des dossiers 03-Races/<race>/
  4. Glue : CharacterCreate.lua (MAX_RACES + icônes), CharacterCreate.xml (boutons de races),
       GlueParent.lua (fond de création), RaceStrings.lua (textes frFR), atlas des icônes de races
  5. retire les fichiers identiques à la base : seuls les ajouts/modifications restent dans patch-Z.mpq
     rapport : 04-Merge/merge-report.md + race-mapping.json (à utiliser côté serveur)
  6. archive MPQ StormLib : fichier final défini par mpq_output dans la configuration

Usage :  python merge_races.py [--config merge-config.json] [--skip-glue]
"""
import argparse
import ctypes
import filecmp
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
from pathlib import Path

from execution_log import run_logged
from race_assets import HIGH_ELF_EYE_TEXTURES, model_dependencies, model_path, player_rows
from race_images import TC_RE, crop_frac, load_blp, recolor_green_to_blue, recolor_character_skin, save_blp_argb

ALL = 0xFFFFFFFF
LOCALES = ["enUS", "koKR", "frFR", "deDE", "zhCN", "zhTW", "esES", "esMX", "ruRU"]
CLASS_IDS = {"Warrior": 1, "Paladin": 2, "Hunter": 3, "Rogue": 4, "Priest": 5,
             "Death Knight": 6, "Shaman": 7, "Mage": 8, "Warlock": 9, "Druid": 11}
STD_CLASSES = list(CLASS_IDS.values())
LANG_SKILL = {"Alliance": 98, "Horde": 109}      # Commun / Orc
BASE_LANG = {"Alliance": 7, "Horde": 1}          # ChrRaces.BaseLanguage
SIDE_VAL = {"Alliance": 0, "Horde": 1}           # ChrRaces.Alliance
DEFAULT_FACTION = {"Alliance": 1, "Horde": 2}    # FactionTemplate Humain / Orc
TABLES = ["ChrRaces", "CharBaseInfo", "CharStartOutfit", "SkillLineAbility", "SkillRaceClassInfo",
          "CharSections", "CharacterFacialHairStyles", "CharHairGeosets",
          "CreatureDisplayInfoExtra", "CreatureDisplayInfo", "CreatureModelData"]
CHR_STR = [6, 11] + list(range(14, 30)) + list(range(31, 47)) + list(range(48, 64)) + [65, 66, 67]
STR_COLS = {"ChrRaces": CHR_STR, "CharSections": [4, 5, 6], "CreatureDisplayInfo": [6, 7, 8, 9],
            "CreatureDisplayInfoExtra": [20], "CreatureModelData": [2]}
# colonnes "race" (pour déplacer une race existante)
RACE_SPECS = {
    "ChrRaces": ("col", 0), "CharBaseInfo": ("byte", 0), "CharStartOutfit": ("byte", 4),
    "SkillLineAbility": ("mask", 3), "SkillRaceClassInfo": ("mask", 2),
    "CharSections": ("col", 1), "CharacterFacialHairStyles": ("col", 0),
    "CharHairGeosets": ("col", 1), "CreatureDisplayInfoExtra": ("col", 1),
}
LUA_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

LOG = []


def log(level, msg):
    LOG.append((level, msg))
    print(f"[{level}] {msg}")


def bit(r):
    return 1 << (r - 1)


def mask_has(m, r):
    return m not in (0, ALL) and bool(m & bit(r))


def ci_find(root, rel):
    cur = Path(root)
    parts = rel.replace("\\", "/").split("/")
    if all(part not in ("", ".", "..") and ":" not in part for part in parts):
        exact = cur.joinpath(*parts)
        if exact.exists():
            return exact
    for part in parts:
        if not cur.is_dir():
            return None
        nxt = next((p for p in cur.iterdir() if p.name.lower() == part.lower()), None)
        if nxt is None:
            return None
        cur = nxt
    return cur


def read_text(path):
    b = Path(path).read_bytes()
    try:
        t, enc = b.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        t, enc = b.decode("latin-1"), "latin-1"
    crlf = "\r\n" in t
    return t.replace("\r\n", "\n"), enc, crlf


def write_text(path, t, enc, crlf):
    if crlf:
        t = t.replace("\n", "\r\n")
    Path(path).write_bytes(t.encode(enc))


# --------------------------------------------------------------------------- DBC
class Dbc:
    def __init__(self, path):
        self.path = Path(path)
        d = self.path.read_bytes()
        if len(d) < 20 or d[:4] != b"WDBC":
            raise ValueError(f"{path}: pas un WDBC")
        rc, self.fc, self.rs, ss = struct.unpack_from("<4I", d, 4)
        if self.rs == 0:
            raise ValueError(f"{path}: en-tête DBC invalide (fields={self.fc}, record_size={self.rs})")
        end = 20 + rc * self.rs + ss
        if end > len(d):
            raise ValueError(f"{path}: fichier tronqué (attendu {end} octets, obtenu {len(d)})")
        self.recs = [bytearray(d[20 + i * self.rs: 20 + (i + 1) * self.rs]) for i in range(rc)]
        sb = 20 + rc * self.rs
        self.strings = bytearray(d[sb: sb + ss]) or bytearray(b"\0")
        self._smap = None

    def u32(self, rec, col):
        return struct.unpack_from("<I", rec, col * 4)[0]

    def set_u32(self, rec, col, v):
        struct.pack_into("<I", rec, col * 4, v & ALL)

    def s(self, off):
        if off == 0:
            return ""
        if off >= len(self.strings):
            raise ValueError(f"{self.path}: offset de chaîne hors limites : {off}")
        return bytes(self.strings[off: self.strings.index(b"\0", off)]).decode("utf-8", "replace")

    def add_s(self, text):
        if not text:
            return 0
        if self._smap is None:
            self._smap, pos = {}, 0
            while pos < len(self.strings):
                end = self.strings.find(b"\0", pos)
                if end < 0:
                    break
                self._smap.setdefault(bytes(self.strings[pos:end]).decode("utf-8", "replace"), pos)
                pos = end + 1
        if text in self._smap:
            return self._smap[text]
        off = len(self.strings)
        self.strings += text.encode("utf-8") + b"\0"
        self._smap[text] = off
        return off

    def clone(self, src, rec, str_cols):
        new = bytearray(rec)
        for c in str_cols:
            if c * 4 + 4 <= len(new):
                self.set_u32(new, c, self.add_s(src.s(src.u32(rec, c))))
        return new

    def sig(self, rec, str_cols):
        sc = set(str_cols)
        return tuple(self.s(self.u32(rec, c)) if c in sc else self.u32(rec, c) for c in range(len(rec) // 4))

    def save(self):
        with open(self.path, "wb") as f:
            f.write(b"WDBC" + struct.pack("<4I", len(self.recs), self.fc, self.rs, len(self.strings)))
            for r in self.recs:
                f.write(r)
            f.write(self.strings)


def load_tables(dbc_dir):
    out = {}
    if not dbc_dir or not Path(dbc_dir).is_dir():
        return out
    for n in TABLES:
        p = ci_find(dbc_dir, n + ".dbc")
        if p:
            out[n] = Dbc(p)
    return out


class Alloc:
    def __init__(self):
        self.cur = {}

    def next(self, name, db):
        if name not in self.cur:
            self.cur[name] = max([db.u32(r, 0) for r in db.recs] + [0]) + 1
        v = self.cur[name]
        self.cur[name] += 1
        return v

    def note(self, name, db, v):
        self.next(name, db)
        if v >= self.cur[name]:
            self.cur[name] = v + 1


def import_rows(name, base, src, rows, tf, alloc):
    """Importe des lignes (pk col 0) : garde l'ID si libre, réutilise si identique, sinon réalloue."""
    str_cols = STR_COLS.get(name, [])
    existing = {base.u32(r, 0): r for r in base.recs}
    idmap = {}
    for r in rows:
        sid = src.u32(r, 0)
        new = base.clone(src, r, str_cols)
        tf(new)
        if sid in existing:
            if base.sig(existing[sid], str_cols) == base.sig(new, str_cols):
                idmap[sid] = sid
                continue
            nid = alloc.next(name, base)
        else:
            nid = sid
            alloc.note(name, base, nid)
        base.set_u32(new, 0, nid)
        base.recs.append(new)
        existing[nid] = new
        idmap[sid] = nid
    return idmap


def import_race_rows(name, base, src, race_col, sid, did, has_pk, alloc):
    n = 0
    for r in [x for x in src.recs if src.u32(x, race_col) == sid]:
        new = base.clone(src, r, STR_COLS.get(name, []))
        base.set_u32(new, race_col, did)
        if has_pk:
            base.set_u32(new, 0, alloc.next(name, base))
        base.recs.append(new)
        n += 1
    return n


def remap_model_texture_paths(data, paths):
    data = bytearray(data)
    count, offset = struct.unpack_from("<II", data, 80)
    for i in range(count):
        entry = offset + i * 16
        kind, _, size, start = struct.unpack_from("<4I", data, entry)
        if kind != 0:
            continue
        source = data[start:start + size].split(b"\0", 1)[0].decode("utf-8").replace("\\", "/").lower()
        target = paths.get(source)
        if target is not None:
            encoded = target.encode("utf-8") + b"\0"
            struct.pack_into("<II", data, entry + 8, len(encoded), len(data))
            data.extend(encoded)
    return data


def relocate_race(dbs, old, new):
    for name, (kind, arg) in RACE_SPECS.items():
        db = dbs.get(name)
        if not db:
            continue
        for rec in db.recs:
            if kind == "col" and db.u32(rec, arg) == old:
                db.set_u32(rec, arg, new)
            elif kind == "byte" and len(rec) > arg and rec[arg] == old:
                rec[arg] = new
            elif kind == "mask":
                m = db.u32(rec, arg)
                if mask_has(m, old):
                    db.set_u32(rec, arg, (m & ~bit(old)) | bit(new))


def remove_non_playable_race(dbs, rid):
    cbi = dbs.get("CharBaseInfo")
    if cbi and any(r[0] == rid for r in cbi.recs):
        raise ValueError(f"Impossible de remplacer la race jouable {rid}")
    for name, (kind, col) in RACE_SPECS.items():
        db = dbs.get(name)
        if not db or name == "CreatureDisplayInfoExtra":
            continue
        if kind == "col":
            db.recs = [r for r in db.recs if db.u32(r, col) != rid]
        elif kind == "byte":
            db.recs = [r for r in db.recs if r[col] != rid]
        else:
            retained = []
            for r in db.recs:
                mask = db.u32(r, col)
                if mask_has(mask, rid):
                    mask &= ~bit(rid)
                    if not mask:
                        continue
                    db.set_u32(r, col, mask)
                retained.append(r)
            db.recs = retained


def merge_mask_table(base, src, mask_col, key_cols, sid, did, add_missing, alloc, name):
    idx = {}
    for r in base.recs:
        idx.setdefault(tuple(base.u32(r, c) for c in key_cols), []).append(r)
    hit = miss = 0
    for r in list(src.recs):
        if not mask_has(src.u32(r, mask_col), sid):
            continue
        k = tuple(src.u32(r, c) for c in key_cols)
        if k in idx:
            for br in idx[k]:
                m = base.u32(br, mask_col)
                if m not in (0, ALL):
                    base.set_u32(br, mask_col, m | bit(did))
            hit += 1
        else:
            miss += 1
            if add_missing:
                new = bytearray(r)
                base.set_u32(new, mask_col, bit(did))
                base.set_u32(new, 0, alloc.next(name, base))
                base.recs.append(new)
                idx.setdefault(k, []).append(new)
    return hit, miss


def find_race_dir(races_dir, sid):
    for p in sorted(Path(races_dir).iterdir()):
        if p.is_dir() and re.match(rf"^0*{sid}-", p.name):
            return p
    return None


# --------------------------------------------------------------------------- fusion DBC + fichiers
def race_classes(rc, source_classes):
    key = f"{rc['name']}.allowed_classes"
    if "classes" in rc:
        raise ValueError(f"{rc['name']}: remplacer classes par allowed_classes avec des noms de classes")
    if "allowed_classes" not in rc:
        classes = [c for c in (source_classes or STD_CLASSES) if c in STD_CLASSES]
        if not classes:
            raise ValueError(f"{key} : aucune classe WotLK compatible dans la source")
        return classes
    names = rc["allowed_classes"]
    if not isinstance(names, list) or not names or any(not isinstance(n, str) for n in names):
        raise ValueError(f"{key} doit être une liste non vide de noms de classes")
    lookup = {name.casefold(): cid for name, cid in CLASS_IDS.items()}
    classes = []
    for name in names:
        cid = lookup.get(name.strip().casefold())
        if cid is None:
            raise ValueError(f"{key} : classe inconnue {name!r} ; valeurs : {', '.join(CLASS_IDS)}")
        if cid in classes:
            raise ValueError(f"{key} : classe en double {name!r}")
        classes.append(cid)
    return sorted(classes)


def install_appearance_textures(meta, rdir, out, asset_paths):
    allowed = {p.lower() for p in HIGH_ELF_EYE_TEXTURES}
    required = allowed & asset_paths
    textures = meta.get("appearance_textures", [])
    if (not isinstance(textures, list)
            or any(not isinstance(p, str) or p.lower() not in allowed for p in textures)):
        raise ValueError(f"{rdir.name}: appearance_textures contient un chemin non autorisé")
    if {p.lower() for p in textures} != required:
        raise ValueError(f"{rdir.name}: textures d'apparence manquantes ou incompatibles ; "
                         "relancer extract_races.py")
    replaced = 0
    for relative in textures:
        source = ci_find(rdir, relative)
        target = ci_find(out, relative)
        if target is not None:
            replaced += 1
        else:
            target = out / relative
        if source is None or not source.is_file():
            raise FileNotFoundError(f"{rdir.name}: texture extraite absente : {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return len(textures), replaced


def recolor_face_textures(db, rows, out, name):
    """Écrit des copies bleues des textures de visage Blood Elf pour une race dédiée.

    Les iris sont peints dans les textures de visage : seules des copies sous
    Character/HighElf sont créées, les fichiers partagés des Blood Elves restent intacts.
    """
    created, cache = [], {}
    for row in rows:
        if db.u32(row, 3) != 1:
            continue
        for col in (4, 5):
            source = db.s(db.u32(row, col)).replace("\\", "/")
            if not source:
                continue
            if source.lower() not in cache:
                path = ci_find(out, source)
                if path is None or not path.is_file():
                    raise FileNotFoundError(f"{name}: texture de visage absente pour l'apparence HD : {source}")
                image = load_blp(path)
                recolored = recolor_green_to_blue(image)
                if recolored is None:
                    cache[source.lower()] = source
                else:
                    parts = source.split("/")
                    stem = re.sub(r"^bloodelf", "HighElf", parts[-1], flags=re.I)
                    target = f"Character/HighElf/{parts[-2]}/{stem}"
                    save_blp_argb(recolored, ci_find(out, target) or out / target)
                    cache[source.lower()] = target
                    created.append(target)
            db.set_u32(row, col, db.add_s(cache[source.lower()].replace("/", "\\")))
    return created


def select_skin_colors(db, rows, colors, name):
    if (not isinstance(colors, list) or not colors
            or any(type(c) is not int or c < 0 for c in colors) or len(set(colors)) != len(colors)):
        raise ValueError(f"{name}: appearance.skin_colors doit contenir des indices uniques positifs ou nuls")
    bodies = [r for r in rows if db.u32(r, 3) == 0]
    if not bodies:
        raise ValueError(f"{name}: aucune peau disponible pour appearance.skin_colors")
    for sex in {db.u32(r, 2) for r in bodies}:
        available = {db.u32(r, 9) for r in bodies if db.u32(r, 2) == sex}
        if set(colors) - available:
            raise ValueError(f"{name}: couleurs de peau absentes pour le sexe {sex} : {sorted(set(colors) - available)}")
    selected = []
    for row in rows:
        if db.u32(row, 3) in (0, 1, 4):
            color = db.u32(row, 9)
            if color not in colors:
                continue
            db.set_u32(row, 9, colors.index(color))
        selected.append(row)
    return selected


def recolor_skin_textures(db, rows, out, tone, name, source_root=None):
    created, cache = [], {}
    for row in rows:
        if db.u32(row, 3) not in (0, 1, 4):
            continue
        for col in (4, 5, 6):
            source = db.s(db.u32(row, col)).replace("\\", "/")
            if not source:
                continue
            key = source.lower()
            if key not in cache:
                path = ci_find(out if source_root is None else source_root, source)
                if path is None or not path.is_file():
                    raise FileNotFoundError(f"{name}: texture de peau HD absente : {source}")
                image = recolor_character_skin(load_blp(path), tone)
                if image is None:
                    cache[key] = source
                else:
                    if image.getchannel("A").getextrema() != (255, 255):
                        raise ValueError(f"{name}: texture de peau HD transparente non prise en charge : {source}")
                    family = "Troll" if tone in ("forest", "ice") else "Orc"
                    target = f"Variants/{family}/{tone}/{source}"
                    save_blp_argb(image, out / target)
                    cache[key] = target
                    created.append(target)
            db.set_u32(row, col, db.add_s(cache[key]))
    return created


def merge_dbc_and_files(cfg, root, out, dbs):
    races_dir = root / cfg["races_dir"]
    max_id = cfg.get("max_race_id", 32)
    if type(max_id) is not int or not 1 <= max_id <= 32:
        raise ValueError("max_race_id doit être un entier entre 1 et 32 (masques de races 32 bits)")
    if "allowed_classes" in cfg:
        raise ValueError("Déplacer allowed_classes dans chaque race et utiliser des noms de classes")
    alloc = Alloc()
    results, needed = [], {}
    appearance_base = (load_tables(out / "DBFilesClient")
                       if any(r.get("appearance") is not None for r in cfg["races"]) else {})

    # contrôles
    targets = [r["target"] for r in cfg["races"]]
    if len(set(targets)) != len(targets):
        sys.exit("Deux races ont le même 'target'")
    for r in cfg["races"]:
        if not 1 <= r["target"] <= max_id:
            sys.exit(f"{r['name']}: target {r['target']} hors limite (1..{max_id})")
        if type(r.get("replace_non_playable", False)) is not bool:
            raise ValueError(f"{r['name']}: replace_non_playable doit être un booléen")
        if type(r.get("swap_model_sexes", False)) is not bool:
            raise ValueError(f"{r['name']}: swap_model_sexes doit être un booléen")

    chr_base = dbs.get("ChrRaces")
    if not chr_base:
        sys.exit("ChrRaces.dbc absent de la base")
    for r in cfg["races"]:
        if r.get("faction") not in SIDE_VAL:
            sys.exit(f"{r.get('name', '<race>')}: faction invalide (Alliance ou Horde attendue)")

    # --- 1. libérer les IDs cibles occupés (relocate)
    used = {chr_base.u32(r, 0) for r in chr_base.recs}
    reserved = set(targets)
    relocated = []
    replaced = {}
    for rc in cfg["races"]:
        t = rc["target"]
        if t in used:
            old_row = next(r for r in chr_base.recs if chr_base.u32(r, 0) == t)
            old_name = next((chr_base.s(chr_base.u32(old_row, c)) for c in range(14, 30)
                             if chr_base.s(chr_base.u32(old_row, c))), chr_base.s(chr_base.u32(old_row, 11)))
            if rc.get("replace_non_playable", False):
                remove_non_playable_race(dbs, t)
                replaced[t] = old_name
                log("warn", f"race PNJ '{old_name}' (ID {t}) remplacée par {rc['name']} ; "
                            "les displays PNJ sont conservés mais leur apparence peut changer")
                continue
            if not cfg.get("relocate_conflicts", True):
                sys.exit(f"ID {t} déjà pris dans la base et relocate_conflicts=false")
            new = next((i for i in range(12, max_id + 1) if i not in used and i not in reserved), None)
            if new is None:
                sys.exit(f"Plus d'ID libre <= {max_id} pour déplacer la race {t} (limite de 32 races)")
            relocate_race(dbs, t, new)
            used.discard(t)
            used.add(new)
            relocated.append({"name": old_name, "from": t, "to": new})
            log("info", f"race de base '{old_name}' déplacée de l'ID {t} vers {new}")

    # --- 2. import race par race
    for rc in cfg["races"]:
        sid, did, side = rc["source"], rc["target"], rc["faction"]
        rdir = find_race_dir(races_dir, sid)
        if not rdir:
            raise ValueError(f"{rc['name']}: dossier 03-Races pour la source {sid} introuvable")
        namespace = rc.get("asset_namespace")
        if namespace is not None:
            if (not isinstance(namespace, str) or not namespace
                    or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", namespace)):
                raise ValueError(f"{rc['name']}: asset_namespace doit être un chemin relatif simple")
            if rc.get("appearance") is not None:
                raise ValueError(f"{rc['name']}: asset_namespace est incompatible avec une apparence HD")
        namespace_paths = {
            f.relative_to(rdir).as_posix().lower(): f"{namespace}/{f.relative_to(rdir).as_posix()}"
            for f in rdir.rglob("*") if f.is_file()
        } if namespace is not None else {}

        def asset_path(relative):
            return namespace_paths.get(relative.replace("\\", "/").lower(), relative)

        sdb = load_tables(rdir / "DBFilesClient")
        meta = {}
        if (rdir / "race.json").exists():
            meta = json.loads((rdir / "race.json").read_text(encoding="utf-8"))
        srow = next((r for r in sdb["ChrRaces"].recs if sdb["ChrRaces"].u32(r, 0) == sid), None) if "ChrRaces" in sdb else None
        if srow is None:
            raise ValueError(f"{rc['name']}: ligne ChrRaces {sid} absente de {rdir.name}")

        def tbl(name, source=None):
            b, s = dbs.get(name), (sdb if source is None else source).get(name)
            if not b or not s:
                return None
            if b.rs != s.rs:
                raise ValueError(f"{rc['name']}: {name} incompatible (base {b.rs} / source {s.rs} octets)")
            return b, s

        schr = sdb["ChrRaces"]
        if schr.rs != chr_base.rs:
            raise ValueError(f"{rc['name']}: ChrRaces.dbc incompatible "
                             f"(base {chr_base.rs} octets, source {schr.rs})")
        appearance = rc.get("appearance")
        appearance_dbs, appearance_sid = sdb, sid
        appearance_root, appearance_rdir = out, None
        race_source, race_row = schr, srow
        if appearance is not None:
            if (not isinstance(appearance, dict)
                    or ("base_race" in appearance) == ("source_race" in appearance)):
                raise ValueError(f"{rc['name']}: appearance exige exactement un base_race ou source_race")
            appearance_sid = appearance.get("base_race", appearance.get("source_race"))
            if type(appearance_sid) is not int or appearance_sid < 1:
                raise ValueError(f"{rc['name']}: ID de race d'apparence invalide")
            if "source_race" in appearance:
                appearance_rdir = find_race_dir(races_dir, appearance_sid)
                if appearance_rdir is None:
                    raise ValueError(f"{rc['name']}: source d'apparence {appearance_sid} introuvable")
                appearance_root = appearance_rdir
                appearance_dbs = load_tables(appearance_rdir / "DBFilesClient")
            else:
                appearance_dbs = appearance_base
            if "skin_tone" in appearance:
                allowed_tones = (("brown", "red") if appearance.get("base_race") == 2 else
                                 ("forest", "ice") if appearance.get("source_race") == 28 else ())
                if appearance["skin_tone"] not in allowed_tones:
                    raise ValueError(f"{rc['name']}: appearance.skin_tone incompatible avec la race d'apparence")
            race_source = appearance_dbs["ChrRaces"]
            if race_source.rs != chr_base.rs:
                raise ValueError(f"{rc['name']}: ChrRaces.dbc incompatible pour la race d'apparence")
            race_row = next((r for r in race_source.recs
                             if race_source.u32(r, 0) == appearance_sid), None)
            if race_row is None:
                raise ValueError(f"{rc['name']}: race d'apparence {appearance_sid} absente des DBC")
            log("info", f"{rc['name']}: apparence de la race {appearance_sid} dans {appearance_root} ; "
                        "modèles et personnalisations de la race source remplacés")
        swap_sexes = rc.get("swap_model_sexes", False)
        male, female = race_source.u32(race_row, 4), race_source.u32(race_row, 5)
        if swap_sexes:
            male, female = female, male
        cdi_rows, cmd_rows, extra_rows = player_rows(appearance_dbs, male, female)
        model_overrides = {}
        if appearance is not None:
            cdi = appearance_dbs["CreatureDisplayInfo"]
            for sex, display in (("male", male), ("female", female)):
                override = appearance.get(f"{sex}_model")
                if override is None:
                    continue
                if not isinstance(override, str):
                    raise ValueError(f"{rc['name']}: appearance.{sex}_model doit être un chemin relatif")
                override = model_path(override)
                if (not override.lower().endswith(".m2") or override.startswith("/")
                        or ":" in override or ".." in override.split("/")):
                    raise ValueError(f"{rc['name']}: chemin de modèle HD invalide : {override}")
                row = next(r for r in cdi_rows if cdi.u32(r, 0) == display)
                model_id = cdi.u32(row, 1)
                if model_id in model_overrides and model_overrides[model_id] != override:
                    raise ValueError(f"{rc['name']}: deux chemins pour le même modèle HD {model_id}")
                model_overrides[model_id] = override

        # modèles / displays (minimum : les 2 displays joueur)
        cmd_map = cdie_map = cdi_map = {}
        t_cdi = tbl("CreatureDisplayInfo", appearance_dbs)
        t_cmd = tbl("CreatureModelData", appearance_dbs)
        t_cdie = tbl("CreatureDisplayInfoExtra", appearance_dbs)
        if extra_rows and not t_cdie:
            raise ValueError(f"{rc['name']}: CreatureDisplayInfoExtra indisponible pour les displays joueur")
        asset_list = []
        asset_dirs = set()
        if t_cdi and t_cmd:
            cdi_b, cdi_s = t_cdi
            cmd_b, cmd_s = t_cmd

            def tf_cmd(n):
                override = model_overrides.get(cmd_b.u32(n, 0))
                if override is not None:
                    cmd_b.set_u32(n, 2, cmd_b.add_s(override))
                elif namespace is not None:
                    path = model_path(cmd_b.s(cmd_b.u32(n, 2)))
                    cmd_b.set_u32(n, 2, cmd_b.add_s(asset_path(path)))

            cmd_map = import_rows("CreatureModelData", cmd_b, cmd_s, cmd_rows, tf_cmd, alloc)
            model_dir = {}
            for r in cmd_rows:
                mp = model_overrides.get(cmd_s.u32(r, 0), model_path(cmd_s.s(cmd_s.u32(r, 2))))
                if mp:
                    asset_list.append(mp)
                    model_file = ci_find(out, mp)
                    if appearance is not None:
                        model_file = ci_find(appearance_root, mp)
                        if model_file is None or not model_file.is_file():
                            raise ValueError(f"{rc['name']}: modèle HD absent de la source d'apparence : {mp}")
                    elif model_file is None or cfg.get("overwrite_files", True):
                        model_file = ci_find(rdir, mp) or model_file
                    if model_file:
                        dependencies = model_dependencies(model_file, mp)
                        if appearance is not None:
                            for dep in dependencies:
                                if dep.lower().endswith(".skin"):
                                    skin = ci_find(appearance_root, dep)
                                    if skin is None or not skin.is_file():
                                        raise ValueError(f"{rc['name']}: skin HD absent de la source d'apparence : {dep}")
                        asset_list.extend(dependencies)
                    model_dir[cmd_s.u32(r, 0)] = mp.rsplit("/", 1)[0] if "/" in mp else ""
                    asset_dirs.add(model_dir[cmd_s.u32(r, 0)].lower())
            if t_cdie:
                cdie_b, cdie_s = t_cdie
                rows = extra_rows

                def tf_cdie(n):
                    cdie_b.set_u32(n, 1, did)
                    if swap_sexes:
                        sex = cdie_b.u32(n, 2)
                        if sex not in (0, 1, 2):
                            raise ValueError(f"{rc['name']}: sexe invalide dans CreatureDisplayInfoExtra : {sex}")
                        if sex != 2:
                            cdie_b.set_u32(n, 2, 1 - sex)

                cdie_map = import_rows("CreatureDisplayInfoExtra", cdie_b, cdie_s, rows, tf_cdie, alloc)
                for r in rows:
                    s = cdie_s.s(cdie_s.u32(r, 20)) if cdie_s.rs >= 84 else ""
                    if s:
                        asset_list.append("Textures/BakedNpcTextures/" + s)

            def tf_cdi(n):
                cdi_b.set_u32(n, 1, cmd_map[cdi_b.u32(n, 1)])
                if cdi_b.u32(n, 3):
                    cdi_b.set_u32(n, 3, cdie_map[cdi_b.u32(n, 3)])

            cdi_map = import_rows("CreatureDisplayInfo", cdi_b, cdi_s, cdi_rows, tf_cdi, alloc)
            for r in cdi_rows:
                d = model_dir.get(cdi_s.u32(r, 1), "")
                for c in (6, 7, 8, 9):
                    s = cdi_s.s(cdi_s.u32(r, c))
                    if s:
                        asset_list.append(f"{d}/{s}" if d else s)
        else:
            raise ValueError(f"{rc['name']}: CreatureDisplayInfo/ModelData indisponibles")

        # tables liées à la race
        counts = {}
        for name, rcol, pk in (("CharSections", 1, True), ("CharHairGeosets", 1, True),
                               ("CharacterFacialHairStyles", 0, False)):
            t = tbl(name, appearance_dbs)
            if appearance is not None and not t:
                raise ValueError(f"{rc['name']}: {name}.dbc absent pour l'apparence HD")
            if t:
                counts[name] = import_race_rows(name, t[0], t[1], rcol, appearance_sid, did, pk, alloc)
                if swap_sexes:
                    new_rows = t[0].recs[-counts[name]:] if counts[name] else []
                    for row in new_rows:
                        sex = t[0].u32(row, rcol + 1)
                        if sex not in (0, 1):
                            raise ValueError(f"{rc['name']}: sexe de modèle invalide dans {name} : {sex}")
                        t[0].set_u32(row, rcol + 1, 1 - sex)
                if name == "CharSections" and appearance is not None and "skin_colors" in appearance:
                    new_rows = t[0].recs[-counts[name]:] if counts[name] else []
                    selected = select_skin_colors(t[0], new_rows, appearance["skin_colors"], rc["name"])
                    if counts[name]:
                        t[0].recs[-counts[name]:] = selected
                    counts[name] = len(selected)
                if name == "CharSections" and namespace is not None:
                    for row in t[0].recs[len(t[0].recs) - counts[name]:] if counts[name] else ():
                        for col in (4, 5, 6):
                            texture = t[0].s(t[0].u32(row, col))
                            t[0].set_u32(row, col, t[0].add_s(asset_path(texture)))
                if name == "CharSections" and appearance is not None and appearance.get("eye_color") == "blue":
                    new_rows = t[0].recs[len(t[0].recs) - counts[name]:]
                    faces = recolor_face_textures(t[0], new_rows, out, rc["name"])
                    log("info", f"{rc['name']}: {len(faces)} textures de visage recolorées en bleu")
                    asset_list.extend(faces)
                if name == "CharSections" and appearance is not None and "skin_tone" in appearance:
                    new_rows = t[0].recs[len(t[0].recs) - counts[name]:] if counts[name] else []
                    textures = recolor_skin_textures(t[0], new_rows, out, appearance["skin_tone"],
                                                    rc["name"], source_root=appearance_root)
                    log("info", f"{rc['name']}: {len(textures)} textures HD adaptées ({appearance['skin_tone']})")
                    asset_list.extend(textures)
                if name == "CharSections":
                    for r in [x for x in t[1].recs if t[1].u32(x, 1) == appearance_sid]:
                        for c in (4, 5, 6):
                            s = t[1].s(t[1].u32(r, c)).replace("\\", "/")
                            if s:
                                asset_list.append(s)

        # classes
        sc = sdb.get("CharBaseInfo")
        src_classes = sorted({r[1] for r in sc.recs if r[0] == sid}) if sc else []
        classes = race_classes(rc, src_classes)
        cbi = dbs.get("CharBaseInfo")
        if cbi:
            have = {(r[0], r[1]) for r in cbi.recs}
            for c in classes:
                if (did, c) not in have:
                    cbi.recs.append(bytearray([did, c]))

        # tenues de départ
        so = dbs.get("CharStartOutfit")
        if so:
            if rc.get("outfit", "copy") == "source" and tbl("CharStartOutfit"):
                rows = [r for r in sdb["CharStartOutfit"].recs if r[4] == sid and r[5] in classes]
            else:
                frm = rc.get("outfit_from", DEFAULT_FACTION[side] if False else (1 if side == "Alliance" else 2))
                rows = [r for r in so.recs if r[4] == frm and r[5] in classes]
            miss_cls = sorted(set(classes) - {r[5] for r in rows})
            donors = [1, 3, 4, 7, 11] if side == "Alliance" else [2, 5, 6, 8, 10]
            for c in miss_cls:  # classe absente chez la race modèle : on prend une race de la même faction qui l'a
                for d in donors:
                    extra = [r for r in so.recs if r[4] == d and r[5] == c]
                    if extra:
                        rows = rows + extra
                        break
            for r in rows:
                new = bytearray(r)
                new[4] = did
                so.set_u32(new, 0, alloc.next("CharStartOutfit", so))
                so.recs.append(new)
            counts["CharStartOutfit"] = len(rows)
            still = sorted(set(classes) - {r[5] for r in rows})
            if still:
                log("warn", f"{rc['name']}: pas de tenue de départ pour les classes {still}")
            elif miss_cls:
                log("info", f"{rc['name']}: tenues de départ des classes {miss_cls} copiées d'une autre race de la même faction")

        # skills (masques de races)
        for name, mcol, key in (("SkillLineAbility", 3, (1, 2)), ("SkillRaceClassInfo", 2, (1, 3, 4))):
            t = tbl(name)
            if t:
                hit, miss = merge_mask_table(t[0], t[1], mcol, key, sid, did, rc.get("add_missing_skills", False), alloc, name)
                counts[name] = hit
                if miss:
                    log("info", f"{rc['name']}: {miss} lignes {name} ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)")

        # ChrRaces
        new = chr_base.clone(schr, srow, CHR_STR)
        if appearance is not None:
            # An HD appearance donor may be an NPC: never inherit its gameplay flags.
            for col in (6, 65, 66, 67):
                value = race_source.s(race_source.u32(race_row, col))
                chr_base.set_u32(new, col, chr_base.add_s(value))
        # These tokens are case-sensitive suffixes of GlueStrings localization keys.
        for col in (65, 66, 67):
            value = chr_base.s(chr_base.u32(new, col)).upper()
            chr_base.set_u32(new, col, chr_base.add_s(value))
        chr_base.set_u32(new, 0, did)
        chr_base.set_u32(new, 4, cdi_map[male])
        chr_base.set_u32(new, 5, cdi_map[female])
        if swap_sexes:
            male_custom, female_custom = (chr_base.u32(new, c) for c in (65, 66))
            chr_base.set_u32(new, 65, female_custom)
            chr_base.set_u32(new, 66, male_custom)
        displaced_ids = {x["to"] for x in relocated}
        used_tokens = {
            chr_base.s(chr_base.u32(row, 11)).upper()
            for row in chr_base.recs
            if chr_base.u32(row, 0) not in displaced_ids
        } | {x["token"] for x in results}
        requested_token = rc.get("client_file") or meta.get("client_file") or rc["name"]
        token = str(requested_token).upper()
        if token in used_tokens:
            if rc.get("client_file"):
                raise ValueError(f"{rc['name']}: ClientFileString déjà utilisé: {token}")
            token = race_token(rc["name"])
            suffix = 2
            base_token = token
            while token in used_tokens:
                token = f"{base_token}_{suffix}"
                suffix += 1
            log("warn", f"{rc['name']}: ClientFileString {requested_token!r} en conflit, remplacement par {token}")
        chr_base.set_u32(new, 11, chr_base.add_s(token))
        src_side = chr_base.u32(new, 13)
        chr_base.set_u32(new, 13, SIDE_VAL[side])
        chr_base.set_u32(new, 7, BASE_LANG[side])
        if "faction_template" in rc:
            chr_base.set_u32(new, 2, rc["faction_template"])
        elif src_side != SIDE_VAL[side]:
            chr_base.set_u32(new, 2, DEFAULT_FACTION[side])
        if chr_base.rs // 4 > 68 and chr_base.u32(new, 68) > 2:
            chr_base.set_u32(new, 68, 0)          # pas d'extension requise (client WotLK)
        names = rc.get("names", {})
        for loc, pair in names.items():
            if loc not in LOCALES:
                log("warn", f"locale inconnue {loc}")
                continue
            i = LOCALES.index(loc)
            for bcol, text in ((14, pair[0]), (31, pair[1]), (48, pair[0])):
                chr_base.set_u32(new, bcol + i, chr_base.add_s(text))
                if chr_base.u32(new, bcol + 16) == 0:
                    chr_base.set_u32(new, bcol + 16, 0xFF01FE)
        loc = cfg.get("locale", "enUS")
        if loc not in names:
            log("warn", f"{rc['name']}: pas de nom pour la locale {loc} dans la config (nom vide en jeu possible)")
        chr_base.recs = [r for r in chr_base.recs if chr_base.u32(r, 0) != did]
        chr_base.recs.append(new)

        if not LUA_TOKEN_RE.fullmatch(token):
            raise ValueError(f"{rc['name']}: ClientFileString invalide pour Lua: {token!r}")
        needed[rc["name"]] = [asset_path(path) for path in asset_list]
        results.append({"name": rc["name"], "source": sid, "target": did, "faction": side, "token": token,
                        "classes": classes, "male_display": chr_base.u32(new, 4), "female_display": chr_base.u32(new, 5),
                        "esteria_token": str(meta.get("client_file", "")).upper(), "rows": counts,
                        "appearance_textures": meta.get("appearance_textures", []) if appearance is not None else [],
                        "folder": rdir.name})
        if swap_sexes:
            results[-1]["swap_model_sexes"] = True
            log("info", f"{rc['name']}: modèles, personnalisations et portraits masculin/féminin permutés")
        if did in replaced:
            results[-1]["replaced_race"] = replaced[did]

        # fichiers (modèles, textures)
        n = repl = ignored = 0
        asset_paths = {p.replace("\\", "/").lower() for p in asset_list}
        if appearance is not None and appearance_rdir is None:
            n, repl = install_appearance_textures(meta, rdir, out, asset_paths)
        asset_root = appearance_rdir if appearance_rdir is not None else rdir
        for f in (asset_root.rglob("*") if appearance is None or appearance_rdir is not None else ()):
            if not f.is_file():
                continue
            rel = f.relative_to(asset_root)
            if rel.parts[0].lower() == "dbfilesclient" or rel.name == "race.json":
                continue
            key = rel.as_posix().lower()
            parent = key.rsplit("/", 1)[0] if "/" in key else ""
            if key not in asset_paths and parent not in asset_dirs:
                ignored += 1
                continue
            t = out / asset_path(rel.as_posix())
            if t.exists():
                repl += 1
                if not cfg.get("overwrite_files", True):
                    continue
            t.parent.mkdir(parents=True, exist_ok=True)
            if namespace is not None and f.suffix.lower() == ".m2":
                model_dependencies(f, rel.as_posix())
                t.write_bytes(remap_model_texture_paths(f.read_bytes(), namespace_paths))
            else:
                shutil.copy2(f, t)
            n += 1
        if ignored:
            log("info", f"{rc['name']}: {ignored} fichiers sans lien avec les displays joueur ignorés "
                        "(ancienne extraction incluant des PNJ possible)")
        log("info", f"{rc['name']}: {sid} -> {did} ({side}), classes {classes}, lignes {counts}, {n} fichiers copiés ({repl} remplacés)")

    toks = {x["token"] for x in results}
    for rel in relocated:
        row = next((r for r in chr_base.recs if chr_base.u32(r, 0) == rel["to"]), None)
        if row is not None:
            cf = chr_base.s(chr_base.u32(row, 11))
            if cf.upper() in toks:
                chr_base.set_u32(row, 11, chr_base.add_s(cf + "Old"))
                log("info", f"race de base déplacée '{rel['name']}' : ClientFileString '{cf}' -> '{cf}Old'")

    # --- 3. langues par faction (Commun / Orc)
    for name, mcol in (("SkillLineAbility", 3), ("SkillRaceClassInfo", 2)):
        db = dbs.get(name)
        if not db:
            continue
        for r in db.recs:
            skill = db.u32(r, 1)
            if skill not in (98, 109):
                continue
            m = db.u32(r, mcol)
            if m in (0, ALL):
                continue
            for x in results:
                m = (m | bit(x["target"])) if LANG_SKILL[x["faction"]] == skill else (m & ~bit(x["target"]))
            db.set_u32(r, mcol, m)

    chr_base.recs.sort(key=lambda r: chr_base.u32(r, 0))
    for db in dbs.values():
        db.save()
    return results, relocated, needed


# --------------------------------------------------------------------------- glue
def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def race_token(name):
    token = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return token or "CUSTOM_RACE"


def write_blp_argb(img, path):
    """Écrit un BLP2 non compressé (ARGB8888, sans perte) avec mipmaps."""
    from PIL import Image
    RES = getattr(Image, "Resampling", Image)
    img = img.convert("RGBA")
    w, h = img.size
    levels, k = [], 0
    while True:
        lw, lh = max(1, w >> k), max(1, h >> k)
        cur = img if k == 0 else img.resize((lw, lh), RES.LANCZOS)
        levels.append(cur.tobytes("raw", "BGRA"))
        if lw == 1 and lh == 1 or k >= 15:
            break
        k += 1
    offs, sizes, pos = [0] * 16, [0] * 16, 1172
    for i, lv in enumerate(levels):
        offs[i], sizes[i] = pos, len(lv)
        pos += len(lv)
    head = b"BLP2" + struct.pack("<IBBBBII", 1, 3, 8, 8, 1 if len(levels) > 1 else 0, w, h)
    head += struct.pack("<16I", *offs) + struct.pack("<16I", *sizes) + b"\0" * 1024
    Path(path).write_bytes(head + b"".join(levels))


def blp_info(d):
    if d[:4] != b"BLP2" or len(d) < 148:
        return None
    _, enc, adepth, aenc, mips, w, h = struct.unpack_from("<IBBBBII", d, 4)
    return {"enc": enc, "w": w, "h": h, "offs": struct.unpack_from("<16I", d, 20), "sizes": struct.unpack_from("<16I", d, 84)}


def save_blp(img, path, manual_dir):
    """Écrit l'atlas. BLP2 ARGB d'origine : réécrit en place (en-tête et mipmaps conservés). Sinon : BLP2 ARGB neuf."""
    manual_dir.mkdir(parents=True, exist_ok=True)
    png = manual_dir / (Path(path).stem + ".png")
    img.save(png)
    try:
        from PIL import Image
        RES = getattr(Image, "Resampling", Image)
        path = Path(path)
        d = path.read_bytes() if path.exists() else b""
        info = blp_info(d)
        if info and info["enc"] == 3 and (info["w"], info["h"]) == img.size:
            buf = bytearray(d)
            for i in range(16):
                off, sz = info["offs"][i], info["sizes"][i]
                lw, lh = max(1, info["w"] >> i), max(1, info["h"] >> i)
                if not sz or lw * lh * 4 != sz or off + sz > len(buf):
                    continue
                cur = img if i == 0 else img.resize((lw, lh), RES.LANCZOS)
                buf[off:off + sz] = cur.convert("RGBA").tobytes("raw", "BGRA")
            path.write_bytes(bytes(buf))
            how = "réécrit sur place (BLP2 ARGB, en-tête conservé)"
        else:
            write_blp_argb(img, path)
            how = "réécrit en BLP2 ARGB non compressé"
        chk = load_blp(path)
        if chk.size != img.size:
            raise ValueError("taille différente après relecture")
        log("info", f"atlas {path.name} {how} ; PNG de contrôle : {png}")
        return True
    except Exception as e:  # noqa
        log("warn", f"écriture BLP impossible ({e}). PNG écrit : {png}. Convertis-le en BLP et place-le sur {path}")
        return False


INCOMPATIBLE_API = re.compile(r"\b(C_CharacterCreate|KeyCommand)\b")


def install_glue_source(cfg, root, out):
    """Remplace Interface/GlueXML du patch par un GlueXML 3.3.5 qui marche sur ton client."""
    src = cfg.get("glue_source")
    if not src:
        return
    sp = Path(src)
    sp = sp if sp.is_absolute() else root / sp
    cand = ci_find(sp, "Interface/GlueXML") or ci_find(sp, "GlueXML") or (sp if ci_find(sp, "CharacterCreate.lua") else None)
    if not cand:
        log("error", f"glue_source : aucun GlueXML trouvé dans {sp}")
        return
    dst = ci_find(out, "Interface/GlueXML") or (out / "Interface" / "GlueXML")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(cand, dst)
    log("info", f"GlueXML remplacé par {cand}")


def check_glue_api(gdir):
    bad = []
    for f in Path(gdir).rglob("*"):
        if f.is_file() and f.suffix.lower() in (".lua", ".xml"):
            if INCOMPATIBLE_API.search(read_text(f)[0]):
                bad.append(f.name)
    if bad:
        log("error", f"GlueXML utilisant des API absentes d'un client 3.3.5 (KeyCommand / C_CharacterCreate dans {sorted(bad)[:8]}). "
                     f"Ces fichiers ne viennent pas du GlueXML Reforged : vérifie la source")


def apply_icon_mask(cell, mask):
    from PIL import ImageChops
    cell = cell.convert("RGBA")
    cell.putalpha(ImageChops.multiply(cell.getchannel("A"), mask))
    return cell


ANCHOR_RE = re.compile(r'<Anchor\b[^>]*relativeTo="CharCreateRaceButton(?:sFrame|\d+)"[^>]*/>')


def make_race_button(tpl, i, anchor, label):
    """Clone un bouton de race existant (modèle) avec un nouvel id / nom / ancre."""
    m = re.match(r'<CheckButton\b[^>]*>', tpl)
    head = re.sub(r'name="[^"]*"', f'name="CharCreateRaceButton{i}"', m.group(0), count=1)
    head = re.sub(r'\bid="[^"]*"', f'id="{i}"', head, count=1)
    body = ANCHOR_RE.sub(lambda _m: anchor, tpl[m.end():], count=1)
    return f"<!-- {label} -->\n\t\t\t\t\t\t\t\t\t{head}{body}"


def inject_race_variant_controls(text):
    if "CharCreateRaceVariantPrevious" in text:
        return text
    panel = re.search(r'<Frame\s+name="CharCreateCustomizationFrame"', text)
    if not panel:
        raise ValueError("CharacterCreate.xml : CharCreateCustomizationFrame introuvable")
    frames = re.search(r"<Frames\b[^>]*>", text[panel.end():])
    if not frames:
        raise ValueError("CharacterCreate.xml : conteneur Frames de personnalisation introuvable")
    start = panel.end() + frames.end()
    depth = 1
    close = None
    for tag in re.finditer(r"</?Frames\b[^>]*>", text[start:]):
        value = tag.group(0)
        if value.startswith("</"):
            depth -= 1
            if depth == 0:
                close = start + tag.start()
                break
        elif not value.endswith("/>"):
            depth += 1
    if close is None:
        raise ValueError("CharacterCreate.xml : fin du conteneur Frames de personnalisation introuvable")
    controls = r'''
							<Frame name="CharCreateRaceVariantRow">
								<Size x="162" y="64"/>
								<Anchors>
									<Anchor point="BOTTOM" relativeTo="CharCreateCustomizationButton1" relativePoint="TOP" x="0" y="0"/>
								</Anchors>
								<Layers>
									<Layer level="ARTWORK">
										<FontString name="CharCreateRaceVariantLabel" inherits="GlueFontHighlightSmall" justifyH="CENTER" hidden="true">
											<Size x="162" y="32"/>
											<Anchors><Anchor point="CENTER"/></Anchors>
										</FontString>
									</Layer>
								</Layers>
								<Scripts>
									<OnLoad>self:SetFrameLevel(CharCreateCustomizationFrame:GetFrameLevel() + 5);</OnLoad>
								</Scripts>
								<Frames>
									<Button name="CharCreateRaceVariantPrevious" hidden="true">
										<Size x="32" y="32"/>
										<Anchors><Anchor point="LEFT" x="-32" y="0"/></Anchors>
										<Scripts>
											<OnClick>MergeRaceVariantStep(-1);</OnClick>
										</Scripts>
										<NormalTexture file="Interface\Buttons\UI-SpellbookIcon-PrevPage-Up"/>
										<PushedTexture file="Interface\Buttons\UI-SpellbookIcon-PrevPage-Down"/>
										<HighlightTexture file="Interface\Buttons\UI-Common-MouseHilight" alphaMode="ADD"/>
									</Button>
									<Button name="CharCreateRaceVariantNext" hidden="true">
										<Size x="32" y="32"/>
										<Anchors><Anchor point="RIGHT" x="32" y="0"/></Anchors>
										<Scripts>
											<OnClick>MergeRaceVariantStep(1);</OnClick>
										</Scripts>
										<NormalTexture file="Interface\Buttons\UI-SpellbookIcon-NextPage-Up"/>
										<PushedTexture file="Interface\Buttons\UI-SpellbookIcon-NextPage-Down"/>
										<HighlightTexture file="Interface\Buttons\UI-Common-MouseHilight" alphaMode="ADD"/>
									</Button>
								</Frames>
							</Frame>
'''
    return text[:close] + controls + text[close:]


def race_button_order(ids, order, faction, names):
    key = f"glue.race_order.{faction}"
    if not isinstance(order, list) or any(not isinstance(name, str) for name in order):
        raise ValueError(f"{key} doit être une liste de noms de races")

    def normalized(name):
        value = re.sub(r"[\s_]+", "", name).casefold()
        return "scourge" if value == "undead" else value

    lookup = {}
    for rid in ids:
        lookup.setdefault(normalized(names[rid]), []).append(rid)
    resolved = []
    for name in order:
        matches = lookup.get(normalized(name), [])
        if not matches:
            raise ValueError(f"{key} : race inconnue, non jouable ou hors faction : {name!r}")
        if len(matches) != 1:
            raise ValueError(f"{key} : nom de race ambigu {name!r} (IDs {matches})")
        if matches[0] in resolved:
            raise ValueError(f"{key} : race en double {name!r}")
        resolved.append(matches[0])
    return resolved + [rid for rid in ids if rid not in resolved]


def race_name_ids(ids, names, requested, key):
    if not isinstance(requested, list) or any(not isinstance(name, str) for name in requested):
        raise ValueError(f"{key} doit être une liste de noms de races")

    def normalized(name):
        return re.sub(r"[\s_]+", "", name).casefold()

    lookup = {}
    for rid in ids:
        lookup.setdefault(normalized(names[rid]), []).append(rid)
    resolved = []
    for name in requested:
        matches = lookup.get(normalized(name), [])
        if not matches:
            raise ValueError(f"{key} : race inconnue ou non jouable : {name!r}")
        if len(matches) != 1:
            raise ValueError(f"{key} : nom de race ambigu {name!r} (IDs {matches})")
        if matches[0] in resolved:
            raise ValueError(f"{key} : race en double {name!r}")
        resolved.append(matches[0])
    return resolved


def variant_model_sexes(dbs, rid, out):
    races = dbs["ChrRaces"]
    row = next(r for r in races.recs if races.u32(r, 0) == rid)
    displays, models, _ = player_rows(dbs, races.u32(row, 4), races.u32(row, 5))
    cdi, cmd = dbs["CreatureDisplayInfo"], dbs["CreatureModelData"]
    paths = {}
    for sex, col in ((0, 4), (1, 5)):
        display = next(r for r in displays if cdi.u32(r, 0) == races.u32(row, col))
        model = next(r for r in models if cmd.u32(r, 0) == cdi.u32(display, 1))
        path = model_path(cmd.s(cmd.u32(model, 2)))
        file = ci_find(out, path)
        if file and file.is_file():
            paths[sex] = path.lower()
    if paths.get(1) == paths.get(0) or "/male/" in paths.get(1, ""):
        paths.pop(1, None)
    if "/female/" in paths.get(0, ""):
        paths.pop(0, None)
    return sorted(paths)


def patch_runtime_race_layout(text, columns, top, gap, inset, hidden_tokens=(), variant_groups=(),
                             variant_sexes=None):
    if not re.search(r"(?m)^function\s+CharacterCreateEnumerateRaces\s*\(\s*\.\.\.\s*\)", text):
        raise ValueError("CharacterCreate.lua : CharacterCreateEnumerateRaces(...) introuvable")
    begin = "-- [merge_races] race layout begin"
    end = "-- [merge_races] race layout end"
    text = re.sub(r"\n" + re.escape(begin) + r"\n.*?\n" + re.escape(end) + r"\n?", "\n", text, flags=re.S)
    orders = ",\n".join("\t{ " + ", ".join(lua_str(token.upper()) for token in column) + " }"
                        for column in columns)
    hidden = ", ".join(f"[{lua_str(token.upper())}] = true" for token in hidden_tokens)
    variants = ",\n".join("\t{ " + ", ".join(lua_str(token.upper()) for token in group) + " }"
                          for group in variant_groups)
    sexes = ",\n".join(
        f"\t[{lua_str(token)}] = {{ "
        + ", ".join(f"[{'SEX_MALE' if sex == 0 else 'SEX_FEMALE'}] = true" for sex in supported) + " }"
        for token, supported in (variant_sexes or {}).items())
    return text.rstrip() + f"""

{begin}
local mergeRaceColumns = {{
{orders}
}};
local mergeRaceVariantHidden = {{ {hidden} }};
local mergeRaceVariantGroups = {{
{variants}
}};
local mergeRaceVariantSexes = {{
{sexes}
}};
local mergeRaceVariantByIndex = {{}};
local mergeRaceVariantNames = {{}};
local mergeRaceVariantBaseByIndex = {{}};
local mergeRaceTokensByIndex = {{}};

local function MergeRaceSupportsSex(index, sex)
    local supported = mergeRaceVariantSexes[mergeRaceTokensByIndex[index]];
    return not supported or supported[sex];
end

local function MergeCustomizationLayout()
    local previous;
    for index = 1, NUM_CHAR_CUSTOMIZATIONS do
        local button = _G["CharCreateCustomizationButton"..index];
        button:ClearAllPoints();
        if ( button:IsShown() ) then
            if ( previous ) then
                button:SetPoint("TOP", previous, "BOTTOM", 0, 0);
            else
                button:SetPoint("TOP", CharCreateCustomizationFrame, "TOP", 0, -15);
            end
            previous = button;
        end
    end
    if ( previous ) then
        CharCreateRandomizeButton:ClearAllPoints();
        CharCreateRandomizeButton:SetPoint("TOP", _G[previous:GetName().."RightButton"], "BOTTOM", -8, 0);
    end
end

local function MergeRaceVariantUpdate()
    if ( not CharCreateRaceVariantPrevious ) then return; end
    local variant = mergeRaceVariantByIndex[GetSelectedRace()];
    if ( not variant or not CharCreateCustomizationFrame:IsShown() ) then
        CharCreateRaceVariantPrevious:Hide();
        CharCreateRaceVariantNext:Hide();
        CharCreateRaceVariantLabel:Hide();
        return;
    end
    CharCreateRaceVariantPrevious:Show();
    CharCreateRaceVariantNext:Show();
    CharCreateRaceVariantLabel:SetText(mergeRaceVariantNames[GetSelectedRace()] or "");
    CharCreateRaceVariantLabel:Show();
end

function MergeRaceVariantStep(delta)
    local variant = mergeRaceVariantByIndex[GetSelectedRace()];
    if ( not variant ) then return; end
    local position = variant.position + delta;
    if ( position < 1 ) then
        position = table.getn(variant.indices);
    elseif ( position > table.getn(variant.indices) ) then
        position = 1;
    end
    local target = variant.indices[position];
    local button = _G["CharCreateRaceButton"..target];
    if ( button and button:IsEnabled() ) then
        CharacterRace_OnClick(button, target, true);
    end
end

local mergeEnumerateRaces = CharacterCreateEnumerateRaces;
function CharacterCreateEnumerateRaces(...)
    mergeEnumerateRaces(...);
    local count = select("#", ...) / 3;
    if ( count > MAX_RACES ) then return; end
    local buttons = {{}};
    local indices = {{}};
    mergeRaceVariantByIndex = {{}};
    mergeRaceVariantNames = {{}};
    mergeRaceVariantBaseByIndex = {{}};
    mergeRaceTokensByIndex = {{}};
    for index = 1, count do
        local token = strupper(select(index * 3 - 1, ...));
        buttons[token] = _G["CharCreateRaceButton"..index];
        indices[token] = index;
        mergeRaceTokensByIndex[index] = token;
        mergeRaceVariantNames[index] = select(index * 3 - 2, ...);
    end
    for token in pairs(mergeRaceVariantHidden) do
        local button = buttons[token];
        if ( button ) then
            button:Hide();
            buttons[token] = nil;
        end
    end
    for _, group in ipairs(mergeRaceVariantGroups) do
        local groupIndices = {{}};
        for _, token in ipairs(group) do
            local index = indices[token];
            if ( index ) then
                mergeRaceVariantBaseByIndex[index] = indices[group[1]];
                if ( MergeRaceSupportsSex(index, GetSelectedSex()) ) then
                    table.insert(groupIndices, index);
                end
            end
        end
        if ( table.getn(groupIndices) > 1 ) then
            for position, index in ipairs(groupIndices) do
                mergeRaceVariantByIndex[index] = {{indices = groupIndices, position = position}};
            end
        end
    end
    for column, tokens in ipairs(mergeRaceColumns) do
        local point = column == 1 and "TOPLEFT" or "TOPRIGHT";
        local x = column == 1 and {inset} or {-inset};
        local y = {top};
        for _, token in ipairs(tokens) do
            local button = buttons[token];
            if ( button ) then
                button:ClearAllPoints();
                button:SetPoint(point, CharCreateRaceButtonsFrame, point, x, y);
                button:Show();
                y = y - button:GetHeight() + {gap};
                buttons[token] = nil;
            end
        end
    end
    for token in pairs(buttons) do
        message("[merge_races] Race absente de la disposition : "..token..". Relancer merge_races.py.");
    end
    MergeRaceVariantUpdate();
end

local mergeCharacterCreateOnShow = CharacterCreate_OnShow;
function CharacterCreate_OnShow()
    mergeCharacterCreateOnShow();
    MergeRaceVariantUpdate();
end

local mergeCustomizationFrameOnShow = CharCreateCustomizationFrame_OnShow;
function CharCreateCustomizationFrame_OnShow()
    mergeCustomizationFrameOnShow();
    CharacterCreate_UpdateHairCustomization();
    MergeRaceVariantUpdate();
end

local mergeUpdateHairCustomization = CharacterCreate_UpdateHairCustomization;
function CharacterCreate_UpdateHairCustomization()
    mergeUpdateHairCustomization();
    MergeCustomizationLayout();
end

local mergeSetCharacterGender = SetCharacterGender;
function SetCharacterGender(sex)
    local index = GetSelectedRace();
    local base = mergeRaceVariantBaseByIndex[index];
    if ( base and not MergeRaceSupportsSex(index, sex) ) then
        SetSelectedRace(base);
    end
    mergeSetCharacterGender(sex);
    MergeRaceVariantUpdate();
end

local mergeCharacterRaceOnClick = CharacterRace_OnClick;
function CharacterRace_OnClick(self, id, forceSelect)
    mergeCharacterRaceOnClick(self, id, forceSelect);
    MergeRaceVariantUpdate();
end

local mergeCharacterCreateForward = CharacterCreate_Forward;
function CharacterCreate_Forward()
    mergeCharacterCreateForward();
    MergeRaceVariantUpdate();
end

local mergeCharacterCreateBack = CharacterCreate_Back;
function CharacterCreate_Back()
    mergeCharacterCreateBack();
    MergeRaceVariantUpdate();
end

local mergeCharacterCreateRandomize = CharacterCreate_Randomize;
function CharacterCreate_Randomize()
    local variant = mergeRaceVariantByIndex[GetSelectedRace()];
    if ( variant ) then
        local position = math.random(1, table.getn(variant.indices));
        local target = variant.indices[position];
        local button = _G["CharCreateRaceButton"..target];
        if ( target ~= GetSelectedRace() and button and button:IsEnabled() ) then
            CharacterRace_OnClick(button, target, true);
        end
    end
    mergeCharacterCreateRandomize();
    MergeRaceVariantUpdate();
end
{end}
"""


def make_scaled_zoom_background(root, out, patterns, src_bg, dst_bg, scale):
    """Crée ui_<dst_bg>_zoom : copie de ui_<src_bg>_zoom (m2 + skins) dont la caméra est
    rapprochée du personnage (position et cible multipliées par `scale`, le personnage
    étant à l'origine de la scène). Le décor reste celui de src_bg."""
    src, dst = f"ui_{src_bg.lower()}_zoom", f"ui_{dst_bg.lower()}_zoom"
    rel = f"Interface/Glues/Models/{src}"
    roots = ([Path(out), *hd_asset_roots(root)]
             + [p for pat in patterns for p in Path(root).glob(pat) if p.is_dir()])
    files = {}
    for r in dict.fromkeys(roots):
        d = ci_find(r, rel)
        if d and d.is_dir():
            for f in d.iterdir():
                if f.is_file():
                    files.setdefault(f.name.lower(), f)
    m2 = files.get(src + ".m2")
    if not m2:
        return False
    ddir = Path(out) / "Interface" / "Glues" / "Models" / dst
    ddir.mkdir(parents=True, exist_ok=True)
    for lname, f in files.items():
        new = dst + lname[len(src):] if lname.startswith(src) else lname
        if new == dst + ".m2":
            data = bytearray(f.read_bytes())
            hdr = 8 + 4 * 38 + 14 * 4          # début des compteurs après les boîtes englobantes
            n_cam, ofs_cam = struct.unpack_from("<II", data, hdr + 14 * 4)
            if data[:4] != b"MD20" or n_cam < 1:
                raise ValueError(f"{f.name}: M2 sans caméra, zoom impossible")
            for i in range(n_cam):
                o = ofs_cam + i * 0x64
                for off in (o + 36, o + 68):   # position de base, cible de base
                    v = struct.unpack_from("<3f", data, off)
                    struct.pack_into("<3f", data, off, *(c * scale for c in v))
            (ddir / new).write_bytes(data)
        else:
            shutil.copy2(f, ddir / new)
    return True


def patch_glue(cfg, root, out, results, dbs, needed_unused=None):
    install_glue_source(cfg, root, out)
    gdir = ci_find(out, "Interface/GlueXML")
    manual = out.parent / "_manual"
    if not gdir:
        log("warn", "Interface/GlueXML absent de la base : glue ignoré")
        return
    check_glue_api(gdir)
    chr_db, cbi = dbs["ChrRaces"], dbs["CharBaseInfo"]
    side = {chr_db.u32(r, 0): chr_db.u32(r, 13) for r in chr_db.recs}
    fname = {chr_db.u32(r, 0): chr_db.s(chr_db.u32(r, 11)) for r in chr_db.recs}
    playable = sorted({r[0] for r in cbi.recs})
    ally = [i for i in playable if side.get(i) == 0]
    horde = [i for i in playable if side.get(i) == 1]
    n_slots = len(ally) + len(horde)
    slot = {rid: i + 1 for i, rid in enumerate(ally + horde)}
    log("info", f"slots de la création de perso : Alliance {ally} / Horde {horde} (MAX_RACES={n_slots})")
    log("info", "disposition réappliquée à l'exécution selon les tokens de GetAvailableRaces ; IDs de boutons conservés")
    for x in results:
        x["slot"] = slot.get(x["target"])
    gl = cfg.get("glue", {})
    order = gl.get("race_order", {})
    if not isinstance(order, dict) or set(order) - {"Alliance", "Horde"}:
        raise ValueError("glue.race_order doit être un objet avec les clés Alliance et/ou Horde")
    names = {**fname, **{x["target"]: x["name"] for x in results}}
    hidden_ids = race_name_ids(playable, names, gl.get("hidden_races", []), "glue.hidden_races")
    variant_groups = gl.get("race_variants", [])
    if not isinstance(variant_groups, list):
        raise ValueError("glue.race_variants doit être une liste de groupes de races")
    variant_ids, variant_base_ids, variant_tokens = set(), set(), []
    variant_sexes = {}
    tokens = {rid: fname[rid].upper() for rid in playable}
    tokens.update({x["target"]: x["token"] for x in results})
    for index, group in enumerate(variant_groups, 1):
        ids = race_name_ids(playable, names, group, f"glue.race_variants[{index}]")
        if len(ids) < 2:
            raise ValueError(f"glue.race_variants[{index}] doit contenir au moins deux races")
        if len({side.get(rid) for rid in ids}) != 1:
            raise ValueError(f"glue.race_variants[{index}] doit rester dans une seule faction")
        if ids[0] in hidden_ids or any(rid not in hidden_ids for rid in ids[1:]):
            raise ValueError(f"glue.race_variants[{index}] : seules les variantes après la première "
                             "doivent être listées dans glue.hidden_races")
        if variant_ids.intersection(ids):
            raise ValueError(f"glue.race_variants[{index}] partage une race avec un autre groupe")
        variant_ids.update(ids)
        variant_base_ids.add(ids[0])
        variant_tokens.append([tokens[rid] for rid in ids])
        for rid in ids[1:]:
            supported = variant_model_sexes(dbs, rid, out)
            if not supported:
                raise ValueError(f"{names[rid]} : aucun modèle joueur disponible dans le patch ou sa base")
            variant_sexes[tokens[rid]] = supported
            if 1 not in supported:
                log("warn", f"{names[rid]} : modèle féminin distinct absent ; variante masquée pour les femmes")
    if set(hidden_ids) != variant_ids - variant_base_ids:
        raise ValueError("glue.hidden_races doit contenir exactement les variantes des groupes glue.race_variants")
    hidden_tokens = [tokens[rid] for rid in hidden_ids]
    layout_ally_all = race_button_order(ally, order["Alliance"], "Alliance", names) if "Alliance" in order else ally
    layout_horde_all = race_button_order(horde, order["Horde"], "Horde", names) if "Horde" in order else horde
    layout_ally = [rid for rid in layout_ally_all if rid not in hidden_ids]
    layout_horde = [rid for rid in layout_horde_all if rid not in hidden_ids]
    log("info", f"ordre visuel des races : Alliance {layout_ally} / Horde {layout_horde}")
    top = gl.get("top_y", -75)
    gap = gl.get("gap", -30 if max(len(ally), len(horde)) <= 5 else -22)
    x0 = gl.get("x", 32)
    for key, value in (("top_y", top), ("gap", gap), ("x", x0)):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"glue.{key} doit être un nombre fini")
    hd_patterns = [p.relative_to(root).as_posix() for p in hd_asset_roots(root)]
    files_idx = index_assets(root, out, hd_patterns + cfg.get("asset_roots", []))
    manual.mkdir(parents=True, exist_ok=True)

    # ---------------- CharacterCreate.lua
    p = ci_find(gdir, "CharacterCreate.lua")
    placements, base_ents, atlas_scale = [], {}, 1
    if p:
        text, enc, crlf = read_text(p)
        text, n = re.subn(r"(?m)^MAX_RACES\s*=\s*\d+[ \t]*;?",
                          lambda m: f"MAX_RACES = {n_slots};\nNUM_ALLIANCE_RACES = {len(ally)};", text, count=1)
        if not n:
            log("warn", "CharacterCreate.lua : MAX_RACES introuvable")
        # changement de race payant : la coupure Alliance/Horde était codée en dur sur MAX_RACES
        old = "(fact < MAX_RACES and i < MAX_RACES) or (fact > (MAX_RACES-1) and i > (MAX_RACES-1))"
        if old in text:
            text = text.replace(old, "(fact <= NUM_ALLIANCE_RACES and i <= NUM_ALLIANCE_RACES) or "
                                     "(fact > NUM_ALLIANCE_RACES and i > NUM_ALLIANCE_RACES)")
        m = re.search(r"RACE_ICON_TCOORDS\s*=\s*\{(.*?)\n[ \t]*\}[ \t]*;?", text, re.S)
        if not m:
            log("warn", "CharacterCreate.lua : table RACE_ICON_TCOORDS introuvable (icônes non ajoutées)")
        else:
            body = m.group(1)
            base_ents = {k.upper(): tuple(float(v) for v in vals) for k, *vals in TC_RE.findall(body)}
            need = [k for k in ("HUMAN_MALE", "ORC_MALE", "HUMAN_FEMALE", "ORC_FEMALE") if k not in base_ents]
            if need:
                log("warn", f"RACE_ICON_TCOORDS : entrées de référence manquantes {need}")
            else:
                w = base_ents["HUMAN_MALE"][1] - base_ents["HUMAN_MALE"][0]
                k0 = max(round(v[1] / w) for v in base_ents.values())
                rows = {("Alliance", "MALE"): base_ents["HUMAN_MALE"][2:], ("Horde", "MALE"): base_ents["ORC_MALE"][2:],
                        ("Alliance", "FEMALE"): base_ents["HUMAN_FEMALE"][2:], ("Horde", "FEMALE"): base_ents["ORC_FEMALE"][2:]}
                added = {
                    faction: sum(x["faction"] == faction and x["target"] not in hidden_ids
                                 and f'{x["token"]}_MALE' not in base_ents for x in results)
                    for faction in SIDE_VAL
                }
                while (k0 + max(added.values())) * w > atlas_scale + 0.0001:
                    atlas_scale *= 2
                if atlas_scale > 1:
                    def scaled_coords(match):
                        key, left, right, top_, bottom = match.groups()
                        return (f'["{key}"] = {{{float(left) / atlas_scale:.6g}, '
                                f'{float(right) / atlas_scale:.6g}, {top_}, {bottom}}}')
                    body = TC_RE.sub(scaled_coords, body)
                nxt = {"Alliance": k0, "Horde": k0}
                lines = []
                for x in results:
                    if f'{x["token"]}_MALE' in base_ents:
                        log("warn", f"{x['name']}: le token {x['token']} existe déjà dans RACE_ICON_TCOORDS (icône non ajoutée)")
                        continue
                    if x["target"] in hidden_ids:
                        rc = next(r for r in cfg["races"] if r["name"] == x["name"])
                        fallback = rc.get("icon_fallback", "HUMAN").upper()
                        for g in ("MALE", "FEMALE"):
                            coords = base_ents.get(f"{fallback}_{g}")
                            if coords is None:
                                raise ValueError(f"{x['name']}: icône {fallback} de référence absente")
                            l, r_, t, b = coords
                            lines.append(f'\t["{x["token"]}_{g}"]\t= {{{l / atlas_scale:.6g}, {r_ / atlas_scale:.6g}, {t:.6g}, {b:.6g}}},')
                        continue
                    col = nxt[x["faction"]]
                    nxt[x["faction"]] += 1
                    l, r_ = col * w, (col + 1) * w
                    for g in ("MALE", "FEMALE"):
                        t, b = rows[(x["faction"], g)]
                        lines.append(f'\t["{x["token"]}_{g}"]\t= {{{l / atlas_scale:.6g}, {r_ / atlas_scale:.6g}, {t:.6g}, {b:.6g}}},')
                        placements.append({"race": x, "gender": g, "box": (l, r_, t, b)})
                ins = ("" if body.rstrip().endswith(",") else ",") + "\n\n" + "\n".join(lines)
                text = text[:m.start(1)] + body.rstrip() + ins + text[m.end(1):]
        text = patch_runtime_race_layout(
            text, [[tokens[rid] for rid in ids] for ids in (layout_ally, layout_horde)], top, gap, x0,
            hidden_tokens, variant_tokens, variant_sexes)
        write_text(p, text, enc, crlf)
    else:
        log("warn", "CharacterCreate.lua introuvable")

    # ---------------- CharacterCreate.xml (boutons CharCreateRaceButtonN, Alliance à gauche / Horde à droite)
    atlas_rel = None
    p = ci_find(gdir, "CharacterCreate.xml")
    if p:
        text, enc, crlf = read_text(p)
        if "RaceStrings.lua" not in text:
            text, n = re.subn(r'(<Script\s+file="CharacterCreate\.lua"\s*/>)',
                              lambda m: '<Script file="RaceStrings.lua"/>\n\t' + m.group(1), text, count=1)
            if not n:
                log("warn", "CharacterCreate.xml : <Script file=\"CharacterCreate.lua\"/> introuvable, RaceStrings.lua non chargé")
        if variant_groups:
            text = inject_race_variant_controls(text)
        tm = re.search(r'<CheckButton\s+name="CharCreateRaceButtonTemplate".*?</CheckButton>', text, re.S)
        if tm:
            nt = re.search(r'<NormalTexture\b[^>]*\bfile="([^"]+)"', tm.group(0))
            if nt:
                atlas_rel = nt.group(1).replace("\\", "/")
        spans = list(re.finditer(r'<CheckButton\s+name="CharCreateRaceButton(\d+)"[^>]*>.*?</CheckButton>', text, re.S))
        tpl_a = next((s.group(0) for s in spans if "<Scripts>" not in s.group(0) and "<Frames>" not in s.group(0)), None)
        tpl_h = next((s.group(0) for s in spans if "<Scripts>" in s.group(0)), None)
        if not spans or not tpl_a or not tpl_h:
            diag = [l for l in text.split("\n") if "RaceButton" in l][:80]
            (manual / "race-button-diagnostic.txt").write_text("\n".join(diag), encoding="utf-8")
            log("warn", "CharacterCreate.xml : boutons de races (CharCreateRaceButtonN) ou modèles Alliance/Horde introuvables, "
                        "disposition inchangée (voir _manual/race-button-diagnostic.txt)")
        else:
            blocks = []
            for ids, tpl, first in ((layout_ally_all, tpl_a, f'<Anchor point="TOPLEFT" relativeTo="CharCreateRaceButtonsFrame" x="{x0}" y="{top}"/>'),
                                    (layout_horde_all, tpl_h, f'<Anchor point="TOPRIGHT" relativeTo="CharCreateRaceButtonsFrame" x="{-x0}" y="{top}"/>')):
                for k, rid in enumerate(ids):
                    a = first if k == 0 else (f'<Anchor point="TOPLEFT" relativeTo="CharCreateRaceButton{slot[ids[k - 1]]}" '
                                              f'relativePoint="BOTTOMLEFT" x="0" y="{gap}"/>')
                    blocks.append(make_race_button(tpl, slot[rid], a, f"slot {slot[rid]} : race {rid} ({fname.get(rid, '?')})"))
            start = spans[0].start()
            cm = re.search(r'<!--[^>]*-->\s*$', text[:start])
            if cm:
                start = cm.start()
            text = text[:start] + "\n\n\t\t\t\t\t\t\t\t\t".join(blocks) + text[spans[-1].end():]
            log("info", f"boutons de races régénérés : {len(layout_ally)} Alliance (gauche) / "
                        f"{len(layout_horde)} Horde (droite), espacement {gap}")
        write_text(p, text, enc, crlf)
    else:
        log("warn", "CharacterCreate.xml introuvable")

    # ---------------- GlueParent.lua : fond / ambiance / lumières des nouvelles races (= ceux d'une race existante)
    p = ci_find(gdir, "GlueParent.lua")
    if p:
        text, enc, crlf = read_text(p)
        mp = re.search(r"(?m)^function\s+SetBackgroundModel\s*\(\s*model\s*,\s*name\s*\)[^\n]*\n", text)
        if mp:
            pairs, zoom_pairs = [], []
            for x in results:
                rc = next(r for r in cfg["races"] if r["name"] == x["name"])
                bg = rc.get("background", "Human")
                zoom_bg = rc.get("zoom_background", bg)
                for key, value in (("background", bg), ("zoom_background", zoom_bg)):
                    if not isinstance(value, str) or not LUA_TOKEN_RE.fullmatch(value):
                        raise ValueError(f"{x['name']}.{key} doit être un nom de fond valide (ex. Gnome)")
                if "zoom_camera_scale" in rc:
                    # fond zoom = décor de zoom_background, caméra rapprochée : modèle ui_<token>_zoom généré
                    scale = float(rc["zoom_camera_scale"])
                    new_zoom = x["token"].lower()
                    if make_scaled_zoom_background(root, out, cfg.get("asset_roots", []), zoom_bg, new_zoom, scale):
                        files_idx.add(f"interface/glues/models/ui_{new_zoom}_zoom/ui_{new_zoom}_zoom.m2")
                        log("info", f"{x['name']}: ui_{new_zoom}_zoom créé (décor {zoom_bg}, caméra x{scale})")
                        zoom_bg = new_zoom
                    else:
                        log("warn", f"{x['name']}: ui_{zoom_bg.lower()}_zoom introuvable, zoom_camera_scale ignoré")
                bg, zoom_bg = bg.upper(), zoom_bg.upper()
                pairs.append(f'["{x["token"]}"] = "{bg}"')
                if "zoom_background" in rc:
                    zoom_pairs.append(f'["{x["token"]}"] = "{zoom_bg}"')
                for background, suffix in ((bg, ""), (zoom_bg, "_zoom")):
                    f = f"interface/glues/models/ui_{background.lower()}{suffix}/ui_{background.lower()}{suffix}.m2"
                    if f not in files_idx:
                        key = "zoom_background" if suffix else "background"
                        log("warn", f"{x['name']}: modèle de fond introuvable ({f}) ; change '{key}' dans la config")
            tables = ("RACE_BACKGROUND_MAP = { " + ", ".join(pairs) + " };\n"
                      "RACE_ZOOM_BACKGROUND_MAP = { " + ", ".join(zoom_pairs) + " };\n")
            prefix = ('\tlocal zoomSuffix = "";\n'
                      "\tlocal baseName = strupper(name);\n"
                      '\tif ( string.find(baseName, "_ZOOM$") ) then baseName = string.gsub(baseName, "_ZOOM$", ""); zoomSuffix = "_ZOOM"; end\n')
            old_body = prefix + "\tif ( RACE_BACKGROUND_MAP[baseName] ) then name = RACE_BACKGROUND_MAP[baseName]..zoomSuffix; end\n"
            body = (prefix
                    + '\tlocal background = (zoomSuffix ~= "" and RACE_ZOOM_BACKGROUND_MAP[baseName]) or RACE_BACKGROUND_MAP[baseName];\n'
                    + "\tif ( background ) then name = background..zoomSuffix; end\n")
            if "RACE_BACKGROUND_MAP" in text:
                if old_body in text:
                    text = text.replace(old_body, body, 1)
                elif body not in text:
                    raise ValueError("GlueParent.lua : ancien patch de fond non reconnu")
                text, count = re.subn(
                    r"(?m)^RACE_BACKGROUND_MAP = \{[^\n]*\};\n"
                    r"(?:RACE_ZOOM_BACKGROUND_MAP = \{[^\n]*\};\n)?",
                    lambda match: tables, text, count=1)
                if count != 1:
                    raise ValueError("GlueParent.lua : tables de fonds existantes non reconnues")
            else:
                defn = ("-- [merge_races] fonds normaux et zoom des races ajoutées\n" + tables + "\n")
                text = text[:mp.start()] + defn + text[mp.start():mp.end()] + body + text[mp.end():]
            write_text(p, text, enc, crlf)
        else:
            log("warn", "GlueParent.lua : SetBackgroundModel(model, name) introuvable (fond des nouvelles races non géré)")
    else:
        log("warn", "GlueParent.lua introuvable")

    # ---------------- RaceStrings.lua (textes de la locale du client)
    L = ["-- généré par merge_races.py : textes de création de personnage pour les races ajoutées",
         "-- (chargé depuis CharacterCreate.xml, donc sans écraser GlueStrings.lua de la locale)"]
    for x in results:
        rc = next(r for r in cfg["races"] if r["name"] == x["name"])
        info = rc.get("info", "")
        L.append(f'RACE_INFO_{x["token"]} = {lua_str(info)};')
        L.append(f'RACE_INFO_{x["token"]}_FEMALE = {lua_str(rc.get("info_female", info))};')
        # le glue boucle jusqu'au premier nil : pas de lignes vides
        for i, t in enumerate([t for t in (rc.get("abilities") or []) if t]):
            L.append(f'ABILITY_INFO_{x["token"]}{i + 1} = {lua_str(t)};')
    (Path(gdir) / "RaceStrings.lua").write_text("\n".join(L) + "\n", encoding="utf-8")

    # ---------------- atlas des icônes
    expanded_atlas = patch_atlas(cfg, root, out, placements, base_ents, manual, atlas_rel, atlas_scale)
    if expanded_atlas:
        original, expanded = expanded_atlas
        p = ci_find(gdir, "CharacterCreate.xml")
        if p is None:
            raise FileNotFoundError("CharacterCreate.xml absent : impossible d'utiliser l'atlas agrandi")
        text, enc, crlf = read_text(p)

        def expanded_texture(match):
            if match[1].replace("\\", "/").lower().removesuffix(".blp") == original.lower().removesuffix(".blp"):
                return 'file="' + expanded.replace("/", "\\") + '"'
            return match[0]

        updated = re.sub(r'\bfile="([^"]+)"', expanded_texture, text)
        if updated == text:
            raise ValueError("CharacterCreate.xml : texture de l'atlas à agrandir introuvable")
        write_text(p, updated, enc, crlf)


def extracted_portrait(cfg, root, race, gender):
    folder = root / cfg["races_dir"] / race["folder"]
    meta = json.loads((folder / "race.json").read_text(encoding="utf-8"))
    source_gender = gender.lower()
    if race.get("swap_model_sexes"):
        source_gender = "female" if source_gender == "male" else "male"
    entry = meta.get("portraits", {}).get(source_gender)
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
        raise ValueError(f"{race['name']} ({gender}): portrait extrait absent dans {folder} ; "
                         "relance extract_races.py --portraits-only")
    path = folder / entry["path"]
    if not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError(f"{race['name']} ({gender}): chemin de portrait hors du dossier de race : {path}")
    if not path.is_file():
        raise FileNotFoundError(f"{race['name']} ({gender}): portrait extrait introuvable : {path}")
    if entry.get("shared"):
        if gender.lower() == "female":
            raise ValueError(f"{race['name']}: portrait féminin dédié requis ; "
                             "le portrait commun ne peut pas remplacer le sexe féminin")
        log("warn", f"{race['name']} ({gender}): portrait commun aux deux sexes ; "
                    "aucune variante propre à ce sexe identifiée à l'extraction")
    return path


def patch_atlas(cfg, root, out, placements, base_ents, manual, atlas_rel=None, width_scale=1):
    if not placements:
        return
    from PIL import Image
    RES = getattr(Image, "Resampling", Image)
    # atlas réellement utilisé par le bouton de race (Reforged : UI-CHARACTERCREATE-RACES_Round)
    cands = []
    if atlas_rel:
        cands.append(atlas_rel if re.search(r"\.\w+$", atlas_rel) else atlas_rel + ".blp")
    cands += ["Interface/Glues/CharacterCreate/UI-CharacterCreate-Races_Round.blp",
              "Interface/Glues/CharacterCreate/UI-CharacterCreate-Races.blp"]
    ap = next((ci_find(out, c) for c in cands if ci_find(out, c) and ci_find(out, c).is_file()), None)
    if not ap:
        raise FileNotFoundError(f"atlas d'icônes de races introuvable dans la base ({cands[0]})")
    log("info", f"atlas d'icônes de races : {ap.name}")
    atlas = load_blp(ap)
    W, H = atlas.size
    source_atlas = atlas
    expanded = None
    if width_scale > 1:
        atlas = Image.new("RGBA", (W * width_scale, H))
        atlas.paste(source_atlas, (0, 0))
        original = ap.relative_to(out).as_posix()
        ap = ap.with_name(ap.stem + "-Merged" + ap.suffix)
        expanded = original, ap.relative_to(out).as_posix()
        log("info", f"atlas de création agrandi : {W}x{H} -> {atlas.width}x{H} ; atlas d'origine conservé")
    gl = cfg.get("glue", {})
    round_icons = gl.get("round_icons", "round" in ap.name.lower())
    rcfg = {r["name"]: r for r in cfg["races"]}
    source_images = {}
    for pl in placements:
        x, g = pl["race"], pl["gender"]
        rc = rcfg[x["name"]]
        if "icons" in rc:
            raise ValueError(f"{x['name']}: 'icons' dans la config est obsolète ; "
                             "extrais les portraits dans le dossier de race avec extract_races.py")
        path = extracted_portrait(cfg, root, x, g)
        img = load_blp(path)
        if not img.getchannel("A").getbbox():
            raise ValueError(f"{path}: portrait extrait vide")
        l, r_, t, b = pl["box"]
        box = (round(l * W), round(t * H), round(r_ * W), round(b * H))
        size = (box[2] - box[0], box[3] - box[1])
        if img.width < size[0] or img.height < size[1]:
            raise ValueError(f"{path}: portrait trop petit ({img.width}x{img.height}) pour la cellule "
                             f"{size[0]}x{size[1]} ; fournir un portrait HD, pas une icône LD agrandie")
        other_gender = "FEMALE" if g == "MALE" else "MALE"
        other = source_images.get((x["folder"], other_gender))
        if other is not None and img.size == other.size and img.tobytes() == other.tobytes():
            raise ValueError(f"{x['name']}: les portraits male et female sont identiques")
        source_images[(x["folder"], g)] = img
        cell = img.resize(size, RES.LANCZOS)
        if round_icons:
            fallback = rc.get("icon_fallback", "HUMAN").upper()
            shape = base_ents.get(f"{fallback}_{g}")
            if shape is None:
                shape = base_ents.get(f"HUMAN_{g}")
            if shape is not None:
                shape = crop_frac(source_atlas, *shape).getchannel("A")
                shape = shape.resize(cell.size, RES.LANCZOS)
                cell = apply_icon_mask(cell, shape)
        atlas.paste(cell, box[:2])
        log("info", f"icône {x['token']}_{g} <- {path.relative_to(root)}")
    if not save_blp(atlas, ap, manual):
        raise RuntimeError(f"échec de l'écriture de l'atlas des portraits : {ap}")
    return expanded


# --------------------------------------------------------------------------- vérifications + rapport
def index_assets(root, out, patterns):
    idx = set()
    roots = [out]
    for pat in patterns:
        roots += [p for p in root.glob(pat) if p.is_dir()]
    for r in dict.fromkeys(roots):
        for f in r.rglob("*"):
            if f.is_file():
                idx.add(str(f.relative_to(r)).replace("\\", "/").lower())
    return idx


def hd_asset_roots(root):
    hd = Path(root) / "01-HD"
    entries = list(hd.iterdir()) if hd.is_dir() else []
    layers = [p for p in entries if p.is_dir() and p.name.lower().endswith(".mpq")]
    return layers or ([hd] if entries else [])


def index_pipeline_assets(root, cfg):
    roots, unavailable = hd_asset_roots(root), []
    if not roots:
        unavailable.append("01-HD")
    base = root / cfg["base"]
    if base.is_dir():
        roots.append(base)
    else:
        unavailable.append("02-HD-Clean")
    races = root / cfg["races_dir"]
    if races.is_dir():
        roots.extend(p for p in races.iterdir() if p.is_dir() and re.match(r"^\d+-", p.name))
    else:
        unavailable.append("03-Races")
    idx = set()
    for folder in dict.fromkeys(roots):
        idx.update(index_assets(root, folder, []))
    return idx, unavailable


def prune_inherited_files(base, out, preserve=()):
    """Keep changed files and explicitly installed race appearance textures."""
    base, out = base.resolve(), out.resolve()
    if base.is_relative_to(out) or out.is_relative_to(base):
        raise ValueError("base et output doivent être distincts et non imbriqués")
    preserved = {p.replace("\\", "/").lower() for p in preserve}
    originals = {p.relative_to(base).as_posix().lower(): p
                 for p in base.rglob("*") if p.is_file()}
    removed = size = 0
    for path in out.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(out).as_posix().lower()
        if relative in preserved:
            continue
        original = originals.get(relative)
        if original is not None and filecmp.cmp(original, path, shallow=False):
            size += path.stat().st_size
            path.unlink()
            removed += 1
    directories = [p for p in out.rglob("*") if p.is_dir()]
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    return removed, size


# --------------------------------------------------------------------------- archive MPQ (Windows x64)
class StormLib:
    """Interface de la DLL Unicode Windows fournie avec le dépôt."""
    def __init__(self, path):
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("La création MPQ nécessite Windows et Python 64 bits (StormLib.dll x64).")
        self.dll = ctypes.WinDLL(str(path.resolve()), use_last_error=True)
        handle = ctypes.c_void_p
        dword = ctypes.c_uint32
        signatures = {
            "SFileCreateArchive": [ctypes.c_wchar_p, dword, dword, ctypes.POINTER(handle)],
            "SFileAddFileEx": [handle, ctypes.c_wchar_p, ctypes.c_char_p, dword, dword, dword],
            "SFileCloseArchive": [handle],
        }
        for name, args in signatures.items():
            fn = getattr(self.dll, name)
            fn.argtypes = args
            fn.restype = ctypes.c_bool

    def check(self, success, operation):
        if not success:
            code = ctypes.get_last_error()
            raise OSError(code, f"{operation}: {ctypes.FormatError(code).strip()}")

    def pack(self, source, destination):
        files = sorted(p for p in source.rglob("*") if p.is_file())
        if not files:
            raise ValueError(f"Aucun fichier à archiver dans {source}")
        names = [p.relative_to(source).as_posix().replace("/", "\\") for p in files]
        if len({n.lower() for n in names}) != len(names):
            raise ValueError("Plusieurs fichiers MPQ ont le même chemin (casse ignorée).")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=destination.stem + "-", suffix=".mpq", dir=destination.parent)
        os.close(fd)
        temporary = Path(tmp)
        try:
            # MPQ v2 (WotLK), avec (listfile) et (attributes).
            archive = ctypes.c_void_p()
            self.check(self.dll.SFileCreateArchive(str(temporary), 0x01300000, len(files) + 2,
                                                  ctypes.byref(archive)), "SFileCreateArchive")
            try:
                for path, name in zip(files, names):
                    self.check(self.dll.SFileAddFileEx(archive, str(path.resolve()), name.encode("utf-8"),
                                                      0x00000200, 0x02, 0x02),
                               f"SFileAddFileEx({name})")
            finally:
                self.check(self.dll.SFileCloseArchive(archive), "SFileCloseArchive")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        log("info", f"MPQ créé : {destination} ({len(files)} fichiers, compression zlib)")


def mpq_destination(cfg, root, out):
    value = cfg.get("mpq_output")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("mpq_output doit contenir le chemin absolu du fichier MPQ final.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"mpq_output doit être un chemin absolu : {value}")
    path = path.resolve()
    if path.suffix.lower() != ".mpq" or path.is_dir():
        raise ValueError(f"mpq_output doit désigner un fichier .mpq : {path}")
    for folder in (out, root / cfg["base"], root / cfg["races_dir"]):
        if path.is_relative_to(folder.resolve()):
            raise ValueError(f"mpq_output doit être en dehors du dossier {folder}")
    return path


def available_races_markdown(cfg, dbs, results, include_glue=True):
    races = dbs["ChrRaces"]
    playable = sorted({r[0] for r in dbs["CharBaseInfo"].recs})
    rows = {races.u32(r, 0): r for r in races.recs}
    tokens = {rid: races.s(races.u32(rows[rid], 11)) for rid in playable}
    names = {**tokens, **{r["target"]: r["name"] for r in results}}
    gl = cfg.get("glue", {}) if include_glue else {}
    parents = {}
    for index, group in enumerate(gl.get("race_variants", []), 1):
        ids = race_name_ids(playable, names, group, f"glue.race_variants[{index}]")
        for rid in ids[1:]:
            parents[rid] = ids[0]

    def label(rid):
        row = rows[rid]
        return (races.s(races.u32(row, 16)) or races.s(races.u32(row, 14))
                or next((races.s(races.u32(row, c)) for c in range(14, 30)
                         if races.s(races.u32(row, c))), tokens[rid]))

    def cell(value):
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

    sides = {value: name for name, value in SIDE_VAL.items()}
    md = ["# Races disponibles", "",
          "Récapitulatif des races jouables déclarées dans les DBC client finales, "
          "variantes comprises. Les races réservées aux PNJ sont exclues.",
          "Les noms privilégient la traduction française disponible dans le client.", "",
          "**Les IDs sont des IDs client, pas des emplacements de boutons.** "
          "Le serveur doit prendre en charge ces IDs ; les variantes ne sont pas encore "
          "des apparences persistantes de leur race principale.", "",
          "| ID client | Nom | Faction | Token client | Accès |",
          "|---|---|---|---|---|"]
    for rid in sorted(playable, key=lambda rid: (races.u32(rows[rid], 13), rid)):
        side = races.u32(rows[rid], 13)
        if side not in sides:
            raise ValueError(f"Race {rid} : faction client inconnue {side}")
        access = (f"Variante de {label(parents[rid])} (ID {parents[rid]})"
                  if rid in parents else "Race principale")
        md.append("| " + " | ".join(cell(v) for v in
                                    (rid, label(rid), sides[side], tokens[rid], access)) + " |")
    md += ["", f"Total : {len(playable)} races et variantes jouables côté client."]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent / "merge-config.json"))
    ap.add_argument("--skip-glue", action="store_true")
    a = ap.parse_args()
    cfgp = Path(a.config).resolve()
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    root = cfgp.parent
    base, out = root / cfg["base"], root / cfg["output"]
    if not base.is_dir():
        sys.exit(f"base introuvable : {base}")
    sources = [base, root / cfg["races_dir"]]
    if cfg.get("glue_source"):
        sources.append(root / cfg["glue_source"])
    for pattern in cfg.get("asset_roots", []):
        sources.extend(root.glob(pattern))
    for source in sources:
        if source.resolve().is_relative_to(out.resolve()) or out.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"source {source} et output doivent être distincts et non imbriqués")
    destination = None
    storm = None
    if sys.platform == "win32":
        destination = mpq_destination(cfg, root, out)
        storm = StormLib(root / cfg.get("stormlib_path", "StormLib.dll"))
    else:
        log("info", f"Création MPQ ignorée sur {sys.platform} : StormLib.dll nécessite Windows ; merge conservé.")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(base, out)
    log("info", f"{base.name} copié vers {out} pour préparer le patch différentiel")

    dbc_dir = ci_find(out, "DBFilesClient")
    dbs = load_tables(dbc_dir)
    missing = [t for t in TABLES if t not in dbs]
    if missing:
        log("warn", f"DBC absentes de la base : {missing}")

    results, relocated, needed = merge_dbc_and_files(cfg, root, out, dbs)

    if not a.skip_glue:
        patch_glue(cfg, root, out, results, dbs)

    # Ressources référencées : les trois sources, plus le résultat effectif.
    idx, unavailable = index_pipeline_assets(root, cfg)
    effective_idx = index_assets(root, out, [])
    idx.update(effective_idx)
    if unavailable:
        log("warn", f"Contrôle des ressources incomplet : {', '.join(unavailable)} "
                    "indisponible(s) ou sans extraction")
    unresolved = {}
    for name, lst in needed.items():
        miss = sorted({f for f in lst if f.replace("\\", "/").lower() not in idx})
        if miss:
            unresolved[name] = miss
            status = ("introuvables dans les sources accessibles" if unavailable
                      else "absentes de 01-HD, 02-HD-Clean et 03-Races")
            log("warn", f"{name}: {len(miss)} ressources référencées {status} (liste complète dans le rapport)")
    missing_models = {
        name: sorted({f for f in files if f.lower().endswith((".m2", ".skin"))
                      and f.replace("\\", "/").lower() not in effective_idx})
        for name, files in needed.items()
    }
    for name, files in missing_models.items():
        if files:
            log("warn", f"{name}: modèles/skins absents de la base HD et du patch : {', '.join(files)} ; "
                        "récupérer les fichiers compatibles avec le M2, ne pas mélanger les versions")

    inherited, inherited_bytes = prune_inherited_files(
        base, out, [p for race in results for p in race["appearance_textures"]])
    remaining = sum(1 for p in out.rglob("*") if p.is_file())
    log("info", f"patch différentiel : {remaining} fichiers nouveaux/modifiés conservés ; "
                f"{inherited} fichiers hérités de la base HD exclus ({inherited_bytes / 1048576:.1f} Mo)")

    dst = out.parent
    (dst / "race-mapping.json").write_text(json.dumps(
        {"races": results, "relocated": relocated}, indent=2, ensure_ascii=False), encoding="utf-8")
    if storm is not None:
        storm.pack(out, destination)
    md = ["# Rapport de merge", "", "## Races", "",
          "| Race | Source Esteria | ID final | Faction | Token glue | Classes |", "|---|---|---|---|---|---|"]
    for x in results:
        md.append(f"| {x['name']} | {x['source']} | {x['target']} | {x['faction']} | {x['token']} | {x['classes']} |")
    md += ["", "## Races de base déplacées", ""] + [f"- {r['name']} : {r['from']} -> {r['to']}" for r in relocated]
    replaced = [r for r in results if "replaced_race" in r]
    if replaced:
        md += ["", "## Races PNJ remplacées", "",
               "Les modèles et displays sont conservés, mais l'apparence des PNJ utilisant "
               "ces anciennes définitions de race peut changer."]
        md += [f"- ID {r['target']} : {r['replaced_race']} -> {r['name']}" for r in replaced]
    md += ["", "## Patch différentiel", "",
           f"- {remaining} fichiers nouveaux ou modifiés conservés.",
           f"- {inherited} fichiers identiques à la base HD exclus ({inherited_bytes / 1048576:.1f} Mo).",
           "- La base HD doit être installée et chargée avant ce patch.",
           "", "## Modèles et skins absents de la base HD et du patch", "",
           "Vérifiés avant exclusion des fichiers hérités. Un fichier présent uniquement dans asset_roots "
           "ne prouve pas sa disponibilité dans le client cible."]
    for name, files in missing_models.items():
        md += [f"- {name} : {f}" for f in files]
    md += ["", "## Vérification des ressources", "",
           "- 01-HD : sortie fusionnée de l'extraction, ou dossiers *.mpq extraits.",
           f"- 02-HD-Clean : base configurée `{cfg['base']}`.",
           f"- 03-Races : tous les dossiers de races dans `{cfg['races_dir']}`, sélectionnés ou non.",
           "- Chemins comparés sans tenir compte de la casse ; ressources du résultat effectif également disponibles."]
    if unavailable:
        md += ["", f"**Contrôle incomplet : {', '.join(unavailable)} indisponible(s) ou non extrait(s).**",
               "Les ressources listées sont introuvables dans les sources accessibles ; leur absence "
               "dans les sources indisponibles n'est pas établie."]
    else:
        md += ["", "Les ressources listées ci-dessous sont absentes des trois sources et du résultat effectif."]
    md += ["", "## Journal", ""] + [f"- **{lv}** {m}" for lv, m in LOG]
    for name, lst in unresolved.items():
        md += ["", f"## Fichiers introuvables : {name}", "",
               f"{len(lst)} ressources référencées introuvables.", ""] + [f"- {f}" for f in lst]
    (dst / "merge-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    recap = dst / "available-races.md"
    recap.write_text(available_races_markdown(cfg, dbs, results, include_glue=not a.skip_glue),
                     encoding="utf-8")
    mpq_status = f"MPQ : {destination}" if storm is not None else "MPQ : création ignorée (hors Windows)"
    print(f"\nOK -> {out}\n{mpq_status}\nRapport : {dst / 'merge-report.md'}"
          f"\nMapping : {dst / 'race-mapping.json'}\nRaces disponibles : {recap}")


if __name__ == "__main__":
    run_logged(main, __file__)
