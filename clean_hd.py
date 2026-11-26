#!/usr/bin/env python3
"""
clean_hd.py - Construit 02-HD-Clean à partir de 01-HD (dossiers *.mpq extraits).

Pour chaque fichier utile au tuto "Adding a New Race" (DBC, GlueXML, icônes, modèles),
on résout l'héritage MPQ (le patch de priorité la plus haute gagne) et on copie
UNIQUEMENT la version gagnante dans 02-HD-Clean/patch-X.mpq/.

Usage (depuis D:\\repo\\reforge-allies) :
    python clean_hd.py                      # génère 02-HD-Clean
    python clean_hd.py --dry-run            # n'écrit rien, affiche le rapport
    python clean_hd.py --keywords worgen,goblin,nightborne
    python clean_hd.py --extra-dbc ChrClasses,Spell
    python clean_hd.py --order base,A,B,C,...   # force l'ordre de priorité
"""
import argparse
import json
import re
import shutil
import struct
import sys
from pathlib import Path

from execution_log import run_logged
from race_assets import UnsupportedModelVersionError, model_dependencies, model_path

# --- Fichiers cités dans le README -----------------------------------------
DBC_LIST = [
    "ChrRaces", "CharBaseInfo", "CharStartOutfit", "SkillLineAbility",
    "SkillRaceClassInfo", "CreatureModelData", "CreatureDisplayInfo",
    "CreatureDisplayInfoExtra", "CharSections", "CharacterFacialHairStyles",
    "CharHairGeosets",
]
GLUE_FILES = [
    "Interface/GlueXML/CharacterCreate.lua",
    "Interface/GlueXML/CharacterCreate.xml",
    "Interface/GlueXML/GlueParent.lua",
    "Interface/GlueXML/GlueStrings.lua",
]
# Dossiers copiés en entier (icônes de création de perso, etc.), non récursif
GLUE_DIRS = ["Interface/Glues/CharacterCreate"]


def norm(p):
    return str(p).replace("\\", "/").strip("/").lower()


# --- Ordre de priorité des MPQ ---------------------------------------------
def mpq_sort_key(name):
    """base < patch < patch-2 < patch-3 < patch-A < patch-B."""
    n = name.lower()
    numbered = re.match(r"^(\d{2,})_(.+)$", n)
    if numbered:
        return (-1, int(numbered.group(1)))
    n = n.removesuffix(".mpq")
    if n == "base":
        return (0, n)
    if n == "patch":
        return (1, "")
    m = re.match(r"patch-(.+)$", n)
    tag = m.group(1) if m else n
    # chiffres avant lettres, puis ordre alphabétique
    return (2 if tag.isdigit() else 3, tag.rjust(8, "0") if tag.isdigit() else tag)


def find_mpq_dirs(src, order):
    dirs = [d for d in src.iterdir() if d.is_dir()]
    if order:
        rank = {}
        for i, tag in enumerate(order):
            t = tag.strip().lower()
            rank[t] = i
            rank["patch-" + t] = i
        def key(d):
            n = re.sub(r"^\d{2,}_", "", d.name.lower()).removesuffix(".mpq")
            if n not in rank:
                raise ValueError(f"--order incomplet : {d.name} absent de la liste de priorité")
            return rank[n]
        return sorted(dirs, key=key)
    return sorted(dirs, key=lambda d: mpq_sort_key(d.name))


class Layer:
    def __init__(self, path):
        self.path = path
        self.name = path.name
        self.files = {}  # chemin normalisé -> Path réel
        for f in path.rglob("*"):
            if f.is_file():
                self.files[norm(f.relative_to(path))] = f


class Stack:
    """Pile de MPQ : index 0 = priorité la plus basse."""
    def __init__(self, layers):
        self.layers = layers

    def providers(self, rel):
        rel = norm(rel)
        return [l for l in self.layers if rel in l.files]

    def resolve(self, rel):
        p = self.providers(rel)
        return (p[-1], p[:-1]) if p else (None, [])

    def listdir(self, reldir, recursive=False):
        """Tous les chemins (normalisés) sous reldir, toutes couches confondues."""
        base = norm(reldir) + "/"
        out = set()
        for l in self.layers:
            for k in l.files:
                if k.startswith(base):
                    if recursive or "/" not in k[len(base):]:
                        out.add(k)
        return sorted(out)


