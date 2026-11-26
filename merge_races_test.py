import json
import re
import shutil
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from execution_log import run_logged
from merge_races import (STR_COLS, available_races_markdown, ci_find, extracted_portrait,
                         inject_race_variant_controls, load_tables,
                         merge_dbc_and_files, patch_atlas, patch_runtime_race_layout,
                         recolor_skin_textures, remap_model_texture_paths, remove_non_playable_race,
                         select_skin_colors, variant_model_sexes)
from race_assets import model_dependencies, model_path, player_rows
from race_images import load_blp, recolor_character_skin, save_blp_argb

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None


NS = {"ui": "http://www.blizzard.com/wow/ui/"}
SOURCE = (Path(__file__).parent
          / "02-HD-Clean/patch-X.mpq/Interface/GlueXML/CharacterCreate.xml")


class RaceVariantControlsTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8-sig")
        self.patched = inject_race_variant_controls(self.source)
        self.root = ET.fromstring(self.patched)

    def named(self, name):
        return self.root.find(f".//*[@name='{name}']")

    def test_text_regions_belong_to_layers_not_frames(self):
        parents = {child: parent for parent in self.root.iter() for child in parent}
        label = self.named("CharCreateRaceVariantLabel")
        self.assertEqual(parents[label].tag, f"{{{NS['ui']}}}Layer")
        for frames in self.root.findall(".//ui:Frames", NS):
            self.assertEqual(frames.findall("ui:FontString", NS), [])

    def test_arrows_match_existing_customization_controls(self):
        template = self.named("CharCreateCustomizationButtonTemplate")
        for suffix, original_name in (("Previous", "$parentLeftButton"),
                                      ("Next", "$parentRightButton")):
            with self.subTest(suffix=suffix):
                button = self.named(f"CharCreateRaceVariant{suffix}")
                original = template.find(f".//*[@name='{original_name}']")
                for tag in ("Size", "NormalTexture", "PushedTexture", "HighlightTexture"):
                    self.assertEqual(button.find(f"ui:{tag}", NS).attrib,
                                     original.find(f"ui:{tag}", NS).attrib)

    def test_selector_is_above_skin_without_moving_existing_controls(self):
        row = self.named("CharCreateRaceVariantRow")
        self.assertIsNotNone(row)
        anchor = row.find("ui:Anchors/ui:Anchor", NS)
        self.assertEqual(anchor.get("point"), "BOTTOM")
        self.assertEqual(anchor.get("relativeTo"), "CharCreateCustomizationButton1")
        self.assertEqual(anchor.get("relativePoint"), "TOP")
        self.assertGreaterEqual(float(anchor.get("y", "0")), 0)
        source_root = ET.fromstring(self.source)
        for name in ("CharCreateRandomizeButton", "CharCreateClassFrame"):
            self.assertEqual(ET.tostring(self.named(name)),
                             ET.tostring(source_root.find(f".//*[@name='{name}']")))
        self.assertEqual(inject_race_variant_controls(self.patched), self.patched)


class VariantModelSexesTests(unittest.TestCase):
    def test_missing_female_model_is_not_offered(self):
        races = SOURCE.parents[4] / "03-Races"
        for folder, expected in (("24-Forest-Troll", [0]), ("25-Ice-Troll", [0]),
                                 ("12-Zandalari-Troll", [0, 1]), ("28-Drakkari-Troll", [0, 1]),
                                 ("23-Fel-Orc", [0, 1]), ("49-Mag-har-Orc", [0, 1]),
                                 ("16-Kul-Tiran", [0, 1]), ("48-Dark-Iron-Dwarf", [0, 1]),
                                 ("66-Highmountain-Tauren", [0, 1])):
            with self.subTest(folder=folder):
                root = races / folder
                dbs = load_tables(root / "DBFilesClient")
                self.assertEqual(variant_model_sexes(dbs, int(folder.split("-")[0]), root), expected)


