#!/usr/bin/env python3
r"""Extrait les .mpq d'un dossier Data WoW dans un sous-dossier par archive
(<patchs>/NN_nom), puis construit la fusion <out> en respectant l'ordre de
chargement (la dernière archive gagne).

Deux profils prédéfinis (modifiables dans PROFILES) :
  coa : C:\\Jeux\\Conquest of Azeroth\\Data      -> Esteria-patchs / Esteria
  hd  : C:\\Jeux\\World of Warcraft 3.3.5\\Data  -> 01-HD-patchs / 01-HD

Optimisations IO :
  - chaque fichier n'est décompressé / écrit qu'UNE fois (dans <patchs>) ;
  - la fusion se fait par liens physiques (zéro octet copié) ; --copy pour dupliquer ;
  - seul le gagnant de chaque fichier est exposé dans <out> ;
  - archives déjà extraites (taille + date identiques) ignorées, sauf --force ;
  - extraction des archives en parallèle (--workers), tampon 4 Mo par thread.

Ignorer des MPQ sources (ni extraits, ni fusionnés) :
  --ignore motif [motif ...]   nom, chemin relatif ou motif (* ?), avec ou sans .mpq,
                               ex : patch-Z  "patch-*"  enUS\\patch-enUS-3  03_patch
  --ignore-file fichier.txt    un motif par ligne, # = commentaire
  Fichiers chargés automatiquement s'ils existent (dans le répertoire courant) :
  ignore-<profil>.txt  (ex : ignore-coa.txt, ignore-hd.txt)
  La numérotation (NN_) est calculée AVANT le filtre : les dossiers existants
  gardent leur nom quand on ajoute / retire une exclusion.

Écrit overrides-<profil>.txt : fichiers présents dans plusieurs archives
(l'ordre listé = ordre de chargement, le dernier gagne).
Utilise StormLib.dll placée dans le répertoire courant (même bitness que Python).

Usage :
  python extract_mpq.py [coa|hd ...] [--workers 4] [--copy] [--force]
                        [--ignore motif ...] [--ignore-file f.txt]
                        [--list] [--find sous-chaine]
                        [--data-dir src] [--patchs-dir dst] [--out-dir dst]   (un seul profil)
                        [--dest-root dossier]            (tous profils : <root>/<patchs> et <root>/<out>)
Sans profil : coa puis hd.
Exemple : python extract_mpq.py hd --data-dir "D:\WoW\Data" --patchs-dir E:\tmp\hd-p --out-dir E:\tmp\hd
Les dossiers de destination doivent être sur le même volume pour les liens physiques
(sinon repli automatique sur la copie). ignore-<profil>.txt est lu dans le répertoire courant.
"""
import argparse
import ctypes
import errno
import fnmatch
import os
import re
import shutil
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

from execution_log import run_logged

CWD = os.getcwd()

PROFILES = {
    "coa": {
        "data_dir": r"C:\Jeux\Conquest of Azeroth\Data",
        "patchs": "Esteria-patchs",
        "out": "Esteria",
        "ignore": [],          # motifs ignorés par défaut pour ce profil
    },
    "hd": {
        "data_dir": r"C:\Jeux\World of Warcraft 3.3.5\Data",
        "patchs": "01-HD-patchs",
        "out": "01-HD",
        "ignore": [],
    },
}

DLL_PATH = os.path.join(CWD, "StormLib.dll")
MAX_PATH = 260
SKIP = {"(listfile)", "(attributes)", "(signature)", "(patch_metadata)"}
CHUNK = 4 * 1024 * 1024
MARKER = ".extracted"

_tls = threading.local()
_print_lock = threading.Lock()


def buf():
    if not hasattr(_tls, "b"):
        _tls.b = ctypes.create_string_buffer(CHUNK)
    return _tls.b


