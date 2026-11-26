"""Lecture des portraits PNG/BLP partagée par l'extraction et la fusion."""
import re
import struct
from pathlib import Path

TC_RE = re.compile(r'\["([A-Za-z][A-Za-z0-9_]*)"\]\s*=\s*\{\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\}')


def crop_frac(img, l, r, t, b):
    w, h = img.size
    return img.crop((round(l * w), round(t * h), round(r * w), round(b * h)))


def load_blp(path):
    """BLP2 ARGB non compressé ; PNG, palette et DXT via Pillow."""
    from PIL import Image
    data = Path(path).read_bytes()
    if data[:4] == b"BLP2" and len(data) >= 148:
        _, encoding, _, _, _, width, height = struct.unpack_from("<IBBBBII", data, 4)
        if encoding == 3:
            offset = struct.unpack_from("<I", data, 20)[0]
            size = width * height * 4
            if not width or not height or offset < 148 or offset + size > len(data):
                raise ValueError(f"{path}: pixels BLP2 ARGB invalides ou tronqués")
            return Image.frombytes("RGBA", (width, height), data[offset:offset + size], "raw", "BGRA")
    with Image.open(path) as image:
        return image.convert("RGBA")


def recolor_green_to_blue(image, shift=100):
    """Tourne les teintes vertes saturées vers le bleu ; renvoie None s'il n'y en a pas.

    La chair et les ombres gardent exactement leurs pixels d'origine.
    """
    from PIL import Image
    image = image.convert("RGBA")
    red, green, blue, alpha = image.split()
    original = Image.merge("RGB", (red, green, blue))
    hue, saturation, value = original.convert("HSV").split()
    # PIL : teinte sur 0-255 pour 360° ; vert ≈ 55°-175°
    lo, hi = round(55 * 255 / 360), round(175 * 255 / 360)
    in_hue = hue.point([255 if lo <= i <= hi else 0 for i in range(256)])
    saturated = saturation.point([255 if i >= 64 else 0 for i in range(256)])
    mask = Image.composite(in_hue, Image.new("L", image.size, 0), saturated)
    if mask.getbbox() is None:
        return None
    shifted = hue.point([(i + round(shift * 255 / 360)) % 256 for i in range(256)])
    recolored = Image.merge("HSV", (shifted, saturation, value)).convert("RGB")
    rgb = Image.composite(recolored, original, mask)
    return Image.merge("RGBA", (*rgb.split(), alpha))


def recolor_character_skin(image, tone):
    """Tint skin hues without changing warm details or transparency."""
    from PIL import Image
    palettes = {
        "brown": (55, 175, 24, 0.70, 85, 1.0),
        "red": (55, 175, 7, 0.90, 85, 1.0),
        "forest": (150, 285, 105, 0.90, 210, 0.85),
        "ice": (150, 285, 195, 1.20, 210, 0.55),
    }
    if tone not in palettes:
        raise ValueError(f"Teinte de peau inconnue : {tone!r}")
    low, high, target, brightness, center, saturation_scale = palettes[tone]
    image = image.convert("RGBA")
    rgb = image.convert("RGB")
    hue, saturation, value = rgb.convert("HSV").split()
    lo, hi = round(low * 255 / 360), round(high * 255 / 360)
    skin = hue.point([255 if lo <= i <= hi else 0 for i in range(256)])
    saturated = saturation.point([255 if i >= 32 else 0 for i in range(256)])
    mask = Image.composite(skin, Image.new("L", image.size, 0), saturated)
    if mask.getbbox() is None:
        return None
    center = round(center * 255 / 360)
    hue = hue.point([round(target * 255 / 360 + (i - center) * 0.10) % 256
                     for i in range(256)])
    value = value.point([min(255, round(i * brightness)) for i in range(256)])
    if saturation_scale != 1.0:
        saturation = saturation.point([round(i * saturation_scale) for i in range(256)])
    recolored = Image.merge("HSV", (hue, saturation, value)).convert("RGB")
    result = Image.composite(recolored, rgb, mask)
    return Image.merge("RGBA", (*result.split(), image.getchannel("A")))


def save_blp_argb(image, path):
    """BLP2 palettisé opaque, niveau initial préservé et mipmaps jusqu'à 1 x 1."""
    from PIL import Image
    image = image.convert("RGB")
    base = image.quantize(256, method=Image.MEDIANCUT, dither=Image.NONE)
    palette = base.getpalette()[:768]
    palette += [0] * (768 - len(palette))
    palette_bytes = b"".join(bytes((palette[i + 2], palette[i + 1], palette[i], 255)) for i in range(0, 768, 3))
    levels, level = [], image
    while True:
        indexed = base if not levels else level.quantize(palette=base, dither=Image.NONE)
        levels.append(indexed.tobytes())
        if max(level.size) == 1:
            break
        level = level.resize((max(1, level.width // 2), max(1, level.height // 2)), Image.LANCZOS)
    offsets, sizes, position = [0] * 16, [0] * 16, 148 + 1024
    for i, data in enumerate(levels):
        offsets[i], sizes[i] = position, len(data)
        position += len(data)
    header = (b"BLP2" + struct.pack("<I4B2I", 1, 1, 0, 8, 1, *image.size)
              + struct.pack("<16I", *offsets) + struct.pack("<16I", *sizes) + palette_bytes)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(header + b"".join(levels))