@unittest.skipIf(LuaRuntime is None, "Install lupa to execute the generated Lua 5.1 behavior tests")
class RaceVariantRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        parent = SOURCE.with_name("GlueParent.lua").read_text(encoding="utf-8-sig")
        self.lua.execute("\n".join(re.findall(r"^SEX_(?:MALE|FEMALE)\s*=\s*\d+;", parent, re.M)))
        self.lua.execute("""
            table.getn = table.getn or function(t) return #t end
            strupper = string.upper
            NUM_CHAR_CUSTOMIZATIONS = 5
            MAX_RACES = 14
            selectedRace, selectedSex = 1, SEX_MALE
            hair, facial = "NORMAL", "NORMAL"
            HAIR_NORMAL_STYLE, HAIR_NORMAL_COLOR, FACIAL_HAIR_NORMAL = "Style", "Color", "Tusks"
            function GetHairCustomization() return hair end
            function GetFacialHairCustomization() return facial end
            function GetSelectedRace() return selectedRace end
            function GetSelectedSex() return selectedSex end
            function SetSelectedRace(index) selectedRace = index end
            function message(text) error(text) end
            function frame(name)
                local f = {name = name, shown = true, height = 64}
                function f:Hide() self.shown = false end
                function f:Show() self.shown = true end
                function f:IsShown() return self.shown end
                function f:IsEnabled() return true end
                function f:GetName() return self.name end
                function f:GetHeight() return self.height end
                function f:ClearAllPoints() self.anchor = nil end
                function f:SetPoint(point, target, relative, x, y)
                    self.anchor = {point, target, relative, x or 0, y or 0}
                end
                function f:SetText(text) self.textValue = text end
                function f:SetSize() end
                function f:SetTexCoord() end
                f.text = {SetText = function() end}
                return f
            end
            CharacterCreateFrame = {customizationType = 1}
            CharCreateCustomizationFrame = frame("customization")
            CharCreateCustomizationFrameBanner = frame("banner")
            CharCreateRaceButtonsFrame = frame("races")
            CharCreateRandomizeButton = frame("random")
            BANNER_DEFAULT_SIZE = {200, 308}
            BANNER_DEFAULT_TEXTURE_COORDS = {0, 1, 0, 1}
            for i = 1, 14 do
                local name = "CharCreateCustomizationButton"..i
                _G[name] = frame(name)
                _G[name.."RightButton"] = frame(name.."RightButton")
                _G["CharCreateRaceButton"..i] = frame("race"..i)
            end
            CharCreateRaceVariantPrevious = frame("previous")
            CharCreateRaceVariantNext = frame("next")
            CharCreateRaceVariantLabel = frame("label")
            function CharacterCreateEnumerateRaces(...) end
            function CharacterCreate_OnShow() end
            function CharacterRace_OnClick(self, index) selectedRace = index end
            function CharacterCreate_Forward() end
            function CharacterCreate_Back() end
            function CharacterCreate_Randomize() end
            function SetCharacterGender(sex)
                selectedSex = sex
                CharacterCreateEnumerateRaces(GetAvailableRaces())
            end
            function GetAvailableRaces()
                return "Troll", "TROLL", 1, "Zandalari", "ZANDALARI", 1,
                       "Forest", "FOREST", 1, "Ice", "ICE", 1, "Drakkari", "DRAKKARI", 1,
                       "Human", "HUMAN", 1, "Kul Tiran", "KUL_TIRAN", 1,
                       "Orc", "ORC", 1, "Fel Orc", "FEL_ORC", 1, "Mag'har", "MAGHAR_ORC", 1,
                       "Dwarf", "DWARF", 1, "Dark Iron", "DARK_IRON_DWARF", 1,
                       "Tauren", "TAUREN", 1, "Highmountain", "HIGHMOUNTAIN_TAUREN", 1
            end
        """)
        source = SOURCE.with_suffix(".lua").read_text(encoding="utf-8-sig")
        for start, end in (("function CharacterCreate_UpdateHairCustomization()",
                            "function CharacterCreate_Forward()"),
                           ("function CharCreateCustomizationFrame_OnShow ()",
                            "function CharacterClass_OnClick")):
            self.lua.execute(source[source.index(start):source.index(end)])
        self.lua.execute(patch_runtime_race_layout(
            "function CharacterCreateEnumerateRaces(...) end",
            [["HUMAN", "DWARF"], ["ORC", "TROLL", "TAUREN"]], -75, -22, 32,
            ["ZANDALARI", "FOREST", "ICE", "DRAKKARI", "KUL_TIRAN", "FEL_ORC", "MAGHAR_ORC",
             "DARK_IRON_DWARF", "HIGHMOUNTAIN_TAUREN"],
            [["TROLL", "ZANDALARI", "FOREST", "ICE", "DRAKKARI"],
             ["HUMAN", "KUL_TIRAN"], ["ORC", "FEL_ORC", "MAGHAR_ORC"],
             ["DWARF", "DARK_IRON_DWARF"], ["TAUREN", "HIGHMOUNTAIN_TAUREN"]],
            {"ZANDALARI": [0, 1], "FOREST": [0], "ICE": [0], "DRAKKARI": [0, 1],
             "KUL_TIRAN": [0, 1], "FEL_ORC": [0, 1], "MAGHAR_ORC": [0, 1],
             "DARK_IRON_DWARF": [0, 1], "HIGHMOUNTAIN_TAUREN": [0, 1]}))

    def test_selectors_are_visible_with_native_glue_sex_constants(self):
        self.lua.execute("""
            for _, sex in ipairs({SEX_MALE, SEX_FEMALE}) do
                SetCharacterGender(sex)
                for _, pair in ipairs({{1, 2}, {6, 7}, {8, 9}, {11, 12}, {13, 14}}) do
                    selectedRace = pair[1]
                    CharCreateCustomizationFrame_OnShow()
                    assert(CharCreateRaceVariantPrevious:IsShown())
                    assert(CharCreateRaceVariantNext:IsShown())
                    assert(CharCreateRaceVariantLabel:IsShown())
                    local base = selectedRace
                    MergeRaceVariantStep(1)
                    assert(selectedRace == pair[2])
                    MergeRaceVariantStep(-1)
                    assert(selectedRace == base)
                end
            end
        """)

    def test_layout_recovers_after_options_are_hidden_then_shown(self):
        self.lua.execute("""
            for _, value in ipairs({"NORMAL", "NONE", "NORMAL"}) do
                hair = value
                CharCreateCustomizationFrame_OnShow()
                local previous
                for i = 1, 5 do
                    local button = _G["CharCreateCustomizationButton"..i]
                    if button:IsShown() then
                        assert(button.anchor[2] == (previous or CharCreateCustomizationFrame))
                        assert(button.anchor[3] == (previous and "BOTTOM" or "TOP"))
                        assert(button.anchor[5] == (previous and 0 or -15))
                        previous = button
                    end
                end
                assert(CharCreateRandomizeButton.anchor[2] == _G[previous:GetName().."RightButton"])
                assert(CharCreateCustomizationButton3:IsShown() == (value == "NORMAL"))
                assert(CharCreateCustomizationButton4:IsShown() == (value == "NORMAL"))
            end
        """)

    def test_female_cycle_skips_missing_models_and_gender_change_returns_to_base(self):
        self.lua.execute("""
            CharacterCreateEnumerateRaces(GetAvailableRaces())
            MergeRaceVariantStep(1); assert(selectedRace == 2)
            MergeRaceVariantStep(1); assert(selectedRace == 3)
            SetCharacterGender(SEX_FEMALE); assert(selectedRace == 1)
            MergeRaceVariantStep(1); assert(selectedRace == 2)
            MergeRaceVariantStep(1); assert(selectedRace == 5)
            MergeRaceVariantStep(1); assert(selectedRace == 1)
            MergeRaceVariantStep(-1); assert(selectedRace == 5)
            for position, expected in ipairs({1, 2, 5}) do
                math.random = function() return position end
                CharacterCreate_Randomize()
                assert(selectedRace == expected)
            end
            SetCharacterGender(SEX_MALE)
            MergeRaceVariantStep(-1); assert(selectedRace == 4)
        """)

    def test_nine_portraits_fit_within_the_previous_eight_portrait_height(self):
        cfg = json.loads((SOURCE.parents[4] / "merge-config.json").read_text(encoding="utf-8"))
        gl = cfg["glue"]
        template = ET.fromstring(SOURCE.read_text(encoding="utf-8-sig")).find(
            ".//*[@name='CharCreateRaceButtonTemplate']/ui:Size", NS)
        height = float(template.get("y"))
        columns = [[f"{faction}{i}" for i in range(9)] for faction in ("ALLIANCE", "HORDE")]
        self.lua.execute("""
            MAX_RACES = 18
            for i = 1, MAX_RACES do
                _G["CharCreateRaceButton"..i] = frame("race"..i)
            end
        """)
        for i in range(1, 19):
            self.lua.globals()[f"CharCreateRaceButton{i}"].height = height
        self.lua.execute(patch_runtime_race_layout(
            "function CharacterCreateEnumerateRaces(...) end",
            columns, gl["top_y"], gl["gap"], gl["x"]))
        args = [value for column in columns for token in column for value in (token, token, 1)]
        self.lua.globals().CharacterCreateEnumerateRaces(*args)
        previous_height = 8 * height + 7 * 22
        for start in (1, 10):
            positions = [self.lua.globals()[f"CharCreateRaceButton{i}"].anchor[5]
                         for i in range(start, start + 9)]
            self.assertEqual(positions[0], gl["top_y"])
            self.assertTrue(all(a - b >= height for a, b in zip(positions, positions[1:])))
            self.assertLessEqual(positions[0] - positions[-1] + height, previous_height)


