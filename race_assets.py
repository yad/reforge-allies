"""Dependencies shared by the WotLK race asset pipeline."""
import re
import struct
from pathlib import PurePosixPath

HIGH_ELF_EYE_TEXTURES = (
    "Character/HighElf/Female/BloodElfFemaleEyeGlowGreen.blp",
    "Character/HighElf/Male/BloodElfFemaleEyeGlowGreen.blp",
)


class UnsupportedModelVersionError(ValueError):
    """The WotLK parser cannot inspect this model layout."""


def model_path(value):
    return re.sub(r"\.(mdx|mdl)$", ".m2", value.replace("\\", "/"), flags=re.I)


def model_dependencies(path, relative):
    """Read external skins and type-0 textures from a WotLK MD20 model."""
    data = path.read_bytes()
    if len(data) < 88 or data[:4] != b"MD20":
        raise ValueError(f"{path}: en-tête M2 invalide ou tronqué")
    version = struct.unpack_from("<I", data, 4)[0]
    if version != 264:
        raise UnsupportedModelVersionError(f"{path}: version M2 {version} incompatible avec WotLK (264)")
    views = struct.unpack_from("<I", data, 68)[0]
    # Each skin profile is an external file in the WotLK format.
    if views > 4:
        raise ValueError(f"{path}: nombre de profils skin invalide : {views}")
    model = PurePosixPath(model_path(relative))
    dependencies = [str(model.with_name(f"{model.stem}{i:02d}.skin")) for i in range(views)]
    count, offset = struct.unpack_from("<2I", data, 80)
    if count and (offset < 88 or offset + count * 16 > len(data)):
        raise ValueError(f"{path}: tableau de textures M2 hors limites")
    for i in range(count):
        kind, _, size, start = struct.unpack_from("<4I", data, offset + i * 16)
        if kind != 0:
            continue
        if not size or start < 88 or start + size > len(data):
            raise ValueError(f"{path}: nom de texture M2 hors limites")
        name = data[start:start + size]
        texture = name.split(b"\0", 1)[0].decode("utf-8").replace("\\", "/")
        if not texture or texture.startswith("/") or ":" in texture or ".." in texture.split("/"):
            raise ValueError(f"{path}: chemin de texture M2 invalide : {texture!r}")
        if not PurePosixPath(texture).suffix:
            texture += ".blp"
        dependencies.append(texture)
    return dependencies


def player_rows(dbs, male, female):
    """Follow player display references, rejecting dangling source IDs."""
    def select(name, ids):
        if not ids:
            return []
        db = dbs.get(name)
        if db is None:
            raise ValueError(f"{name}.dbc absent pour les IDs joueur {sorted(ids)}")
        rows = [r for r in db.recs if db.u32(r, 0) in ids]
        missing = ids - {db.u32(r, 0) for r in rows}
        if missing or 0 in ids:
            raise ValueError(f"{db.path}: références joueur invalides : {sorted(missing or {0})}")
        return rows

    displays = select("CreatureDisplayInfo", {male, female})
    cdi = dbs["CreatureDisplayInfo"]
    models = select("CreatureModelData", {cdi.u32(r, 1) for r in displays})
    extras = select("CreatureDisplayInfoExtra", {cdi.u32(r, 3) for r in displays if cdi.u32(r, 3)})
    return displays, models, extras