# --- Lecture minimale des DBC ----------------------------------------------
def read_dbc_strings(path, col):
    """Retourne la liste des chaînes de la colonne `col` (champs de 4 octets)."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"WDBC":
        raise ValueError(f"{path}: pas un WDBC")
    rc, fc, rs, ss = struct.unpack_from("<4I", data, 4)
    if rs == 0:
        raise ValueError(f"{path}: taille de ligne DBC nulle")
    sb = 20 + rc * rs
    if sb + ss > len(data):
        raise ValueError(f"{path}: fichier DBC tronqué")
    out = []
    for i in range(rc):
        if col * 4 + 4 > rs:
            raise ValueError(f"{path}: colonne {col} absente (record_size={rs})")
        off = struct.unpack_from("<I", data, 20 + i * rs + col * 4)[0]
        if off == 0:
            continue
        if off >= ss:
            raise ValueError(f"{path}: offset de chaîne hors limites: {off}")
        end = data.find(b"\0", sb + off, sb + ss)
        if end < 0:
            raise ValueError(f"{path}: chaîne non terminée à l'offset {off}")
        out.append(data[sb + off:end].decode("utf-8", "replace"))
    return out


def dbc_info(path):
    with path.open("rb") as stream:
        d = stream.read(20)
    if len(d) < 20 or d[:4] != b"WDBC":
        raise ValueError(f"{path}: pas un WDBC")
    _, rc, fc, rs, ss = struct.unpack("<4s4I", d)
    if rs == 0 or 20 + rc * rs + ss > path.stat().st_size:
        raise ValueError(f"{path}: fichier DBC invalide ou tronqué")
    return rc, fc


def model_files(stack, cmd_layer_path, keywords):
    """
    Conserve Character entier et les autres modèles correspondant aux mots-clés,
    même s'ils ne sont pas référencés par CreatureModelData.
    """
    models = {norm(model_path(m)) for m in read_dbc_strings(cmd_layer_path, 2)} if cmd_layer_path else set()
    for layer in stack.layers:
        models.update(k for k in layer.files if k.endswith(".m2"))
    wanted = set(stack.listdir("Character", recursive=True))
    matched, unverified = [], []
    for mn in sorted(models):
        if not mn.startswith("character/") and not any(k in mn for k in keywords):
            continue
        matched.append(mn)
        wanted.add(mn)
        win, _ = stack.resolve(mn)
        if win:
            try:
                dependencies = model_dependencies(win.files[mn], mn)
            except UnsupportedModelVersionError as exc:
                unverified.append({"file": mn, "reason": str(exc)})
            else:
                wanted.update(norm(p) for p in dependencies)
        parts = mn.split("/")
        if parts[0] != "character":
            d = "/".join(parts[:-1])
            stem = parts[-1].rsplit(".", 1)[0]
            for k in stack.listdir(d):
                if k.rsplit("/", 1)[-1].startswith(stem[:len(stem)]) or k.endswith(".blp"):
                    wanted.add(k)
    return wanted, matched, unverified


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    ap.add_argument("--src", default=str(root / "01-HD-patchs"))
    ap.add_argument("--dst", default=str(root / "02-HD-Clean"))
    ap.add_argument("--patch-name", default="patch-X.mpq")
    ap.add_argument("--keywords", default="worgen,goblin",
                    help="modèles supplémentaires hors Character, recherchés dans les fichiers et CreatureModelData")
    ap.add_argument("--extra-dbc", default="", help="DBC supplémentaires, séparées par des virgules")
    ap.add_argument("--extra-files", default="", help="chemins supplémentaires (relatifs au MPQ), séparés par des virgules")
    ap.add_argument("--order", default="",
                    help="ordre complet de priorité, ex: base,patch,2,3,A,B,C")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="store_true", help="ne pas vider le dossier de sortie")
    a = ap.parse_args()

    src, dst = Path(a.src), Path(a.dst)
    if not src.is_dir():
        sys.exit(f"Source introuvable : {src}")
    if src.resolve().is_relative_to(dst.resolve()) or dst.resolve().is_relative_to(src.resolve()):
        raise ValueError("Source et destination doivent être distinctes et non imbriquées")
    if a.patch_name in ("", ".", "..") or any(c in a.patch_name for c in "/\\:"):
        raise ValueError("--patch-name doit être un simple nom de dossier")

    dirs = find_mpq_dirs(src, [t for t in a.order.split(",") if t])
    if not dirs:
        sys.exit(f"Aucun dossier *.mpq dans {src}")
    if any(d.name.lower() == a.patch_name.lower() for d in dirs):
        sys.exit(f"{a.patch_name} existe déjà dans la source, choisis un autre --patch-name")

    print("Ordre de priorité (bas -> haut) :")
    layers = []
    for d in dirs:
        l = Layer(d)
        layers.append(l)
        print(f"  {d.name:20s} {len(l.files):7d} fichiers")
    stack = Stack(layers)

    # --- 1. liste des fichiers voulus ---
    dbcs = DBC_LIST + [x for x in a.extra_dbc.split(",") if x]
    wanted = [f"DBFilesClient/{n}.dbc" for n in dbcs]
    wanted += GLUE_FILES
    for g in GLUE_DIRS:
        wanted += stack.listdir(g)
    wanted += [x for x in a.extra_files.split(",") if x]

    report = {"resolved": [], "missing": [], "models": []}
    chosen = {}  # chemin normalisé -> (Path source, couche, couches masquées)

    for rel in wanted:
        win, hidden = stack.resolve(rel)
        k = norm(rel)
        if win is None:
            report["missing"].append(rel)
            continue
        chosen[k] = (win.files[k], win, hidden)

    # --- 2. modèles présents dans la pile + références CreatureModelData ---
    cmd_key = norm("DBFilesClient/CreatureModelData.dbc")
    kws = [k.strip().lower() for k in a.keywords.split(",") if k.strip()]
    cmd_path = chosen[cmd_key][0] if cmd_key in chosen else None
    if cmd_path is None:
        print("! CreatureModelData introuvable : découverte des modèles directement dans la pile")
    mfiles, matched, unverified = model_files(stack, cmd_path, kws)
    report["models"] = matched
    report["unverified_models"] = unverified
    for entry in unverified:
        print(f"! {entry['reason']} ; conservé sans analyse des dépendances, "
              "à ne pas utiliser comme modèle joueur 3.3.5 sans conversion")
    for k in mfiles:
        win, hidden = stack.resolve(k)
        if win is None:
            report["missing"].append(k)
            continue
        chosen[k] = (win.files[k], win, hidden)

    # --- 3. rapport + copie ---
    out_root = dst / a.patch_name
    total = 0
    print(f"\n{len(chosen)} fichiers retenus -> {out_root}")
    for k, (p, win, hidden) in sorted(chosen.items()):
        rel = p.relative_to(win.path)  # casse d'origine
        total += p.stat().st_size
        report["resolved"].append({
            "file": str(rel).replace("\\", "/"),
            "from": win.name,
            "shadows": [h.name for h in hidden],
        })
        if k.startswith("dbfilesclient/") and k.endswith(".dbc"):
            rc, fc = dbc_info(p)
            print(f"  {rel.name:34s} <- {win.name:14s} ({rc} lignes, {fc} champs)"
                  + (f"  masque: {', '.join(h.name for h in hidden)}" if hidden else ""))
    if report["missing"]:
        print("\nIntrouvables dans la pile :")
        for m in report["missing"]:
            print("  -", m)
    if report["models"]:
        print(f"\nModèles repérés ({len(report['models'])}) :")
        for m in report["models"][:30]:
            print("  ", m)
        if len(report["models"]) > 30:
            print(f"   ... +{len(report['models']) - 30}")
    print(f"\nTaille totale : {total / 1048576:.1f} Mo")

    if a.dry_run:
        print("\n(dry-run : rien n'a été écrit)")
        return

    if dst.exists() and not a.keep:
        shutil.rmtree(dst)
    out_root.mkdir(parents=True, exist_ok=True)
    for k, (p, win, _) in chosen.items():
        target = out_root / p.relative_to(win.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    (dst / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nOK -> {dst}  (détails dans report.json)")


if __name__ == "__main__":
    run_logged(main, __file__)