class SFILE_FIND_DATA(ctypes.Structure):
    _fields_ = [
        ("cFileName", ctypes.c_char * MAX_PATH),
        ("szPlainName", ctypes.c_char_p),
        ("dwHashIndex", wintypes.DWORD),
        ("dwBlockIndex", wintypes.DWORD),
        ("dwFileSize", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwCompSize", wintypes.DWORD),
        ("dwFileTimeLo", wintypes.DWORD),
        ("dwFileTimeHi", wintypes.DWORD),
        ("lcLocale", wintypes.DWORD),
    ]


def load_storm():
    if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("L'extraction MPQ nécessite Windows et Python 64 bits ; "
                           "--list reste disponible sans StormLib.")
    if not os.path.isfile(DLL_PATH):
        sys.exit(f"StormLib.dll introuvable : {DLL_PATH}")
    dll = ctypes.WinDLL(DLL_PATH, use_last_error=True)
    H = ctypes.c_void_p
    dll.SFileOpenArchive.argtypes = [ctypes.c_wchar_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(H)]
    dll.SFileOpenArchive.restype = ctypes.c_bool
    dll.SFileCloseArchive.argtypes = [H]
    dll.SFileCloseArchive.restype = ctypes.c_bool
    dll.SFileFindFirstFile.argtypes = [H, ctypes.c_char_p, ctypes.POINTER(SFILE_FIND_DATA), ctypes.c_char_p]
    dll.SFileFindFirstFile.restype = H
    dll.SFileFindNextFile.argtypes = [H, ctypes.POINTER(SFILE_FIND_DATA)]
    dll.SFileFindNextFile.restype = ctypes.c_bool
    dll.SFileFindClose.argtypes = [H]
    dll.SFileFindClose.restype = ctypes.c_bool
    dll.SFileOpenFileEx.argtypes = [H, ctypes.c_char_p, wintypes.DWORD, ctypes.POINTER(H)]
    dll.SFileOpenFileEx.restype = ctypes.c_bool
    dll.SFileReadFile.argtypes = [H, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    dll.SFileReadFile.restype = ctypes.c_bool
    dll.SFileCloseFile.argtypes = [H]
    dll.SFileCloseFile.restype = ctypes.c_bool
    return dll


def load_order(data_dir):
    """Retourne la liste des .mpq dans l'ordre de chargement WoW 3.3.5."""
    found = {}
    for root, _dirs, files in os.walk(data_dir):
        for f in files:
            if f.lower().endswith(".mpq"):
                full = os.path.join(root, f)
                found[os.path.relpath(full, data_dir).lower()] = full

    locales = sorted({os.path.dirname(r) for r in found if os.path.dirname(r)})
    ordered = []

    def add(rel):
        rel = rel.lower()
        if rel in found and found[rel] not in ordered:
            ordered.append(found[rel])

    for n in ("common", "common-2", "expansion", "lichking", "patch", "patch-2", "patch-3"):
        add(f"{n}.mpq")

    for loc in locales:
        for n in (f"locale-{loc}", f"speech-{loc}", f"expansion-locale-{loc}",
                  f"lichking-locale-{loc}", f"expansion-speech-{loc}",
                  f"lichking-speech-{loc}", f"patch-{loc}", f"patch-{loc}-2",
                  f"patch-{loc}-3"):
            add(os.path.join(loc, f"{n}.mpq"))

    root_rest = sorted((r for r in found if os.sep not in r and found[r] not in ordered))
    pat = re.compile(r"^patch-[^.]+\.mpq$")
    for r in root_rest:
        if pat.match(r):
            add(r)

    for loc in locales:
        extra = sorted(r for r in found if os.path.dirname(r) == loc and found[r] not in ordered)
        for r in extra:
            add(r)

    for r in sorted(found):
        add(r)
    return ordered


# ---------------------------------------------------------------- ignore ---

def _norm(s):
    return s.strip().lower().replace("/", os.sep).replace("\\", os.sep)


def read_ignore_file(path):
    pats = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.split("#", 1)[0].strip().strip('"')
            if line:
                pats.append(line)
    return pats


def build_ignore(profile, cli_patterns, cli_files):
    pats = list(PROFILES[profile]["ignore"])
    auto = os.path.join(CWD, f"ignore-{profile}.txt")
    if os.path.isfile(auto):
        pats += read_ignore_file(auto)
    for fpath in cli_files:
        if not os.path.isfile(fpath):
            sys.exit(f"Fichier d'exclusion introuvable : {fpath}")
        pats += read_ignore_file(fpath)
    pats += cli_patterns
    return [_norm(p) for p in pats]


def is_ignored(path, folder, data_dir, patterns):
    """Vrai si l'archive correspond à un motif (chemin relatif, nom, avec/sans .mpq, dossier NN_)."""
    rel = _norm(os.path.relpath(path, data_dir))
    base = os.path.basename(rel)
    cands = {rel, os.path.splitext(rel)[0], base, os.path.splitext(base)[0],
             _norm(folder), _norm(folder)[3:]}  # [3:] = sans le préfixe "NN_"
    return any(fnmatch.fnmatchcase(c, p) for p in patterns for c in cands)


# ------------------------------------------------------------ extraction ---

class MPQFileError(OSError):
    """Source-file failure that can be retried without hiding local IO errors."""


def extract_file(dll, h_mpq, name, dest, made, expected_size):
    h_file = ctypes.c_void_p()
    if not dll.SFileOpenFileEx(h_mpq, name, 0, ctypes.byref(h_file)):
        raise MPQFileError(ctypes.get_last_error(), f"SFileOpenFileEx : {name!r}")
    try:
        d = os.path.dirname(dest)
        if d not in made:
            os.makedirs(d, exist_ok=True)
            made.add(d)
        b = buf()
        view = memoryview(b).cast("B")
        read = wintypes.DWORD(0)
        total = 0
        with open(dest, "wb") as out:
            while True:
                read.value = 0
                ok = dll.SFileReadFile(h_file, b, CHUNK, ctypes.byref(read), None)
                if not ok:
                    error = ctypes.get_last_error()
                    if error != 38:  # ERROR_HANDLE_EOF can accompany a final partial read.
                        raise MPQFileError(error, f"SFileReadFile : {name!r}")
                if read.value:
                    out.write(view[:read.value])
                    total += read.value
                if not ok or read.value < CHUNK:
                    break
        if total != expected_size:
            raise MPQFileError(f"{name!r} : extraction tronquée ({total} octets, {expected_size} attendus)")
    finally:
        dll.SFileCloseFile(h_file)
    return True


def signature(path):
    st = os.stat(path)
    return f"v3:{st.st_size}:{st.st_mtime_ns}"


def extract_archive(dll, path, outdir, force):
    """Extrait une archive dans outdir. Retourne (chemins relatifs, extraits, fichiers ignorés, en cache)."""
    sig = signature(path)
    marker = os.path.join(outdir, MARKER)
    if not force and os.path.isfile(marker):
        with open(marker, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
        if lines and lines[0] == sig:
            return [l for l in lines[1:] if l], 0, 0, True

    h_mpq = ctypes.c_void_p()
    if not dll.SFileOpenArchive(path, 0, 0x100, ctypes.byref(h_mpq)):  # 0x100 = READ_ONLY
        raise OSError(ctypes.get_last_error(), f"SFileOpenArchive : {path}")
    files, ignored = [], 0
    try:
        if os.path.isdir(outdir):
            shutil.rmtree(outdir)
        os.makedirs(outdir, exist_ok=True)
        fd = SFILE_FIND_DATA()
        h_find = dll.SFileFindFirstFile(h_mpq, b"*", ctypes.byref(fd), None)
        if not h_find:
            error = ctypes.get_last_error()
            if error != 18:  # ERROR_NO_MORE_FILES
                raise OSError(error, f"SFileFindFirstFile : {path}")
        else:
            try:
                seen, made, extracted, dup_streak = set(), set(), set(), 0
                while True:
                    name = fd.cFileName
                    key = name.lower()
                    if key in seen:
                        dup_streak += 1
                        if dup_streak >= 2000:
                            raise RuntimeError(f"SFileFindNextFile boucle sur {name!r} dans {path}")
                    else:
                        dup_streak = 0
                        seen.add(key)
                        if name and key.decode("latin-1") not in SKIP:
                            parts = name.decode("utf-8", "replace").replace("\\", "/").split("/")
                            if (not parts[0] or not parts[-1]
                                    or any(p in (".", "..") or ":" in p for p in parts)):
                                raise ValueError(f"Chemin de fichier MPQ invalide : {name!r}")
                            rel = os.path.join(*(p for p in parts if p))
                            if rel.lower() not in extracted:
                                dest = os.path.join(outdir, rel)
                                for attempt in range(1, 4):
                                    try:
                                        extract_file(dll, h_mpq, name, dest, made, fd.dwFileSize)
                                    except MPQFileError as exc:
                                        Path(dest).unlink(missing_ok=True)
                                        status = "anomalie" if attempt == 3 else "retry"
                                        with _print_lock:
                                            print(f"[{status}] {name!r} dans {path} : "
                                                  f"tentative {attempt}/3 : {exc}")
                                    else:
                                        files.append(rel)
                                        extracted.add(rel.lower())
                                        break
                                else:
                                    ignored += 1
                    if not dll.SFileFindNextFile(h_find, ctypes.byref(fd)):
                        error = ctypes.get_last_error()
                        if error != 18:
                            raise OSError(error, f"SFileFindNextFile : {path}")
                        break
            finally:
                dll.SFileFindClose(h_find)
    finally:
        dll.SFileCloseArchive(h_mpq)

    if not ignored:
        with open(marker, "w", encoding="utf-8") as f:
            f.write(sig + "\n" + "\n".join(files))
    return files, len(files), ignored, False


def prune_patchs(patchs_dir, keep):
    """Supprime de <patchs> les dossiers NN_nom qui ne correspondent plus à une archive
    traitée (MPQ supprimé, renommé, renuméroté ou désormais ignoré)."""
    pat = re.compile(r"^\d{2,}_")
    stale = [e for e in sorted(os.listdir(patchs_dir))
             if e not in keep and pat.match(e) and os.path.isdir(os.path.join(patchs_dir, e))]

    # archives conservées dont le dossier n'existe pas encore sous ce numéro : renumérotation
    missing = {f.split("_", 1)[1]: f for f in keep
               if not os.path.exists(os.path.join(patchs_dir, f))}
    remaining = []
    for entry in stale:
        target = missing.get(entry.split("_", 1)[1])
        if target:
            os.rename(os.path.join(patchs_dir, entry), os.path.join(patchs_dir, target))
            print(f"  renuméroté : {entry} -> {target}")
        else:
            remaining.append(entry)

    for entry in remaining:
        print(f"  nettoyage : {entry} (archive source absente ou ignorée)")
        shutil.rmtree(os.path.join(patchs_dir, entry), ignore_errors=True)


def merge(archives, results, patchs_dir, out_dir, overrides_path, use_copy):
    """Construit la fusion : la dernière archive de l'ordre de chargement gagne."""
    winners = {}                      # clé minuscule -> (rel, chemin source)
    providers = defaultdict(list)     # clé minuscule -> [noms de dossiers dans l'ordre]
    for (path, folder), files in zip(archives, results):
        src_root = os.path.join(patchs_dir, folder)
        for rel in files:
            k = rel.lower()
            winners[k] = (rel, os.path.join(src_root, rel))
            providers[k].append(folder)

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    made = set()
    linked = copied = link_errors = 0
    can_link = not use_copy
    for rel, src in winners.values():
        dest = os.path.join(out_dir, rel)
        d = os.path.dirname(dest)
        if d not in made:
            os.makedirs(d, exist_ok=True)
            made.add(d)
        if can_link:
            try:
                os.link(src, dest)
                linked += 1
                continue
            except OSError as e:
                # 1 = fonction non supportée, 17 = autre volume (Windows) ; EXDEV/EPERM ailleurs
                if getattr(e, "winerror", None) in (1, 17) or e.errno in (errno.EXDEV, errno.EPERM):
                    can_link = False  # volume sans liens physiques : on copie tout le reste
                    print(f"  liens impossibles ({e}) : copie pour le reste")
                else:                 # échec ponctuel : on copie ce fichier seulement
                    link_errors += 1
                    if link_errors <= 10:
                        print(f"  lien impossible, copie : {rel} ({e})")
        shutil.copyfile(src, dest)
        copied += 1
    if link_errors > 10:
        print(f"  ... {link_errors} échecs de lien au total")

    with open(overrides_path, "w", encoding="utf-8") as f:
        for k in sorted(providers):
            if len(providers[k]) > 1:
                f.write(f"{winners[k][0]}\t" + " -> ".join(providers[k]) + "\n")
    return winners, providers, linked, copied


# ------------------------------------------------------------------ main ---

def run_profile(dll, name, args):
    prof = PROFILES[name]
    data_dir = args.data_dir or prof["data_dir"]
    root = os.path.abspath(args.dest_root) if args.dest_root else CWD
    patchs_dir = os.path.abspath(args.patchs_dir or os.path.join(root, prof["patchs"]))
    out_dir = os.path.abspath(args.out_dir or os.path.join(root, prof["out"]))
    overrides = os.path.join(CWD, f"overrides-{name}.txt")

    print(f"\n===== profil {name} : {data_dir} =====")
    if not os.path.isdir(data_dir):
        print(f"Dossier introuvable : {data_dir}")
        return False
    if not args.list:
        paths = [Path(p).resolve() for p in (data_dir, patchs_dir, out_dir)]
        if any(a.is_relative_to(b) or b.is_relative_to(a)
               for i, a in enumerate(paths) for b in paths[i + 1:]):
            raise ValueError("Data, archives extraites et fusion doivent être distincts et non imbriqués")

    # numérotation sur la liste complète, puis filtre
    all_paths = load_order(data_dir)
    numbered = []
    for i, p in enumerate(all_paths, 1):
        rel = os.path.splitext(os.path.relpath(p, data_dir))[0].replace(os.sep, "_")
        numbered.append((p, f"{i:02d}_{rel}"))

    patterns = build_ignore(name, args.ignore, args.ignore_file)
    archives, skipped = [], []
    for p, folder in numbered:
        (skipped if is_ignored(p, folder, data_dir, patterns) else archives).append((p, folder))

    if args.list:
        ign = {f for _, f in skipped}
        for p, folder in numbered:
            print(f"  {'[IGNORÉ] ' if folder in ign else '         '}{folder}")
        return True

    print(f"{len(archives)} archives ({len(skipped)} ignorées), "
          f"patchs : {patchs_dir}, fusion : {out_dir}")
    for _, folder in skipped:
        print(f"  ignorée : {folder}")
    os.makedirs(patchs_dir, exist_ok=True)
    prune_patchs(patchs_dir, {folder for _, folder in archives})

    def job(i):
        path, folder = archives[i]
        res = extract_archive(dll, path, os.path.join(patchs_dir, folder), args.force)
        with _print_lock:
            files, ok, ignored, was_skipped = res
            if was_skipped:
                print(f"[{i + 1}/{len(archives)}] {folder} : déjà extrait ({len(files)} fichiers)")
            else:
                print(f"[{i + 1}/{len(archives)}] {folder} : {ok} extraits"
                      + (f", {ignored} anomalies (fichiers ignorés, archive non mise en cache)"
                         if ignored else ""))
        return res

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        extractions = list(ex.map(job, range(len(archives))))  # conserve l'ordre de chargement
    results = [result[0] for result in extractions]
    anomalies = sum(result[2] for result in extractions)

    winners, providers, linked, copied = merge(archives, results, patchs_dir, out_dir,
                                               overrides, args.copy)
    print(f"Fusion : {len(winners)} fichiers ({linked} liés, {copied} copiés). "
          f"Surcharges listées dans {os.path.basename(overrides)}")
    if anomalies:
        print(f"[anomalie] Profil {name} : {anomalies} fichiers ignorés après 3 tentatives ; "
              "fusion potentiellement incomplète. Les archives concernées seront retentées au prochain lancement.")

    if args.find:
        needle = args.find.lower().replace("/", os.sep)
        for k in sorted(providers):
            if needle in k:
                print(f"{winners[k][0]}\n    " + " -> ".join(providers[k])
                      + "  (gagnant : " + providers[k][-1] + ")")
    return True


def main():
    ap = argparse.ArgumentParser(description="Extraction + fusion de MPQ (profils coa / hd)")
    ap.add_argument("profiles", nargs="*", metavar="{" + ",".join(sorted(PROFILES)) + "}",
                    help="profils à traiter (défaut : tous, dans l'ordre coa puis hd)")
    ap.add_argument("--workers", type=int, default=1, help="archives extraites en parallèle")
    ap.add_argument("--copy", action="store_true", help="copier au lieu de lier (sortie indépendante)")
    ap.add_argument("--force", action="store_true", help="ré-extraire même si déjà fait")
    ap.add_argument("--find", help="affiche les archives contenant un chemin (sous-chaîne)")
    ap.add_argument("--ignore", nargs="+", action="extend", default=[], metavar="MOTIF",
                    help="MPQ sources à ignorer (nom, chemin relatif ou motif * ?)")
    ap.add_argument("--ignore-file", nargs="+", action="extend", default=[], metavar="FICHIER",
                    help="fichier(s) texte : un motif d'exclusion par ligne")
    ap.add_argument("--list", action="store_true",
                    help="liste les archives dans l'ordre de chargement (avec les ignorées) sans rien extraire")
    ap.add_argument("--data-dir", help="dossier source (Data) : remplace celui du profil (un seul profil)")
    ap.add_argument("--patchs-dir", help="dossier de destination des archives extraites (un seul profil)")
    ap.add_argument("--out-dir", help="dossier de destination de la fusion (un seul profil)")
    ap.add_argument("--dest-root", help="dossier parent des destinations : y crée <patchs> et <out> "
                                        "de chaque profil (utilisable avec plusieurs profils)")
    args = ap.parse_args()

    profiles = args.profiles or list(PROFILES)
    if any(name not in PROFILES for name in profiles):
        ap.error("profils inconnus ; choisir parmi " + ", ".join(sorted(PROFILES)))
    if (args.data_dir or args.patchs_dir or args.out_dir) and len(profiles) != 1:
        ap.error("--data-dir / --patchs-dir / --out-dir exigent exactement un profil")

    dll = None if args.list else load_storm()
    for name in profiles:
        if not run_profile(dll, name, args):
            sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    run_logged(main, __file__)