class AddedRacesTests(unittest.TestCase):
    def test_ogre_swap_keeps_models_customizations_and_portraits_together(self):
        root = SOURCE.parents[4]
        cfg = json.loads((root / "merge-config.json").read_text(encoding="utf-8"))
        cfg["races"] = [r for r in cfg["races"] if r["name"] in ("Ogre", "Murloc")]
        source = root / "03-Races/53-Ogre"
        original = load_tables(source / "DBFilesClient")
        with tempfile.TemporaryDirectory() as tmp, patch("merge_races.log"):
            out = Path(tmp)
            shutil.copytree(root / cfg["base"] / "DBFilesClient", out / "DBFilesClient")
            dbs = load_tables(out / "DBFilesClient")
            results, _, _ = merge_dbc_and_files(cfg, root, out, dbs)
            dbs = load_tables(out / "DBFilesClient")
            races = dbs["ChrRaces"]
            ogre = next(x for x in results if x["name"] == "Ogre")
            target = ogre["target"]
            row = next(r for r in races.recs if races.u32(r, 0) == target)
            original_race = original["ChrRaces"].recs[0]
            self.assertEqual(races.u32(row, 13), 1)
            displays, models, _ = player_rows(dbs, races.u32(row, 4), races.u32(row, 5))
            cdi, cmd = dbs["CreatureDisplayInfo"], dbs["CreatureModelData"]
            for sex, expected in ((0, "OgreMagePC"), (1, "OgrePC")):
                display = next(r for r in displays if cdi.u32(r, 0) == races.u32(row, 4 + sex))
                model = next(r for r in models if cmd.u32(r, 0) == cdi.u32(display, 1))
                path = model_path(cmd.s(cmd.u32(model, 2)))
                self.assertEqual(Path(path).stem, expected)
                self.assertEqual(ci_find(out, path).read_bytes(), ci_find(source, path).read_bytes())
                for dep in model_dependencies(ci_find(out, path), path):
                    self.assertIsNotNone(ci_find(out, dep), dep)
                self.assertEqual(races.s(races.u32(row, 65 + sex)),
                                 original["ChrRaces"].s(
                                     original["ChrRaces"].u32(original_race, 66 - sex)))
                for name, race_col, pk in (("CharSections", 1, True),
                                           ("CharHairGeosets", 1, True),
                                           ("CharacterFacialHairStyles", 0, False)):
                    db, src = dbs[name], original[name]
                    expected_rows = []
                    for r in src.recs:
                        if src.u32(r, race_col) == 53 and src.u32(r, race_col + 1) == 1 - sex:
                            r = bytearray(r)
                            src.set_u32(r, race_col, target)
                            src.set_u32(r, race_col + 1, sex)
                            expected_rows.append(src.sig(r, STR_COLS.get(name, []))[int(pk):])
                    actual_rows = [db.sig(r, STR_COLS.get(name, []))[int(pk):] for r in db.recs
                                   if db.u32(r, race_col) == target
                                   and db.u32(r, race_col + 1) == sex]
                    self.assertCountEqual(actual_rows, expected_rows)
                portrait = extracted_portrait(cfg, root, ogre, "MALE" if sex == 0 else "FEMALE")
                self.assertEqual(portrait, source / "Portraits" / ("female.png" if sex == 0 else "male.png"))
                outfits = dbs["CharStartOutfit"]
                outfit = next(r for r in outfits.recs if r[4:7] == bytes((target, 1, sex)))
                donor = next(r for r in outfits.recs if r[4:7] == bytes((2, 1, sex)))
                self.assertEqual(outfit[5:], donor[5:])
            murloc = next(x for x in results if x["name"] == "Murloc")
            row = next(r for r in races.recs if races.u32(r, 0) == murloc["target"])
            self.assertEqual(races.u32(row, 13), 0)
            player_rows(dbs, races.u32(row, 4), races.u32(row, 5))
            for sex in ("MALE", "FEMALE"):
                self.assertTrue(extracted_portrait(cfg, root, murloc, sex).is_file())


class RaceAtlasTests(unittest.TestCase):
    def test_expanded_atlas_preserves_original_cells_and_portrait_resolution(self):
        from PIL import Image, ImageChops

        root = SOURCE.parents[4]
        cfg = json.loads((root / "merge-config.json").read_text(encoding="utf-8"))
        relative = "Interface/Glues/CharacterCreate/UI-CharacterCreate-Races_Round.blp"
        original = ci_find(root / cfg["base"], relative)
        image = load_blp(original)
        race = {"name": "Murloc", "token": "MURLOC", "folder": "30-Murloc"}
        placements = [{"race": race, "gender": "MALE", "box": (1, 1.125, 0, .25)}]
        with tempfile.TemporaryDirectory() as tmp, patch("merge_races.log"):
            out = Path(tmp)
            atlas = out / relative
            atlas.parent.mkdir(parents=True)
            shutil.copy2(original, atlas)
            expanded = patch_atlas(
                cfg, root, out, placements, {"HUMAN_MALE": (0, .125, 0, .25)},
                out / "manual", relative, width_scale=2)
            self.assertEqual(expanded[0], relative)
            result = load_blp(out / expanded[1])
            self.assertEqual(result.size, (image.width * 2, image.height))
            self.assertEqual(atlas.read_bytes(), original.read_bytes())
            self.assertEqual(result.crop((0, 0, image.width, image.height)).tobytes(), image.tobytes())
            cell = result.crop((image.width, 0, image.width + image.width // 8, image.height // 4))
            mask = image.crop((0, 0, image.width // 8, image.height // 4)).getchannel("A")
            source = load_blp(root / cfg["races_dir"] / race["folder"] / "Portraits/male.png")
            expected = source.resize(mask.size, Image.LANCZOS)
            expected.putalpha(ImageChops.multiply(expected.getchannel("A"), mask))
            self.assertEqual(cell.tobytes(), expected.tobytes())


class RaceAssetIsolationTests(unittest.TestCase):
    def test_extensionless_murloc_texture_dependency_resolves_to_existing_blp(self):
        root = SOURCE.parents[4] / "03-Races/30-Murloc"
        relative = "Creature/WhimMurloc/WhimPlayer.m2"
        dependencies = model_dependencies(ci_find(root, relative), relative)
        reflection = "creature/whimmurloc/armorreflect4.blp"
        self.assertIn(reflection, dependencies)
        self.assertTrue(ci_find(root, reflection).is_file())
        self.assertNotIn(reflection.removesuffix(".blp"), dependencies)

    def test_model_texture_paths_are_relocated_without_changing_geometry(self):
        original = b"Character/Orc/Male/OrcMaleSkin.blp\0"
        data = bytearray(104) + original
        struct.pack_into("<II", data, 80, 1, 88)
        struct.pack_into("<4I", data, 88, 0, 0, len(original), 104)
        target = "Variants/Maghar/Character/Orc/Male/OrcMaleSkin.blp"
        changed = remap_model_texture_paths(data, {original[:-1].decode().lower(): target})
        self.assertEqual(changed[:96], data[:96])
        self.assertEqual(changed[104:len(data)], original)
        size, offset = struct.unpack_from("<II", changed, 96)
        self.assertEqual(changed[offset:offset + size], target.encode() + b"\0")

    def test_replacing_npc_clears_old_customizations_and_rejects_playable_races(self):
        dbs = load_tables(SOURCE.parents[2] / "DBFilesClient")
        sections = dbs["CharSections"]
        row = bytearray(sections.recs[0])
        sections.set_u32(row, 1, 16)
        sections.recs.append(row)
        skills = dbs["SkillRaceClassInfo"]
        for mask in (1 << 15, (1 << 15) | (1 << 7), 0):
            record = bytearray(skills.recs[0])
            skills.set_u32(record, 2, mask)
            skills.recs.append(record)
        displays = [bytes(r) for r in dbs["CreatureDisplayInfo"].recs]
        remove_non_playable_race(dbs, 16)
        self.assertFalse(any(sections.u32(r, 1) == 16 for r in sections.recs))
        self.assertNotIn(1 << 15, [skills.u32(r, 2) for r in skills.recs])
        self.assertEqual([skills.u32(r, 2) for r in skills.recs][-2:], [1 << 7, 0])
        self.assertEqual([bytes(r) for r in dbs["CreatureDisplayInfo"].recs], displays)
        with self.assertRaisesRegex(ValueError, "jouable"):
            remove_non_playable_race(dbs, 1)


class BLPTextureWriterTests(unittest.TestCase):
    def test_directly_sampled_atlases_have_complete_mip_chains(self):
        from PIL import Image
        for size in ((8, 8), (8, 4)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "extra.blp"
                save_blp_argb(Image.new("RGB", size, (100, 60, 30)), path)
                data = path.read_bytes()
                offsets = struct.unpack_from("<16I", data, 20)
                lengths = struct.unpack_from("<16I", data, 84)
                width, height = size
                level = 0
                while True:
                    self.assertEqual(lengths[level], width * height)
                    self.assertLessEqual(offsets[level] + lengths[level], len(data))
                    if width == height == 1:
                        break
                    width, height = max(1, width // 2), max(1, height // 2)
                    level += 1
                self.assertTrue(all(length == 0 for length in lengths[level + 1:]))

    def test_top_level_retains_close_palette_colors_exactly(self):
        from PIL import Image
        image = Image.new("RGB", (4, 4))
        image.putdata([(100, 60, 30), (101, 61, 31)] * 8)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skin.blp"
            save_blp_argb(image, path)
            self.assertEqual(load_blp(path).convert("RGB").tobytes(), image.tobytes())


class OrcHDTextureTests(unittest.TestCase):
    def test_remaps_body_face_and_ear_textures_without_changing_hair_or_shared_assets(self):
        base = SOURCE.parents[2]
        db = load_tables(base / "DBFilesClient")["CharSections"]
        rows = [bytearray(next(r for r in db.recs
                               if [db.u32(r, c) for c in (1, 2, 3)] == [2, 1, section]
                               and (section != 3 or db.s(db.u32(r, 6)))))
                for section in (0, 1, 3)]
        originals = {(i, c): db.s(db.u32(row, c)).replace("\\", "/")
                     for i, row in enumerate(rows) for c in (4, 5, 6)}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for path in set(originals.values()) - {""}:
                target = out / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(base / path, target)
            before = {p: (out / p).read_bytes() for p in set(originals.values()) - {""}}
            created = recolor_skin_textures(db, rows, out, "brown", "Mag'har Orc")
            for i, c in ((0, 4), (0, 5), (1, 4), (1, 5)):
                path = db.s(db.u32(rows[i], c))
                self.assertIn(path, created)
                self.assertEqual(load_blp(out / path).size, load_blp(out / originals[i, c]).size)
            for c in (4, 5, 6):
                self.assertEqual(db.s(db.u32(rows[2], c)).replace("\\", "/"), originals[2, c])
            self.assertTrue(all((out / p).read_bytes() == data for p, data in before.items()))

    def test_tints_skin_without_recoloring_eyes_teeth_or_transparency(self):
        from PIL import Image
        image = Image.new("RGBA", (4, 1))
        image.putdata([(100, 160, 50, 180), (40, 64, 20, 0),
                       (230, 110, 30, 255), (230, 225, 210, 255)])
        for tone in ("red", "brown"):
            with self.subTest(tone=tone):
                changed = recolor_character_skin(image, tone)
                self.assertEqual(changed.getchannel("A").tobytes(), image.getchannel("A").tobytes())
                for x in (2, 3):
                    self.assertEqual(changed.getpixel((x, 0)), image.getpixel((x, 0)))
                light, dark = changed.getpixel((0, 0)), changed.getpixel((1, 0))
                self.assertGreater(light[0], light[1])
                self.assertGreater(light[1], light[2])
                self.assertGreater(light[0], dark[0])

    def test_rejects_transparent_skin_instead_of_dropping_alpha(self):
        from PIL import Image
        db = load_tables(SOURCE.parents[2] / "DBFilesClient")["CharSections"]
        row = bytearray(next(r for r in db.recs
                             if [db.u32(r, c) for c in (1, 2, 3)] == [2, 0, 0]))
        db.set_u32(row, 4, db.add_s("skin.png"))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            Image.new("RGBA", (4, 4), (60, 110, 30, 127)).save(out / "skin.png")
            with self.assertRaisesRegex(ValueError, "transparente"):
                recolor_skin_textures(db, [row], out, "brown", "Mag'har Orc")


class TrollHDTextureTests(unittest.TestCase):
    def setUp(self):
        source = SOURCE.parents[4] / "03-Races/28-Drakkari-Troll"
        self.db = load_tables(source / "DBFilesClient")["CharSections"]
        self.rows = [bytearray(r) for r in self.db.recs if self.db.u32(r, 1) == 28]

    def test_imported_hair_labels_resolve_for_direct_and_inherited_troll_appearances(self):
        root = SOURCE.parents[4]
        cfg = json.loads((root / "merge-config.json").read_text(encoding="utf-8"))
        cfg["races"] = [r for r in cfg["races"] if r["name"] in ("Forest Troll", "Drakkari Troll")]
        strings = SOURCE.with_name("GlueStrings.lua").read_text(encoding="utf-8-sig")
        labels = set(re.findall(r"(?m)^((?:HAIR|FACIAL_HAIR)_\w+)\s*=", strings))
        with tempfile.TemporaryDirectory() as tmp, patch("merge_races.log"):
            out = Path(tmp)
            shutil.copytree(root / cfg["base"] / "DBFilesClient", out / "DBFilesClient")
            dbs = load_tables(out / "DBFilesClient")
            results, _, _ = merge_dbc_and_files(cfg, root, out, dbs)
            races = dbs["ChrRaces"]
            for result in results:
                row = next(r for r in races.recs if races.u32(r, 0) == result["target"])
                for col, prefix, suffix in ((67, "HAIR_", "_STYLE"), (67, "HAIR_", "_COLOR"),
                                             (65, "FACIAL_HAIR_", ""), (66, "FACIAL_HAIR_", "")):
                    with self.subTest(race=result["name"], col=col, suffix=suffix):
                        self.assertIn(prefix + races.s(races.u32(row, col)) + suffix, labels)

    def test_source_donor_supplies_hd_assets_even_when_not_imported_as_a_race(self):
        root = SOURCE.parents[4]
        cfg = json.loads((root / "merge-config.json").read_text(encoding="utf-8"))
        cfg["races"] = [next(r for r in cfg["races"] if r["name"] == "Forest Troll")]
        rid = cfg["races"][0]["target"]
        donor = root / "03-Races/28-Drakkari-Troll"
        with tempfile.TemporaryDirectory() as tmp, patch("merge_races.log"):
            out = Path(tmp)
            shutil.copytree(root / cfg["base"] / "DBFilesClient", out / "DBFilesClient")
            dbs = load_tables(out / "DBFilesClient")
            merge_dbc_and_files(cfg, root, out, dbs)
            races = dbs["ChrRaces"]
            race = next(r for r in races.recs if races.u32(r, 0) == rid)
            _, models, _ = player_rows(dbs, races.u32(race, 4), races.u32(race, 5))
            cmd = dbs["CreatureModelData"]
            for row in models:
                path = model_path(cmd.s(cmd.u32(row, 2)))
                self.assertIn("DrakkariTroll", path)
                self.assertEqual(ci_find(out, path).read_bytes(), ci_find(donor, path).read_bytes())
                for dep in model_dependencies(ci_find(out, path), path):
                    self.assertIsNotNone(ci_find(out, dep))
            self.assertEqual(variant_model_sexes(dbs, rid, out), [0, 1])
            self.assertFalse((out / "Character/ForestTroll").exists())
            sections = dbs["CharSections"]
            rows = [r for r in sections.recs if sections.u32(r, 1) == rid]
            self.assertTrue(any(sections.s(sections.u32(r, 4)).startswith("Variants/Troll/forest/")
                                for r in rows))
            for row in rows:
                for col in (4, 5, 6):
                    path = sections.s(sections.u32(row, col))
                    if path:
                        self.assertIsNotNone(ci_find(out, path), path)

    def test_selected_skin_colors_are_contiguous_without_changing_hair_colors(self):
        hair = [bytes(r) for r in self.rows if self.db.u32(r, 3) == 3]
        selected = select_skin_colors(self.db, self.rows, [0, 1, 2, 3, 4, 8], "Forest Troll")
        for sex in (0, 1):
            for section in (0, 1, 4):
                colors = {self.db.u32(r, 9) for r in selected
                          if self.db.u32(r, 2) == sex and self.db.u32(r, 3) == section}
                self.assertEqual(colors, set(range(6)))
        self.assertEqual([bytes(r) for r in selected if self.db.u32(r, 3) == 3], hair)
        with self.assertRaisesRegex(ValueError, "absentes"):
            select_skin_colors(self.db, self.rows, [99], "Ice Troll")

    def test_forest_and_ice_tints_preserve_warm_details_and_shading(self):
        from PIL import Image
        image = Image.new("RGBA", (4, 1))
        image.putdata([(50, 130, 190, 255), (20, 52, 76, 120),
                       (220, 100, 25, 255), (230, 225, 210, 255)])
        forest = recolor_character_skin(image, "forest")
        ice = recolor_character_skin(image, "ice")
        for changed in (forest, ice):
            self.assertEqual(changed.getchannel("A").tobytes(), image.getchannel("A").tobytes())
            for x in (2, 3):
                self.assertEqual(changed.getpixel((x, 0)), image.getpixel((x, 0)))
            self.assertGreater(max(changed.getpixel((0, 0))[:3]), max(changed.getpixel((1, 0))[:3]))
        green = forest.getpixel((0, 0))
        pale_blue = ice.getpixel((0, 0))
        self.assertGreater(green[1], max(green[0], green[2]))
        self.assertGreater(pale_blue[2], pale_blue[0])
        self.assertGreater(min(pale_blue[:3]), min(green[:3]))


class AvailableRacesReportTests(unittest.TestCase):
    def setUp(self):
        self.dbs = load_tables(SOURCE.parents[2] / "DBFilesClient")
        races = self.dbs["ChrRaces"]
        row = bytearray(next(r for r in races.recs if races.u32(r, 0) == 8))
        races.set_u32(row, 0, 29)
        races.set_u32(row, 16, races.add_s("Troll des forêts"))
        races.set_u32(row, 11, races.add_s("FOREST_TROLL"))
        races.recs.append(row)
        self.dbs["CharBaseInfo"].recs.append(bytearray([29, 1]))
        self.cfg = {"glue": {"race_variants": [["Troll", "Forest Troll"]]}}
        self.results = [{"target": 29, "name": "Forest Troll"}]

    def test_lists_native_and_imported_playable_races_with_final_ids(self):
        text = available_races_markdown(self.cfg, self.dbs, self.results)
        self.assertIn("| 1 | Humain | Alliance | Human | Race principale |", text)
        self.assertIn("| 2 | Orc | Horde | Orc | Race principale |", text)
        self.assertIn("| 29 | Troll des forêts | Horde | FOREST_TROLL | Variante de Troll (ID 8) |", text)
        listed = [int(r.split("|")[1]) for r in text.splitlines()
                  if re.match(r"\| \d+ \|", r)]
        self.assertCountEqual(listed, {r[0] for r in self.dbs["CharBaseInfo"].recs})
        self.assertNotIn(16, listed)

    def test_skip_glue_does_not_claim_variant_navigation(self):
        text = available_races_markdown(self.cfg, self.dbs, self.results, include_glue=False)
        self.assertIn("| 29 | Troll des forêts | Horde | FOREST_TROLL | Race principale |", text)
        self.assertNotIn("Variante de", text)


if __name__ == "__main__":
    run_logged(unittest.main, __file__)
