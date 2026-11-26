# Adding a New Race - Step by Step Tutorial (3.3.5)

This guide provides a complete, step-by-step walkthrough on how to add fully playable custom races to a World of Warcraft 3.3.5a server based on TrinityCore. It covers every part of the process, from modifying the core, to editing DBCs, updating the database, and finally enabling the races in the game client.

[![Trinitycore](https://img.shields.io/badge/TrinityCore-supported-brightgreen?logo=worldofwarcraft&style=flat)](https://trinitycore.org/)

[![AzerothCore](https://img.shields.io/badge/Azerothcore-not%20fully%20supported-yellow?logo=worldofwarcraft&style=flat)](https://www.azerothcore.org/)

--> [More information]()

--> [Jump straight to the Tutorial](#The-Tutorial)

## Credits to

**Tuerny** - for the original guide on Wowcreador (https://wowcreador.com/threads/tutorial-creacion-razas-custom-3-3-5a-tc-parte-1-4-core.987/)

**Crxgiles** (Edd the Duck IN Storyland) - For the translation from Spanish to English (https://discord.com/channels/407664041016688662/1338242825405468732)

**[Hex](https://github.com/Hextv)** - For editing the guide and making the repo (https://github.com/Hextv/Adding-a-New-Race-Step-by-Step-Tutorial-3.3.5)

## Tools for the Tutorial

### Latest execution logs

`run_extract.bat` recreates the repository's `Logs/` directory at startup.
Each Python script keeps its console output and also writes stdout, stderr and
uncaught exception tracebacks to `Logs/<script>.log` in UTF-8. Repeated calls to
the same script within that pipeline append to its file, so the CoA and HD
extraction logs are both retained. Only the current pipeline is kept; the next
BAT launch removes all previous logs.

Running a Python entry point directly starts a new execution and recreates
`Logs/` too, including for `--help`, `--list` and dry runs. Importing the modules
does not touch logs. `REFORGE_PIPELINE_LOGS=1` is set locally by the BAT to share
its freshly initialized log directory. Do not run independent pipelines
concurrently in the same checkout. Logs are ignored by Git.

MPQ extraction stops on archive-open, enumeration, unsafe-path or local IO errors.
Individual source-file open, read and size errors follow the retry policy below.
Cache signatures now use nanosecond modification times, detecting same-size
updates within a second. Existing second-resolution markers are rebuilt once.
The cleaner respects numeric extraction-layer prefixes beyond 99, and reads only
20 bytes per DBC for header reports. Exact-case asset lookups avoid directory
scans; MPQ extraction writes buffer views without copying each chunk into a new
Python bytes object. Output paths overlapping configured source directories are
rejected before destructive cleanup.

StormLib extraction uses one-byte C++ boolean return values, matching the bundled
DLL; reading them as Windows `BOOL` could mistake the end of enumeration for
success and repeat the last filename. The duplicate-loop safeguard remains active.
Pre-fix extraction cache markers are invalidated once, including nanosecond markers.
The BAT stops immediately after any failed step, and multiple extraction profiles
also stop on their first failure rather than continuing with stale inputs.

Every source file gets up to **three total attempts**, reopening it from the
beginning each time. Failures are logged as `[retry]`; after the third failure,
the partial file is removed, an `[anomalie]` entry records its archive, name and
error, and extraction continues with the remaining files. The profile summary
explicitly warns that the merged result may be incomplete.

There are no filename-specific corruption exclusions. Repeated internal path
separators are normalized, but rooted paths, parent traversal and drive-qualified
paths remain rejected. Successfully extracted aliases cannot be overwritten by
a later damaged alias.

Archives with skipped failed files get no completion marker and are retried on
the next launch. Earlier cache markers are invalidated once so files previously
excluded by name are attempted again. A recovered file does not prevent caching.

Resource checks and zoom-background generation accept both the merged `01-HD/`
output and the older `01-HD/*.mpq/` layout. Extensionless M2 texture references
are resolved as `.blp` dependencies without modifying the original models.
Missing resources are still reported; these checks do not manufacture absent
models, textures or portraits.

### Building the merged MPQ with StormLib

Run `python merge_races.py` with **64-bit Python on Windows**. The bundled
`StormLib.dll` is a Windows x64 Unicode library.

In [merge-config.json](./merge-config.json):

- `base` is the effective inherited HD directory. The corresponding HD patches
  must already be installed on the target client.
- `output` is the directory containing the **differential patch**, not an archive
  or a complete copy of the HD base.
- `mpq_output` is the **absolute path of the final MPQ file**, for example
  `C:/Jeux/WoW/Data/patch-Z.MPQ`. Change it to your client installation path.
- `stormlib_path` is the DLL path, relative to the configuration file or absolute.

The configuration adds Pandaren to the Alliance (source 20, target 25) and Naga
to the Horde (source 21, target 13), last in their respective faction columns.
The Pandaren extraction is Horde-aligned; the merge applies the configured
Alliance faction, language and starting outfits.

The script packs the working directory into a WotLK-compatible MPQ v2, using zlib
compression, relative archive paths, a listfile and file attributes. Reports and
the `_manual` previews remain outside the archive. An existing destination MPQ is
replaced only after all files have been added and the archive closed successfully.
Close the WoW client before replacing a patch. `--skip-glue` skips UI changes but
still builds the MPQ on Windows. On macOS and Linux, MPQ creation is automatically
skipped before validating `mpq_output` or loading the DLL; the merge, reports and
previews are still generated (Pillow is required for previews). On Windows, a
missing or incompatible DLL stops execution before the working directory is rebuilt.

Each successful generation also writes `available-races.md` next to
`merge-report.md` and `race-mapping.json` (in `04-Merge` with the current
configuration), outside the MPQ. It lists all final playable client races,
including inherited races and hidden model variants, with their localized names
(French preferred), factions, final client IDs, tokens, and parent race for
variants. NPC-only races are excluded. This is a client inventory, not a guarantee
of server-side support. With `--skip-glue`, no variant navigation is reported.

The merge uses a full working copy to edit DBC/GlueXML and resolve dependencies,
then removes every file byte-identical to `base` before packaging. Paths are
compared case-insensitively; file timestamps are not used to decide equality.
Only new or modified files, plus the explicitly extracted High Elf blue-eye
textures, remain in `output` and the final MPQ. Unchanged
FelOrc/Naga/NPC assets are inherited, not duplicated. The HD source is untouched.
Load the differential MPQ **after** the same HD baseline used for the merge.

### Classes per race

Set `allowed_classes` inside each entry of `races`, using English class names:

```json
{
  "name": "High Elf",
  "allowed_classes": ["Warrior", "Hunter", "Rogue", "Priest", "Mage"]
}
```

Supported names are `Warrior`, `Paladin`, `Hunter`, `Rogue`, `Priest`,
`Death Knight`, `Shaman`, `Mage`, `Warlock`, and `Druid` (case-insensitive).
The list selects the race's client-side classes directly, including classes not
listed in its source extraction. The server must support the same combinations.
The current configuration preserves the nine previously enabled classes for each
imported race; add `Death Knight` explicitly to enable it. If the list is omitted,
compatible source classes are retained, or all WotLK classes when the source has
no class entries. Empty lists, unknown names, numeric IDs and duplicates are
rejected. The old global `allowed_classes` and per-race `classes` keys must be
migrated, not silently ignored.

### Race button order and position

`glue.race_order` sets the visual order from top to bottom in each faction column,
using readable race names rather than numeric IDs or client button slots:

```json
"glue": {
  "top_y": -75,
  "gap": -22,
  "x": 32,
  "round_icons": true,
  "race_order": {
    "Alliance": ["Human", "Dwarf", "Night Elf", "Gnome", "Draenei", "Worgen", "High Elf"],
    "Horde": ["Orc", "Undead", "Tauren", "Troll", "Blood Elf", "Goblin", "Broken"]
  }
}
```

In this example Blood Elf is above Goblin, followed by Broken. Move names within
a faction's list to reorder its buttons. Imported races use their configured
`name`; existing races use their client token (`Blood Elf`/`BloodElf` and
`Night Elf`/`NightElf` are equivalent; `Undead` also accepts `Scourge`).
Matching ignores case, spaces and underscores. Omitted playable races are
appended in ascending ID order; without `race_order`, the existing ascending-ID
layout is preserved. Duplicate, ambiguous, unknown, non-playable or wrong-faction
names and numeric IDs stop the merge explicitly.
The XML supplies the initial anchors; after every `CharacterCreateEnumerateRaces`
call, the Lua layout matches the actual `GetAvailableRaces` tokens to their
buttons and reapplies the configured positions. It does not assume that native
slots follow numeric race-ID order. Available buttons are explicitly shown,
including after a previous enumeration hid them. Races not returned by the client
do not leave empty positions. Client button IDs and race-selection slots remain
unchanged, so moving a button does not select a different race.
`top_y`, `gap` and `x` control the columns' vertical origin, spacing and horizontal
inset. The current `gap: -12` gives a 64-pixel vertical step for 52-pixel buttons:
nine portraits per faction fit within the height previously used by eight at
`gap: -22`, without shrinking the portraits. Re-run `merge_races.py` after
editing the configuration.

### Race model variants in character creation

`glue.hidden_races` removes selected races from the icon grid, and
`glue.race_variants` groups them with a visible base race. During character
customization, previous/next buttons switch the selected client race and its
preview model while keeping those variants out of the main race list:

```json
"hidden_races": [
  "Zandalari Troll", "Forest Troll", "Ice Troll", "Drakkari Troll",
  "Fel Orc", "Mag'har Orc", "Kul Tiran", "Dark Iron Dwarf", "Highmountain Tauren"
],
"race_variants": [
  ["Troll", "Zandalari Troll", "Forest Troll", "Ice Troll", "Drakkari Troll"],
  ["Orc", "Fel Orc", "Mag'har Orc"],
  ["Human", "Kul Tiran"],
  ["Dwarf", "Dark Iron Dwarf"],
  ["Tauren", "Highmountain Tauren"]
]
```

The selector occupies a separate row above Skin, using the same arrow textures
as the other customization controls, without moving the appearance randomizer.
After a model change, visible customization options are stacked again at a
uniform spacing, and the randomizer follows the last visible option.
Variants whose female display reuses the male model are excluded from the female
selector and randomizer. Switching to female while such a variant is selected
returns to its base race. Forest and Ice Troll now use genuine female HD models
and are available for both sexes.

Imported hair and facial-hair customization tokens are normalized to uppercase
to match the case-sensitive GlueStrings keys. This keeps the hairstyle, hair
color and facial-hair controls visible for Forest, Ice and Drakkari Trolls whose
source DBCs use `Normal` instead of `NORMAL`. Regenerate the MPQ to apply the fix.

The variants still use their own client race IDs so the 3.3.5 character-creation
preview can load each model. They are not yet a persistent appearance choice on
the existing Troll, Orc, Human, Dwarf, or Tauren server races: the server must later map/support
those IDs.

### Client race IDs

The configuration prefers native WoW IDs, not the IDs assigned by the CoA
extraction pack. WotLK NPC races retain their original race identity when made
playable; later races use their official IDs where they fit within the 32-bit
race-mask limit.

| Race | Previous client ID | Current client ID | Reference |
|---|---|---|---|
| Goblin | 9 | 9 | Native |
| Fel Orc | 13 | 12 | Native WotLK NPC |
| Naga | 27 | 13 | Native WotLK NPC |
| Broken | 24 | 14 | Native WotLK NPC |
| Forest Troll | 29 | 18 | Native WotLK NPC |
| Ice Troll | 25 | 21 | Native WotLK NPC |
| Worgen | 22 | 22 | Official |
| High Elf | 23 | 23 | Custom |
| Murloc (Alliance) | - | 24 | Custom; source ID 30 |
| Pandaren (Alliance) | 26 | 25 | Official Alliance ID, not Horde ID 26 |
| Drakkari Troll | 28 | 26 | Custom; moved to free Highmountain's official ID 28 |
| Ogre (Horde) | - | 27 | Custom; source ID 53, model sexes swapped |
| Highmountain Tauren | - | 28 | Official; source ID 66 |
| Mag'har Orc | 14 | 29 | Custom; official ID 36 and source ID 49 exceed 32 |
| Dark Iron Dwarf | - | 30 | Custom; official ID 34 and source ID 48 exceed 32 |
| Zandalari Troll | 12 | 31 | Official |
| Kul Tiran | 16 | 32 | Official |

The ten original playable WotLK race IDs are unchanged. Custom IDs are local
assignments, not claims to the corresponding modern WoW race IDs. Extraction
directory names and `source` IDs remain unchanged; `target` is the final client
ID. The generated `available-races.md` and `race-mapping.json` reflect these
final assignments.

Goblin, Fel Orc, Naga, Broken, Forest Troll, and Ice Troll use
`replace_non_playable: true` to update the existing NPC race at its native ID
instead of relocating it into an artificial duplicate race. Playable race IDs
cannot be replaced this way. Existing display/model records are retained, but
NPC appearance may change; the merge report lists these replacements. Vrykul
keeps its native ID 16.

Regenerate the MPQ after this renumbering. Any server configuration, race masks
or existing characters using the previous client IDs need a coordinated
migration; this script does not migrate server databases or saved characters.

### Murlocs and Ogres

Murlocs have their own Alliance icon (client ID 24), and Ogres their own Horde
icon (client ID 27). Both use the same nine allowed classes as the other
standalone imported races, with Human and Orc starting-outfit donors respectively.
The generated race summary includes both, bringing the grid to nine visible
portraits per faction.
When the original portrait atlas is full, the merge writes a wider
`*-Merged.blp` atlas and adjusts the creation screen's texture coordinates.
Portrait cells keep their original resolution; the original atlas remains
unchanged for other screens.

Ogres use the two original models from `03-Races/53-Ogre`, not the separate
HD extraction numbered 85. `swap_model_sexes: true` assigns the source female
two-headed `OgreMagePC` to the male choice, and the source male one-headed
`OgrePC` to the female choice. Their customization rows, facial-hair labels,
display-extra sex values and extracted portraits follow the swap. Race IDs,
classes and starting-outfit genders do not. Original model and texture files
are copied unchanged.

If the Murloc extraction predates the dedicated PNG portraits in `Icons`,
refresh it before merging:

```powershell
python extract_races.py --portraits-only --only 30
```

### Dwarf and Tauren alternatives

Dark Iron Dwarf is selected under Dwarf (Alliance), and Highmountain Tauren under
Tauren (Horde), without extra race icons. Both use their extracted HD male and
female models, original textures and matching customization tables; no tinting
or LD donor is used. Their allowed classes and starting-outfit donors match the
base Dwarf and Tauren races respectively, including Death Knight.

Highmountain takes official client ID 28; Drakkari moves from 28 to custom ID 26.
Dark Iron uses custom ID 30 because its official ID 34 exceeds the 32-ID limit.
Regenerate the patch and update any server data that used ID 28 for Drakkari.
The source extraction folders stay numbered 48 and 66. Final rendering needs
an in-game check.

### HD Orc appearances

Orc, Mag'har, and Fel Orc deliberately share the inherited Orc HD models and
animations, including the upright male posture. These are three appearances,
not three different body meshes; Fel Orc does not retain its old protrusions.
Both variants use `appearance.base_race: 2`, with `appearance.skin_tone` set to
`"brown"` for Mag'har or `"red"` for Fel Orc. They inherit the same HD
customization tables, including the companion eye/ear atlases, instead of mixing
the source pack's unrelated models and textures. Skin, face, and underwear are
tinted consistently; non-green details are preserved. Hair and scalp hair
overlays remain shared and unchanged. Generated textures live under
`Variants/Orc/<tone>/`, leaving the
original Orc files untouched. Their older imported models/textures, including
the LD Fel Orc, are no longer installed. A missing required HD texture stops the
merge explicitly. Regenerate the patch; final rendering still needs an in-game
check. Skin textures in the current HD base are opaque; unsupported transparent
skin textures stop generation rather than silently losing their alpha channel.

Generated Orc and Troll skin textures retain the original BLP2 paletted format.
Their mip chains run all the way to 1x1, including for companion atlases sampled
directly on ears, tusks, claws and accessories. The top-level palette indices are
written directly, avoiding a second quantization that previously merged nearby
colors and introduced extra pixel noise. Source artwork can still show its
original 256-color palette limits. Regenerate the patch to replace older
textures with incomplete mip chains.

### HD Troll appearances

Forest Troll (ID 18) and Ice Troll (ID 21) use the existing Drakkari HD male and
female models instead of their LD source models. Drakkari (ID 26), the base
Troll, and Zandalari are not changed. The three variants share the Drakkari
morphology; Forest uses green skin and Ice uses pale blue skin.

Their `appearance.source_race: 28` selects the extracted Drakkari models,
animations, textures and matching customization tables, independently of import
order. Unlike `base_race`, this donor is read from `03-Races`, not the HD base.
Specify exactly one of `source_race` or `base_race`. `skin_tone` is `"forest"` or
`"ice"` for this donor. `skin_colors: [0, 1, 2, 3, 4, 8]` keeps its six blue/aqua
palettes suitable for tinting and excludes its three brown palettes; body, face
and underwear color indices are renumbered together without changing hair
colors. Generated textures live under `Variants/Troll/<tone>/`; Drakkari's
original files and hair are left untouched. Both variants now have actual HD
female models, so the selector also offers them when female is selected.
Regenerate the MPQ; final rendering still needs an in-game check.

Zandalari's previously reported geometry artifacts remain unresolved.

### Face zoom background

Each race may set `zoom_background` independently of its normal `background`.
Goblin uses `"background": "Orc"` and `"zoom_background": "Gnome"`: normal view
keeps the Orc setting, while face customization uses the Gnome close-up preset
for a shorter character. Other races keep their existing zoom unless configured.
This selects the entire zoom background model, including its camera and
lighting, not just a vertical offset. The corresponding
`Interface/Glues/Models/UI_GNOME_ZOOM/UI_GNOME_ZOOM.m2` and its dependencies must
be available in the installed client patches. Fine framing still needs an
in-game check. Re-run `merge_races.py` after changing the preset.

### Race portraits

`extract_races.py` reads portraits from the repository's `Icons` directory
(override with `--portraits-src <root>`). Install Pillow with
`python -m pip install Pillow` for extraction and atlas generation.

The supplied flat PNGs are used directly:
`Charactercreate-races_<RaceName>-male.png` and
`Charactercreate-races_<RaceName>-female.png`. Names are case-insensitive;
`<RaceName>` is the English race name without spaces or punctuation.
An unnumbered filename takes precedence; otherwise a unique numbered variant
is accepted, including the supplied Worgen `male2.png` / `female2.png`.
If no generic file exists, an `_<Faction>` suffix matching the extracted race's
faction is also supported. Multiple numbered candidates are rejected rather than
chosen arbitrarily. A shared model token never substitutes another race's PNG.
Both sexes must be present, nonempty, at least 128x128, and different; an invalid
pair stops extraction before either portrait is written.

The six configured races use the twelve supplied 130x130 PNGs from `Icons`.
They are reduced to 128x128 atlas cells, never enlarged. No files need to be
copied into Esteria-Interface, and no other source directory is implicitly read.

For an explicitly selected legacy Interface tree, dedicated HD pairs use:
`Interface/Glues/CharacterCreate/Portraits/<RaceName>/male.png` and `female.png`,
where `<RaceName>` is the English race name without spaces or punctuation
(case-insensitive, e.g. `HighElf`). Both files must exist, be nonempty,
at least 128x128, and contain different images. Invalid or incomplete HD pairs
stop extraction instead of silently falling back to an older icon.

Legacy Lua/atlas discovery requires `Interface/GlueXML`, `Interface/SharedXML`
and the referenced assets under `Interface/Icons` and
`Interface/Glues/CharacterCreate` in that explicit source tree. This discovery
does not fall back to another directory when the default `Icons` source is used.

Each extracted race contains `Portraits/male.png` and `Portraits/female.png`.
`race.json` records their relative paths and original assets under `portraits`;
atlas crops also record `tex_coords`. Sex-specific icons and atlas cells take
precedence over shared CoA icons. Coordinates are read from
`SharedXML/SharedConstants.lua`, then overridden by `GlueXML/CharacterCreate.lua`
if present. The standard atlas layout also covers the separate male/female
Goblin and Worgen cells. Without explicit coordinates, these two races use
`UI-CharacterCreate-Races.blp`, then `UI-CharacterCreate-RacesRound.blp` as a last
resort. The WotLK `UI-CharacterCreate-Races_Round.blp` has only ten races:
its tiny edge pixels in the next column must not be mistaken for portraits.
The supplied `RacesRound` atlas also duplicates the Goblin and Worgen male
artwork in its female cells; these duplicate female cells are rejected.
The square atlas has the correct separate portraits. The merge applies the destination's alpha mask
after extraction, so choosing the square source does not disable masking.

The Glue's explicit race-name mapping is respected for remaining shared icons.
When no sex-specific portrait is found, the shared CoA image is retained with
an explicit warning and `shared: true` in its metadata; this is **not** a
confirmed female portrait and cannot be merged as one. In particular, the
old High Elf and Broken CoA icons contain only male artwork; the dedicated HD
pairs described above replace them. No female artwork is invented.
A missing custom portrait is reported in
`portraits_missing`, never replaced by another race merely sharing its model.

To add or refresh portraits in existing extractions **without modifying their
DBC, models or textures**, run:

```shell
python extract_races.py --portraits-only
```

`--dst`, `--only` and `--exclude-standard` also apply to this mode. Normal
extraction includes portraits automatically.

`merge_races.py` reads portraits exclusively from the selected race folders in
`03-Races`, using `race.json`, including races with an HD `appearance` override.
It needs neither RaceGuide nor Esteria/Esteria-Interface during the merge.
Remove old per-race `icons` configuration entries: external paths are no longer
supported. Missing, invalid or empty portraits stop atlas generation and MPQ
packaging instead of silently substituting another race. The merge also rejects
shared female portraits, identical male/female images, and sources smaller than
their destination cell: increasing a 64x64 icon to 128x128 is not an HD portrait.

With `glue.round_icons` enabled, portraits use the alpha mask of an existing atlas
cell rather than an arbitrary circle. `icon_fallback` selects only the mask,
not substitute artwork. Check the generated PNG in `04-Merge/_manual` before
installing the rebuilt MPQ. No Esteria GlueXML/runtime files are installed.

### Race extraction and model isolation

The High Elf configuration uses `appearance.base_race: 10` to inherit the HD
Blood Elf appearance records (player displays, `CharSections`,
`CharHairGeosets`, and `CharacterFacialHairStyles`). `appearance.male_model` and
`appearance.female_model` select the existing HD `Character/HighElf` models and
their matching skins. Their original eye textures are blue despite the
`BloodElfFemaleEyeGlowGreen.blp` filename. `extract_races.py` copies these two
sex-specific textures under `Character/HighElf` in the High Elf extraction and
lists them in `race.json` as `appearance_textures`. The originals are stored in
[`Assets/Character/HighElf`](./Assets/Character/HighElf), independently of
`02-HD-Clean`; no `--fallback` is needed for these textures.
The merge installs only these two explicitly allowed overrides, checks that the
HD player models reference them, and keeps them in the final patch even if they
match the base. If the textures are absent from the HD base, the merge recreates
them in `04-Merge/patch-Z.mpq`, not in `02-HD-Clean`. Old extractions without them
must be regenerated.
Neither extraction nor merging changes the HD base or any `Character/BloodElf`
file. Death Knight textures are not changed. Both HighElf models, their matching
skins and animations must be present in the inherited HD patches.
The appearance is read from the original HD tables, before
race relocation or imports. Only `ChrRaces` display references, `ClientPrefix`
and the three hair-customization strings come from the HD appearance donor.
Flags, sounds, cinematic, expansion and other non-visual fields remain those of
the playable source race, with configuration overrides applied as usual.
In particular, the original HD Goblin has NPC flags `0x1`; importing its whole
`ChrRaces` row would hide the new Goblin instead of retaining the source's
playable flags `0xC`. Names, faction, classes and skills still follow the
race configuration/import. No Esteria appearance files are copied in this mode,
even with `overwrite_files: true`; only the extracted High Elf blue-eye overrides
are installed. The existing Blood Elf model/skin pairs remain
untouched. Missing HD models or skins stop the merge instead of substituting an
Esteria model. Without `appearance`, the existing source-import behavior applies.

Goblin uses `appearance.base_race: 9` for both sexes, retaining the HD models,
matching skins, textures and customization tables instead of the Esteria
overrides. This also preserves the transparent HD face layers rather than
replacing them with opaque older face textures. No texture upscaling is performed.
The original appearance remains available from the snapshot even when race 9
is relocated before the new Goblin is imported.

`extract_races.py` follows the male/female display IDs in `ChrRaces.dbc` to
`CreatureDisplayInfo.dbc`, then to the referenced models and display extras.
NPC displays are not selected merely because their `CreatureDisplayInfoExtra`
row shares the race ID. That reverse lookup can pull Night Elf or Worgen models
into an unrelated race folder.

For the Sirus Naga models, extraction normalizes permanent submeshes in the
referenced player `.skin` files from geoset ID `10000` to the standard visible
default `0`, only when no default `0` already exists. This addresses hidden
face/body geometry without replacing the Sirus models, changing texture alpha,
or removing customization geosets. The changes are recorded in `race.json`
under `skin_geoset_fixes`; the original source files are not modified.
Other races are not normalized. Confirm the resulting visibility in the client.

The Sirus Naga `CharSections` rows also fill unused texture slots with the opaque
`Character/Human/Male/HumanMaleSkin00_00.blp`. The 3.3.5 client composites it
(scalp textures are drawn over the face region), hiding the Naga face textures.
`extract_races.py` blanks those fields in the extracted DBC (count in `race.json`
under `placeholder_textures_cleared`).

High Elf irises are painted in the Blood Elf face textures, not only in the eye
glow. With `"eye_color": "blue"` in the race `appearance`, `merge_races.py`
writes blue copies of the greenish face textures under `Character/HighElf/` and
points only the High Elf `CharSections` rows to them. Blood Elf rows and files
are untouched. Requires Pillow.

`merge_races.py` also filters existing race folders: only files next to the player
models and textures explicitly referenced by the imported DBC rows or M2s are copied.
This keeps old, over-inclusive extractions from injecting unrelated models.
Regenerate old extractions with `extract_races.py` when the original source is
available. Missing models or companion files such as `.skin` still need to be
recovered from the matching source client; filtering does not reconstruct them.

### Pipeline checks before testing in the client

1. `clean_hd.py`: automatic priority is `base.mpq`, `patch.mpq`, numbered patches,
   then lettered patches. `--order` must include every source MPQ directory;
   omitted patches no longer silently override the explicit order. The entire
   `Character` directory is retained, including unreferenced M2s, skins, animations
   and textures. `--keywords` selects additional models outside `Character` by
   their paths in both the source files and `CreatureModelData`; a missing or
   incomplete DBC does not prevent discovering models on disk. Dependencies are
   read from the winning M2 after resolving patch priority. Alternate M2 versions
   (for example Cata version 272) are preserved without conversion or dependency
   parsing, with console warnings and entries in `report.json` under
   `unverified_models`. This does not certify their compatibility with 3.3.5.
2. `extract_races.py`: a missing player display, model row or referenced display
   extra stops extraction rather than producing dangling DBC references.
3. `merge_races.py`: source references must resolve before IDs are remapped.
   Incompatible DBC record sizes stop the merge. `max_race_id` cannot exceed 32,
   even when explicitly configured, because race masks are 32-bit.

All three stages use [race_assets.py](./race_assets.py) to read WotLK M2
dependencies: external skin profiles and embedded texture paths, including
textures outside the model folder. Invalid/truncated model headers or texture
arrays are rejected. Texture names end at their first NUL byte; trailing padding
within the declared string array is ignored. Missing dependencies appear in `report.json` (clean),
`race.json` (extract), or `merge-report.md` (merge). The merge report highlights
models and skins absent from both the inherited HD base and the differential
patch separately so they are not lost in long texture lists. Dependency checks
run before inherited files are excluded. A file found only in `asset_roots` is
not counted as installed; those roots are lookup sources, not guaranteed client
archives.
An exhausted icon atlas stops the merge rather than emitting missing Lua icon
coordinates.

Resource alerts search **all three pipeline sources**: extracted `01-HD/*.mpq`
layers, the configured HD `base`, and every race directory in `races_dir`,
including unselected races. Paths are matched case-insensitively relative to each
MPQ/race root. The effective HD-plus-patch result is also checked. Additional
sources such as Esteria do not suppress this three-stage absence alert.
Warnings give counts per selected race; `merge-report.md` contains the complete
lists, without the previous 200-entry limit. If a stage is inaccessible (or
`01-HD` has no extracted MPQ directories), the console and report explicitly mark
the check incomplete rather than certifying absence from all three sources.
Source availability and availability in the deployed HD-plus-patch remain
separate checks: finding a file in another extraction does not install it.

Extraction and merge still reject an unsupported M2 version when that file is
selected as a player model; the cleaner's broader collection is not a conversion.

These checks do not certify every animation or skin's binary compatibility.
Recover companion files from the **same model version**; vanilla skins are not
necessarily compatible with an HD replacement. A missing file in these reports
may still be provided by the target client's other MPQs: check the actual client
before concluding that an absent extracted file caused a crash.

Run the synthetic pipeline regressions with
`python -m unittest -v test_race_assets`. Original HD/Esteria sources are not
required for these tests. The legacy `patch_glue_reforged.py` is an obsolete
source-code rewriting helper, **not** a pipeline step; do not run it. Its UI
changes are already integrated into `merge_races.py`.

### [Visual Studio Community](https://visualstudio.microsoft.com/vs/community/) (Used)

### Binary to Decimal Converter
[Rapid Tables BtD Converter 1](https://www.rapidtables.com/convert/number/binary-to-decimal.html) (Used)

[es.convertbinary BtD Converter 2](https://www.rapidtables.com/convert/number/binary-to-decimal.html) (Optional)

### MPQ Editor

[Ladik's MPQ Editor](https://www.hiveworkshop.com/threads/ladiks-mpq-editor.249562/) (Used)

### DBC Editor (Used)

[WDBX Editor](https://github.com/WowDevTools/WDBXEditor) (Used)

[HexDBC Editor](https://github.com/Hextv/hexdbc/releases) (Optional)

[Rekt's WDBX Editor](https://github.com/rektbyfaith/WDBX-Editor--WoW-Modding/releases/tag/Release) (Optional)

### Blp Viewer (Optional)

[BlpV](https://github.com/Hextv/BlpV) (Optional)

[Blp View](https://www.wowinterface.com/downloads/info16700-BLPView.html) (Optional)

### PNG To BLP Converter (Optional)

[BLPtoPNG Online Converter](https://blp-convert.haaxor1689.dev/) (Optional)

[BLPNG Converter](https://www.wowinterface.com/downloads/info22128-BLPNGConverter.html) (Optional)

## The Tutorial

### Hello everyone,

I am bringing back the custom race implementation tutorial for your servers in version WotLK 3.3.5. To do this, it’s worth clarifying what we mean by "custom" in this tutorial:

- On one hand, we have the **Goblin race**, which we call custom, but it is actually already integrated into the official core, and we only need to configure it to unlock it.
  
- On the other hand, we have the **Worgen race**, which we will also call custom, but this one is not included in the core, and we will have to create lines before compiling to implement it.

With that said, let’s proceed with the tutorial. The first thing we are going to do, as I mentioned, is modify the core:

---

### MODIFICATION OF THE CORE

This is the first step we need to understand to start creating custom races. I assume you know how to download the TrinityCore git and pass it through CMake. If not, there are guides on the forum for that.

#### Modification of the "SharedDefines.h" file
- Open the "TrinityCore.sln" file with Visual Studio.
- In the Solution Explorer, search for "shared" and click on "SharedDefines.h". You will see the following:

```cpp
// Race value is index in ChrRaces.dbc
// EnumUtils: DESCRIBE THIS
enum Races
{
    RACE_NONE               = 0,  // SKIP
    RACE_HUMAN              = 1,  // TITLE Human
    RACE_ORC                = 2,  // TITLE Orc
    RACE_DWARF              = 3,  // TITLE Dwarf
    RACE_NIGHTELF           = 4,  // TITLE Night Elf
    RACE_UNDEAD_PLAYER      = 5,  // TITLE Undead
    RACE_TAUREN             = 6,  // TITLE Tauren
    RACE_GNOME              = 7,  // TITLE Gnome
    RACE_TROLL              = 8,  // TITLE Troll
    //RACE_GOBLIN           = 9,
    RACE_BLOODELF           = 10, // TITLE Blood Elf
    RACE_DRAENEI            = 11, // TITLE Draenei
    //RACE_FEL_ORC            = 12,
    //RACE_NAGA               = 13,
    //RACE_BROKEN             = 14,
    //RACE_SKELETON           = 15,
    //RACE_VRYKUL             = 16,
    //RACE_TUSKARR            = 17,
    //RACE_FOREST_TROLL       = 18,
    //RACE_TAUNKA             = 19,
    //RACE_NORTHREND_SKELETON = 20,
    //RACE_ICE_TROLL          = 21,
};
```

This is the section where we declare the IDs of the races we are going to use. If you look closely, we have the Goblin, but not the Worgen. To enable the races we want, we will do the following:

```cpp
// Race value is index in ChrRaces.dbc
// EnumUtils: DESCRIBE THIS
enum Races
{
    RACE_NONE               = 0,  // SKIP
    RACE_HUMAN              = 1,  // TITLE Human
    RACE_ORC                = 2,  // TITLE Orc
    RACE_DWARF              = 3,  // TITLE Dwarf
    RACE_NIGHTELF           = 4,  // TITLE Night Elf
    RACE_UNDEAD_PLAYER      = 5,  // TITLE Undead
    RACE_TAUREN             = 6,  // TITLE Tauren
    RACE_GNOME              = 7,  // TITLE Gnome
    RACE_TROLL              = 8,  // TITLE Troll
    //RACE_GOBLINOLD          = 9,
    RACE_BLOODELF           = 10, // TITLE Blood Elf
    RACE_DRAENEI            = 11, // TITLE Draenei
    //RACE_FEL_ORC            = 12,
    //RACE_NAGA               = 13,
    //RACE_BROKEN             = 14,
    //RACE_SKELETON           = 15,
    //RACE_VRYKUL             = 16,
    //RACE_TUSKARR            = 17,
    //RACE_FOREST_TROLL       = 18,
    //RACE_TAUNKA             = 19,
    //RACE_NORTHREND_SKELETON = 20,
    //RACE_ICE_TROLL          = 21,
    RACE_GOBLIN             = 23,
    RACE_WORGEN             = 24
};
```

Note that the Goblins, which were already declared but not accessible or playable, have been renamed to declare the new Goblin with ID 23. Personally, I don’t like leaving open roots declared in high IDs because it can cause errors when assigning languages, racials, and other things. That’s why I replace the ID of one race with another, like this:

```cpp
// Race value is index in ChrRaces.dbc
// EnumUtils: DESCRIBE THIS
enum Races
{
    RACE_NONE               = 0,  // SKIP
    RACE_HUMAN              = 1,  // TITLE Human
    RACE_ORC                = 2,  // TITLE Orc
    RACE_DWARF              = 3,  // TITLE Dwarf
    RACE_NIGHTELF           = 4,  // TITLE Night Elf
    RACE_UNDEAD_PLAYER      = 5,  // TITLE Undead
    RACE_TAUREN             = 6,  // TITLE Tauren
    RACE_GNOME              = 7,  // TITLE Gnome
    RACE_TROLL              = 8,  // TITLE Troll
    //RACE_GOBLINOLD          = 23,
    RACE_BLOODELF           = 10, // TITLE Blood Elf
    RACE_DRAENEI            = 11, // TITLE Draenei
    //RACE_FEL_ORC            = 24,
    //RACE_NAGA               = 13,
    //RACE_BROKEN             = 14,
    //RACE_SKELETON           = 15,
    //RACE_VRYKUL             = 16,
    //RACE_TUSKARR            = 17,
    //RACE_FOREST_TROLL       = 18,
    //RACE_TAUNKA             = 19,
    //RACE_NORTHREND_SKELETON = 20,
    //RACE_ICE_TROLL          = 21,
    RACE_GOBLIN             = 9,
    RACE_WORGEN             = 12
};
```

I have replaced `GOBLINOLD` with `GOBLIN` and `FEL_ORC` with `WORGEN`.

- Now let’s declare the maximum value of races. We must always assign the value of the highest open race ID and add 1:

This is what we have:

```cpp
// max+1 for player race
#define MAX_RACES         12
```

And this is what we will put, considering the above. The ID of the highest open race (we have Worgen = 12) and we add 1 (Worgen + 1 = 13):

```cpp
// max+1 for player race
#define MAX_RACES         13
```

- Now let’s define which races will be playable. To do this, we will see the following:

```cpp
#define RACEMASK_ALL_PLAYABLE \
    ((1<<(RACE_HUMAN-1)) | (1<<(RACE_ORC-1)) | (1<<(RACE_DWARF-1)) |\
     (1<<(RACE_NIGHTELF-1)) | (1<<(RACE_UNDEAD_PLAYER-1)) | (1<<(RACE_TAUREN-1)) |\
     (1<<(RACE_GNOME-1)) | (1<<(RACE_TROLL-1)) | (1<<(RACE_BLOODELF-1))|\
     (1<<(RACE_DRAENEI-1)))
```

To define them, we will do the following, taking the rule that every 3 roots we mark the end of the line with `\`, otherwise it will give you an error when compiling. So we put it this way:

```cpp
#define RACEMASK_ALL_PLAYABLE \
    ((1<<(RACE_HUMAN-1)) | (1<<(RACE_ORC-1)) | (1<<(RACE_DWARF-1)) |\
     (1<<(RACE_NIGHTELF-1)) | (1<<(RACE_UNDEAD_PLAYER-1)) | (1<<(RACE_TAUREN-1)) |\
     (1<<(RACE_GNOME-1)) | (1<<(RACE_TROLL-1)) | (1<<(RACE_WORGEN-1)) |\
     (1<<(RACE_BLOODELF-1)) | (1<<(RACE_DRAENEI-1)) | (1<<(RACE_GOBLIN-1)))
```

- The next thing is to define the faction, whether it’s Horde or Alliance. For this, we look for this:

```cpp
#define RACEMASK_ALLIANCE \
    ((1<<(RACE_HUMAN-1)) | (1<<(RACE_DWARF-1)) | (1<<(RACE_NIGHTELF-1)) | \
     (1<<(RACE_GNOME-1)) | (1<<(RACE_DRAENEI-1)))
```

And we declare the Worgen race for the Alliance, following the rule of the previous step (whatever you don’t declare there will be automatically assigned to the Horde):

```cpp
#define RACEMASK_ALLIANCE \
    ((1<<(RACE_HUMAN-1)) | (1<<(RACE_DWARF-1)) | (1<<(RACE_NIGHTELF-1)) | \
     (1<<(RACE_GNOME-1)) | (1<<(RACE_WORGEN-1)) | (1<<(RACE_DRAENEI-1)))
```

- With this, we will have finished configuring our precompile. Now we just need to mark the solution as Release and compile.

We will continue with part 2, where we will see the .dbc files that we need to configure.

---

### Part 2: Modifying DBC Files

In this second part, we are going to see which .dbc files we need to modify to make our races selectable.

#### Where do I get the DBCs from?

To get the correct .dbc files for our server, we need to go to our client and its official patches. We will always look for .dbc files in the patches with the greatest expansion to the least. That is, if I have "patch-3.MPQ" and "patch-2.MPQ", I extract from the major (patch-3.MPQ) and, if you can’t find it in that patch, go down: patch-2.MPQ ... patch.MPQ ...

Let me tell you that you will find almost all of them between the "patch-esES-3" and "patch-esES-2" patches (my client is Spanish).

Now, I will name the .dbc files that you should extract before starting:

- `ChrRaces.dbc`
- `CharBaseInfo.dbc`
- `CharStartOutfit.dbc`
- `SkillLineAbility.dbc`
- `SkillRaceClassInfo.dbc`
- `CreatureModelData.dbc`
- `CreatureDisplayInfo.dbc`
- `CreatureDisplayInfoExtra.dbc`
- `CharSections.dbc`
- `CharacterFacialHairStyles.dbc`
- `CharHairGeosets.dbc`

I will explain what you need to do in each .dbc file so that you understand it better.

---

### ChrRaces.dbc

In this .dbc, the races are defined as playable, the ID we assigned in the precompile, the faction, the display, etc. To understand it better, let’s visit `ChrRaces.dbc`.

We will take the Goblin and Fel_Orc lines and modify them like this:

```cpp
23,1,1,0x0,6894,6895,"Go",7,7,15007,0x448,"GoblinOld",0,0x2,"GoblinOld",,,,,,,,,,,,,,,,0xFF01FE,,,,,,,,,,,,,,,,,0xFF01EC,,,,,,,,,,,,,,,,,0xFF01EC,"NORMAL","NONE","NORMAL",0,
24,5,1,0x0,16981,16980,"Fo",7,7,15007,0x448,"FelOrc",0,0x2,"Fel Orc",,,,,,,,,,,,,,,,0xFF01FE,,,,,,,,,,,,,,,,,0xFF01EC,,,,,,,,,,,,,,,,,0xFF01EC,"NORMAL","NORMAL","NORMAL",0,
```

And we will add the custom races that we declared in part 1 of the tutorial:

```cpp
12,12,1,0x102C,40029,40030,"Ta",7,7,15007,0x448,"Worgen",81,0x0,"Worgen",,,,,,,,,,,,,,,,0xFF01FF,,,,,,,,,,,,,,,,,0xFF01EC,,,,,,,,,,,,,,,,,0xFF01EC,"NORMAL","HAIR","HORNS",0,
9,12,1,0x102D,40032,40033,"Go",1,7,15007,0x448,"Goblin",21,0x1,"Goblin",,,,,,,,,,,,,,,,0xFF01FF,,,,,,,,,,,,,,,,,0xFF01EC,,,,,,,,,,,,,,,,,0xFF01EC,"NORMAL","PIERCINGS","NORMAL",0,
```

---

### CharBaseInfo.dbc

This .dbc is responsible for relating race ID to class ID. We must add the custom races (in this case, we will only do the warrior) and assign them a class. So we do the following, we add this:

```cpp
9,1,
12,1,
```

---

### CharStartOutfit.dbc

This is where we declare the items that our custom races will use when we create them. What we have to do is add the following lines (remember that it is for warrior):

```cpp
380,9,1,0,0,38,39,40,0,49778,-1,-1,6948,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,9891,9892,10141,-1,2380,-1,-1,6418,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,7,8,-1,17,-1,-1,0,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
381,9,1,1,0,38,39,40,0,49778,-1,-1,6948,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,9891,9892,10141,-1,2380,-1,-1,6418,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,7,8,-1,17,-1,-1,0,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
382,12,1,0,0,6125,139,140,6948,49778,0,-1,0,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,9995,9988,9992,6418,22291,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,7,8,0,17,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
383,12,1,1,0,6125,139,140,6948,49778,0,-1,0,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,9995,9988,9992,6418,22291,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,7,8,0,17,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
```

---

### SkillLineAbility.dbc

This .dbc is responsible for assigning skills to characters. For example, to make them speak common language, orcish, etc. And that is what we are going to do with our new races, since without this, you will not be able to speak.

We are going to assign Skill 98, which is the common language, to Worgen. We are going to need a binary to decimal converter and vice versa. I use this website: [Binary to Decimal Converter](https://www.rapidtables.com/convert/number/binary-to-decimal.html).

We look for skill 98 (the skill IDs are in the second column) and we will see this:

```cpp
590,98,668,1101,0,,,1,0,0x2,0,0,,,
```

If we convert 1101 (which is what roots are allowed to use them) to binary with the converter, we will get `10001001101`. What does this mean? Take `1=ON`, `0=OFF` as a reference. And the order in which we have declared the races in part 1 of the tutorial according to their IDs. That is:

```
WORGEN | DRAENEI | BLOODELF | GOBLIN | TROLL | GNOME | TAUREN | UNDEAD_PLAYER | NIGHTELF | DWARF | ORC | HUMAN
```

So if we activate the common language for Alliance roots, including Worgen with ID 12, we will do the following:

```
1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 0 |
```

The binary number we get is `110001001101`. Now we convert it to decimal with the converter, and it would give us `3149`.

With which we change the fourth column of skill 98 as follows:

```cpp
590,98,668,3149,0,,,1,0,0x2,0,0,,,
```

This also applies to the issue of assigning mesh skills, 2-handed axes, etc. Just look for the skill ID in Wowhead and modify it as I told you above to allow them in the roots you want.

---

### SkillRaceClassInfo.dbc

In this table, the information is assigned to the skill for the roots and classes you want. I am only going to touch on the third column, which is related to roots, as in the previous .dbc. The fourth column is the one related to classes, but I will leave it by default.

We look for the following line of skill 98:

```cpp
40,98,1101,1535,0x80,0x0,0,0x0,
```

And to change it, we need to do the same before converting to binary and then to decimal. But we already know the value, remember that it gave us `3149`, so we change it as follows:

```cpp
40,98,3149,1535,0x80,0x0,0,0x0,
```

We do the same with this other line for the Goblin, we search:

```cpp
48,109,690,1535,0x80,0x0,0,0x0,
```

And we change the value of the roots (third column):

```cpp
48,109,946,1535,0x80,0x0,0,0x0,
```

With this, your PCs will be able to speak correctly. Just like when we change values in `SkillRaceAbility.dbc`, we must also change them in this .dbc.

When you have several lines in a skill, as you have verified with 98 and 109, look at the fifth column; the value `0x80` means available to learn.

You can better understand this .dbc at this link: [SkillRaceClassInfo.dbc](https://wowdev.wiki/DB/SkillRaceClassInfo).

---

### CreatureModelData.dbc

In this .dbc, we are going to assign the `.mdx` file of our race to both the male and female models for the races we are implementing. We do it by adding new lines:

```cpp
5005,2052,"Character\Worgen\Male\WorgenMale.mdx",1,1.0,1,7,18.0,12.0,1.0,,0,0,44,0.611100018024,2.03099989891,1.29404699802,-0.655966997147,-1.17623198032,0.000852000026498,0.702094972134,1.08035695553,2.29017710686,1.0,1.0,0.0,0.0,0.0,
5006,2052,"Character\Worgen\Female\WorgenFemale.mdx",1,1.0,1,7,18.0,12.0,1.0,,0,0,44,0.611100018024,2.03099989891,1.29404699802,-0.655966997147,-1.17623198032,0.000852000026498,0.702094972134,1.08035695553,2.29017710686,1.0,1.0,0.0,0.0,0.0,
5009,4,"Character\Goblin\Male\GoblinMale.mdx",1,1.0,1,1,12.0,10.0,1.0,,0,0,1128,0.555599987507,1.38900005817,0.460123002529,-0.452913999557,-0.579069972038,-0.0106370002031,0.470234006643,0.530076026917,1.39890694618,1.0,1.0,0.0,0.0,0.0,
5010,4,"Character\Goblin\Female\GoblinFemale.mdx",1,1.0,1,1,12.0,10.0,1.0,,0,0,1128,0.555599987507,1.38900005817,0.460123002529,-0.452913999557,-0.579069972038,-0.0106370002031,0.470234006643,0.530076026917,1.39890694618,1.0,1.0,0.0,0.0,0.0,
```

To know what each column is, visit: [CreatureModelData.dbc](https://wowdev.wiki/DB/CreatureModelData).

---

### CreatureDisplayInfo.dbc

In this .dbc, we are going to assign a DisplayID to our custom race model. To do this, we will put the following:

```cpp
40029,5005,0,25017,1.0,255,"","","","",3,0,0,0,0x0,0,
40030,5006,0,25018,1.0,255,"","","","",3,0,0,0,0x0,0,
40032,5009,0,25019,0.0,255,"","","","",0,0,0,0,0x0,0,
40033,5010,0,25020,0.0,255,"","","","",0,0,0,0,0x0,0,
```

Roughly speaking, this means that we created DisplayID 40029 for the CreatureModelData 5005 (WorgenMale) and with the CreatureDisplayInfoExtra 25017 that we will see now. We do that for each of the displays that we want to declare, which is why there are 4 lines, corresponding to the Male Worgen, Female Worgen, Male Goblin, and Female Goblin.

More information from the table at: [CreatureDisplayInfo.dbc](https://wowdev.wiki/DB/CreatureDisplayInfo).

---

### CreatureDisplayInfoExtra.dbc

In this .dbc, we are going to assign skins and other extras for the race. For this example, we will put the following in some new lines:

```cpp
25017,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,"CreatureDisplayExtra-21381.blp",
25018,12,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,"CreatureDisplayExtra-21381.blp",
25019,9,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,"CreatureDisplayExtra-21381.blp",
25020,9,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,"CreatureDisplayExtra-21381.blp",
```

---

### CharSections.dbc

In this .dbc, the paths to the `.blp` files for our custom races are established. It’s very easy; you just have to take the lines of a PC such as the Tauren, which is the one related to the placement of skins most similar to the Worgen. We paste them into a text editor like Notepad and rename the lines with high ID values and the path to the `.blp` we want to declare.

Here I leave you in a `.txt` the lines that you have to add to the .dbc: [DOWNLOAD](https://mega.nz/file/OExmyAgT#18nQxLxOSlSS9Ih1rbRnfgVbWPdO8UGlOPfHMCeMr34).

---

### CharacterFacialHairStyles.dbc

Here we will assign the values of the beards and facial hair for our races. In this case, the first thing would be to change the values that already come from the GoblinOld, remembering that by default it was ID=9, for the value ID=23, which is the one we gave it before, and that of the Fel_Orcs, which by default is 12, and we change it to 24. Once this is done, we add the following lines:

```cpp
12,0,0,0,0,0,0.0,2,
12,1,2,0,3,0,0.0,2,
12,1,3,0,4,0,0.0,2,
12,1,4,0,5,0,0.0,2,
12,1,5,0,6,0,0.0,2,
12,1,6,0,7,0,0.0,2,
12,1,7,0,8,0,0.0,2,
12,1,8,0,9,0,0.0,2,
12,1,9,0,10,0,0.0,2,
12,1,10,0,11,0,0.0,2,
12,0,1,2,0,0,0.0,2,
12,0,2,3,0,0,0.0,2,
12,0,3,4,0,0,0.0,2,
12,0,4,5,0,0,0.0,2,
12,0,5,6,0,0,0.0,2,
12,0,6,7,0,0,0.0,2,
12,0,7,8,0,0,0.0,2,
12,0,8,9,0,0,0.0,2,
12,0,9,10,0,0,0.0,2,
12,1,1,0,2,0,0.0,2,
9,1,0,6,11,2,0.0,0,
9,1,1,5,10,3,0.0,0,
9,1,2,2,9,4,0.0,0,
9,1,3,3,8,5,0.0,0,
9,1,4,2,7,6,0.0,0,
9,1,5,5,6,7,0.0,0,
9,1,6,4,5,8,0.0,0,
9,1,7,3,4,9,0.0,0,
9,1,8,2,3,10,0.0,0,
9,1,9,5,2,11,0.0,0,
9,1,10,4,11,12,0.0,0,
9,1,11,3,10,13,0.0,0,
9,0,0,6,11,2,0.0,0,
9,0,2,2,9,4,0.0,0,
9,0,3,3,8,5,0.0,0,
9,0,1,5,10,3,0.0,0,
9,0,8,2,3,10,0.0,0,
9,0,4,2,7,6,0.0,0,
9,0,5,5,6,7,0.0,0,
9,0,6,4,5,8,0.0,0,
9,0,7,3,4,9,0.0,0,
9,0,10,4,11,12,0.0,0,
9,0,9,5,2,11,0.0,0,
9,0,11,3,10,13,0.0,0,
9,0,13,6,8,3,0.0,0,
9,0,14,5,7,4,0.0,0,
9,0,18,6,3,8,0.0,0,
9,0,17,4,4,7,0.0,0,
9,0,16,3,5,6,0.0,0,
9,0,22,3,9,12,0.0,0,
9,0,24,2,7,13,0.0,0,
9,0,21,2,10,11,0.0,0,
9,0,19,5,2,9,0.0,0,
9,0,23,5,8,13,0.0,0,
9,0,20,4,11,10,0.0,0,
9,0,15,4,6,5,0.0,0,
9,0,12,5,9,2,0.0,0,
9,1,13,6,8,3,0.0,0,
9,1,12,5,9,2,0.0,0,
9,1,15,4,6,5,0.0,0,
9,1,14,5,7,4,0.0,0,
9,1,17,4,4,7,0.0,0,
9,1,16,3,5,6,0.0,0,
9,1,18,6,3,8,0.0,0,
9,1,23,5,8,13,0.0,0,
9,1,19,5,2,9,0.0,0,
```

More info about this .dbc at: [CharacterFacialHairStyles.dbc](https://wowdev.wiki/DB/CharacterFacialHairStyles).

---

### CharHairGeosets.dbc

Here we will establish the geosets for our custom races. As we did previously, first we will replace all values 9 with 23 in the second column and values 12 with 24. Then we will add the following lines:

```cpp
536,9,0,3,4,0,
537,9,0,4,5,0,
538,9,1,2,4,0,
539,9,1,3,5,0,
540,9,1,4,6,0,
541,9,1,5,7,0,
542,9,1,6,8,0,
543,9,1,7,9,0,
544,9,1,8,10,0,
545,9,1,9,11,0,
546,9,1,10,12,0,
547,9,1,11,13,0,
548,9,1,12,14,0,
549,9,1,13,15,0,
550,9,1,14,16,0,
551,9,1,15,17,0,
552,9,1,16,18,0,
553,9,0,5,6,0,
554,9,0,6,7,0,
555,9,0,7,8,0,
556,9,0,9,10,0,
557,9,0,10,11,0,
558,9,0,8,9,0,
559,9,0,11,12,0,
560,9,0,12,13,0,
561,9,0,13,14,0,
562,9,0,14,15,0,
563,9,0,15,16,0,
564,9,0,16,17,0,
565,9,0,17,18,0,
566,9,0,2,3,0,
500,12,1,0,2,0,
501,12,1,3,5,0,
502,12,1,4,6,0,
503,12,1,5,7,0,
504,12,1,6,8,0,
505,12,1,7,9,0,
506,12,0,1,2,0,
507,12,1,1,3,0,
508,12,1,2,4,0,
509,12,0,1,2,0,
510,12,0,0,3,0,
511,12,0,3,5,0,
512,12,0,4,6,0,
519,12,1,8,10,0,
520,12,1,9,11,0,
521,12,1,14,16,0,
522,12,1,11,13,0,
523,12,1,12,14,0,
524,12,1,13,15,0,
525,12,1,15,17,0,
526,12,1,16,18,0,
527,12,1,17,19,0,
528,12,1,18,20,0,
529,12,1,19,21,0,
535,12,1,14,16,0,
```

With this, we will have completed our .dbc files for the custom races that we want to open.

To download the `.blp` files that I have mentioned, you can download them from here: [DOWNLOAD BLPs](https://mega.nz/file/KZxGBRxR#8ykFNi9MpnZXhZBWHSglp0-zil7tC1BqGoSKTm714NU). In them, you can find the necessary `.blp` files for male and female Goblin and for male and female Worgen.

Finally, we put all the modified .dbc files in a patch (that’s why there are guides in the forum) and then we also copy them to the "dbc" folder of our release.

If you think we’re done... I’ll tell you no, we still have to configure the database using SQL, and I’ll explain that in part 3.

---

### Part 3: Modifying the Database

For the third part of the tutorial, we will see the data that we must enter into the database through our manager. I use SQLYog to do it, and it works without problems. I have seen the SQL commands that I have used in the guide Goblin in this direction.

Without further ado, we will proceed to modify our database as follows:

#### Declare the Birthplace of Our Custom Races

Since Gilneas is not built into my server, I have placed the Worgen in the starting zone of humans and the Goblin in the starting zone of orcs. To do this, we put the following:

```sql
INSERT INTO `playercreateinfo` (`race`, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation`) 
VALUES ('9', '1', '1', '14', '-618.518', '-4251.67', '38.718', '1');

INSERT INTO `playercreateinfo` (`race`, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation`) 
VALUES ('12', '1', '0', '12', '-8949.95', '-132.493', '83.5312', '0');
```

#### Copy the Stats of Another Race

For the Goblin, we copy the stats of the Orc:

```sql
SET @NEW_RACE = 9; -- ID of the new race
SET @NEW_CLASS = 1; -- ID of the class you want
SET @COPY_RACE = 2; -- ID of the race you are copying the stats from

DELETE FROM `player_levelstats` WHERE race = @NEW_RACE AND class = @NEW_CLASS;

INSERT INTO `player_levelstats` (`race`, `class`, `level`, `str`, `agi`, `sta`, `inte`, `spi`)
SELECT @NEW_RACE, @NEW_CLASS, `level`, `str`, `agi`, `sta`, `inte`, `spi` 
FROM `player_levelstats`
WHERE race = @COPY_RACE AND class = @NEW_CLASS;
```

And for Worgen, we copy the stats of Humans:

```sql
SET @NEW_RACE = 12; -- ID of the new race
SET @NEW_CLASS = 1; -- ID of the class you want
SET @COPY_RACE = 1; -- ID of the race you are copying the stats from

DELETE FROM `player_levelstats` WHERE race = @NEW_RACE AND class = @NEW_CLASS;

INSERT INTO `player_levelstats` (`race`, `class`, `level`, `str`, `agi`, `sta`, `inte`, `spi`)
SELECT @NEW_RACE, @NEW_CLASS, `level`, `str`, `agi`, `sta`, `inte`, `spi` 
FROM `player_levelstats`
WHERE race = @COPY_RACE AND class = @NEW_CLASS;
```

#### Add Creation Information to Our Race

For the Goblin, we copy from the Orc again:

```sql
SET @NEW_RACE = 9;
SET @NEW_CLASS = 1;
SET @COPY_RACE = 2;

DELETE FROM `playercreateinfo_action` WHERE race = @NEW_RACE AND class = @NEW_CLASS;

INSERT INTO `playercreateinfo_action` (`race`, `class`, `button`, `action`, `type`)
SELECT @NEW_RACE, @NEW_CLASS, `button`, `action`, `type` 
FROM `playercreateinfo_action`
WHERE race = @COPY_RACE AND class = @NEW_CLASS;
```

And for Human Worgen:

```sql
SET @NEW_RACE = 12;
SET @NEW_CLASS = 1;
SET @COPY_RACE = 1;

DELETE FROM `playercreateinfo_action` WHERE race = @NEW_RACE AND class = @NEW_CLASS;

INSERT INTO `playercreateinfo_action` (`race`, `class`, `button`, `action`, `type`)
SELECT @NEW_RACE, @NEW_CLASS, `button`, `action`, `type` 
FROM `playercreateinfo_action`
WHERE race = @COPY_RACE AND class = @NEW_CLASS;
```

#### Modify the `playercreateinfo_skills` Table

Finally, we will have to go to the `playercreateinfo_skills` table and replace (remember part 2 of the tutorial) the decimal value of the races that are allowed the skill. Before, if you remember, we put skill 98 on the entire Alliance and skill 109 on the entire Horde.

Then we will look for those skills (in column 3) and modify the value `1101` to `3149` in skill 98 again and the value `690` to `946` in skill 109.

With this, we will have finished configuring our database. We close SQLYog and move on to part 4 of the guide to modify the Client Interface so that the new races appear in the creation panel.

---

### Part 4: Modifying the Client Interface

This will be the last part of the guide. After this, you will have successfully implemented the Worgens and Goblins on your server. Well, really, if you have already done the other 3 parts of the tutorial, you already have them implemented, but you still cannot access them from your client. For that, what we are going to do is change the interface files that refer to this and modify them so that our custom races appear in the character creation panel.

We are going to need several files for this, which, as I already explained in part 2, we will take from the patches from largest to smallest. The files to extract from the original MPQs are the following:

- `CharacterCreate.lua`
- `CharacterCreate.xml`
- `GlueParent.lua`
- `GlueStrings.lua`

Once we have them, we start the modifications.

---

### CharacterCreate.lua

Here we will establish the maximum number of races available. We will change this line:

```lua
MAX_RACES = 10;
```

To this (adding 2 more races):

```lua
MAX_RACES = 12;
```

Now we will establish the position of the race icons in their corresponding boxes. We search:

```lua
RACE_ICON_TCOORDS = {
    ["HUMAN_MALE"]        = {0, 0.125, 0, 0.25},
    ["DWARF_MALE"]        = {0.125, 0.25, 0, 0.25},
    ["GNOME_MALE"]        = {0.25, 0.375, 0, 0.25},
    ["NIGHTELF_MALE"]    = {0.375, 0.5, 0, 0.25},

    ["TAUREN_MALE"]        = {0, 0.125, 0.25, 0.5},
    ["SCOURGE_MALE"]    = {0.125, 0.25, 0.25, 0.5},
    ["TROLL_MALE"]        = {0.25, 0.375, 0.25, 0.5},
    ["ORC_MALE"]        = {0.375, 0.5, 0.25, 0.5},

    ["HUMAN_FEMALE"]    = {0, 0.125, 0.5, 0.75},
    ["DWARF_FEMALE"]    = {0.125, 0.25, 0.5, 0.75},
    ["GNOME_FEMALE"]    = {0.25, 0.375, 0.5, 0.75},
    ["NIGHTELF_FEMALE"]    = {0.375, 0.5, 0.5, 0.75},

    ["TAUREN_FEMALE"]    = {0, 0.125, 0.75, 1.0},
    ["SCOURGE_FEMALE"]    = {0.125, 0.25, 0.75, 1.0},
    ["TROLL_FEMALE"]    = {0.25, 0.375, 0.75, 1.0},
    ["ORC_FEMALE"]        = {0.375, 0.5, 0.75, 1.0},

    ["BLOODELF_MALE"]    = {0.5, 0.625, 0.25, 0.5},
    ["BLOODELF_FEMALE"]    = {0.5, 0.625, 0.75, 1.0},

    ["DRAENEI_MALE"]    = {0.5, 0.625, 0, 0.25},
    ["DRAENEI_FEMALE"]    = {0.5, 0.625, 0.5, 0.75},
};
```

And we add below the Draenei the icons of our new races:

```lua
RACE_ICON_TCOORDS = {
    ["HUMAN_MALE"]        = {0, 0.125, 0, 0.25},
    ["DWARF_MALE"]        = {0.125, 0.25, 0, 0.25},
    ["GNOME_MALE"]        = {0.25, 0.375, 0, 0.25},
    ["NIGHTELF_MALE"]    = {0.375, 0.5, 0, 0.25},

    ["TAUREN_MALE"]        = {0, 0.125, 0.25, 0.5},
    ["SCOURGE_MALE"]    = {0.125, 0.25, 0.25, 0.5},
    ["TROLL_MALE"]        = {0.25, 0.375, 0.25, 0.5},
    ["ORC_MALE"]        = {0.375, 0.5, 0.25, 0.5},

    ["HUMAN_FEMALE"]    = {0, 0.125, 0.5, 0.75},
    ["DWARF_FEMALE"]    = {0.125, 0.25, 0.5, 0.75},
    ["GNOME_FEMALE"]    = {0.25, 0.375, 0.5, 0.75},
    ["NIGHTELF_FEMALE"]    = {0.375, 0.5, 0.5, 0.75},

    ["TAUREN_FEMALE"]    = {0, 0.125, 0.75, 1.0},
    ["SCOURGE_FEMALE"]    = {0.125, 0.25, 0.75, 1.0},
    ["TROLL_FEMALE"]    = {0.25, 0.375, 0.75, 1.0},
    ["ORC_FEMALE"]        = {0.375, 0.5, 0.75, 1.0},

    ["BLOODELF_MALE"]    = {0.5, 0.625, 0.25, 0.5},
    ["BLOODELF_FEMALE"]    = {0.5, 0.625, 0.75, 1.0},

    ["DRAENEI_MALE"]    = {0.5, 0.625, 0, 0.25},
    ["DRAENEI_FEMALE"]    = {0.5, 0.625, 0.5, 0.75},

    ["GOBLIN_MALE"]        = {0.625, 0.750, 0.25, 0.5},
    ["GOBLIN_FEMALE"]    = {0.625, 0.750, 0.75, 1.0},

    ["WORGEN_MALE"]        = {0.625, 0.750, 0, 0.25},
    ["WORGEN_FEMALE"]    = {0.625, 0.750, 0.5, 0.75},
};
```

---

### CharacterCreate.xml

Now we are going to configure the position of the icons in their respective buttons and positions. To do this, we have to look for the race buttons section in `CharacterCreate.xml`. It goes something like this:

```xml
<CheckButton name="CharacterCreateRaceButton1" inherits="CharacterCreateRaceButtonTemplate" id="1">
    <Anchors>
        <Anchor point="TOP" relativePoint="TOP" x="-50" y="-61"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton2" inherits="CharacterCreateRaceButtonTemplate" id="2">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton1" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton3" inherits="CharacterCreateRaceButtonTemplate" id="3">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton2" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton4" inherits="CharacterCreateRaceButtonTemplate" id="4">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton3" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton5" inherits="CharacterCreateRaceButtonTemplate" id="5">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton4" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton6" inherits="CharacterCreateRaceButtonTemplate" id="6">
    <Anchors>
        <Anchor point="TOP" relativePoint="TOP" x="50" y="-61"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton7" inherits="CharacterCreateRaceButtonTemplate" id="7">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton6" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton8" inherits="CharacterCreateRaceButtonTemplate" id="8">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton7" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton9" inherits="CharacterCreateRaceButtonTemplate" id="9">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton8" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton10" inherits="CharacterCreateRaceButtonTemplate" id="10">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton9" relativePoint="BOTTOMLEFT" x="0" y="-21"/>
    </Anchors>
</CheckButton>
```

And we will replace it like this:

```xml
<CheckButton name="CharacterCreateRaceButton1" inherits="CharacterCreateRaceButtonTemplate" id="1">
    <Anchors>
        <Anchor point="TOP" relativePoint="TOP" x="-50" y="-50"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton2" inherits="CharacterCreateRaceButtonTemplate" id="2">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton1" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton3" inherits="CharacterCreateRaceButtonTemplate" id="3">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton2" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton4" inherits="CharacterCreateRaceButtonTemplate" id="4">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton3" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton5" inherits="CharacterCreateRaceButtonTemplate" id="5">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton4" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton8" inherits="CharacterCreateRaceButtonTemplate" id="8">
    <Anchors>
        <Anchor point="TOP" relativePoint="TOP" x="50" y="-50"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton9" inherits="CharacterCreateRaceButtonTemplate" id="9">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton8" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton10" inherits="CharacterCreateRaceButtonTemplate" id="10">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton9" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton11" inherits="CharacterCreateRaceButtonTemplate" id="11">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton10" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton12" inherits="CharacterCreateRaceButtonTemplate" id="12">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton11" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton7" inherits="CharacterCreateRaceButtonTemplate" id="7">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton12" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
<CheckButton name="CharacterCreateRaceButton6" inherits="CharacterCreateRaceButtonTemplate" id="6">
    <Anchors>
        <Anchor point="TOPLEFT" relativeTo="CharacterCreateRaceButton5" relativePoint="BOTTOMLEFT" x="0" y="-10"/>
    </Anchors>
</CheckButton>
```

---

### GlueParent.lua

Here we will put the track corresponding to each class as follows:

We search:

```lua
GlueAmbienceTracks["CHARACTERSELECT"] = "GlueScreenIntro";
```

And just below we add:

```lua
GlueAmbienceTracks["WORGEN"] = "GlueScreenHuman";
GlueAmbienceTracks["GOBLIN"] = "GlueScreenOrcTroll";
```

In the next "racelights" section, we must add our races. We are looking for this:

```lua
CHARACTERSELECT =  {
    {1,     0,  0.00000,        0.00000,        -1.00000,   1.0,    0.15000,    0.15000,    0.15000,    1.0,    0.00000,    0.00000,    0.00000},
    {1,     0,  -0.74919,       0.35208,        -0.56103,   1.0,    0.00000,    0.00000,    0.00000,    1.0,    0.44706,    0.54510,    0.73725},
    {1,     0,  0.53162,        -0.84340,       0.07780,    1.0,    0.00000,    0.00000,    0.00000,    2.0,    0.55,       0.338625,   0.148825},
```

And below we add this:

```lua
GOBLIN = {   
    {1,     0,  0.00000,        0.00000,        -1.00000,   1.0,    0.15000,    0.15000,    0.15000,    1.0,    0.00000,    0.00000,    0.00000},
    {1,     0,  -0.74919,       0.35208,        -0.56103,   1.0,    0.00000,    0.00000,    0.00000,    1.0,    0.44706,    0.54510,    0.73725},
    {1,     0,  0.53162,        -0.84340,       0.07780,    1.0,    0.00000,    0.00000,    0.00000,    2.0,    0.55,       0.338625,   0.148825},
},
WORGEN = {   
    {1,     0,  0.00000,        0.00000,        -1.00000,   1.0,    0.15000,    0.15000,    0.15000,    1.0,    0.00000,    0.00000,    0.00000},
    {1,     0,  -0.74919,       0.35208,        -0.56103,   1.0,    0.00000,    0.00000,    0.00000,    1.0,    0.44706,    0.54510,    0.73725},
    {1,     0,  0.53162,        -0.84340,       0.07780,    1.0,    0.00000,    0.00000,    0.00000,    2.0,    0.55,       0.338625,   0.148825},
}
```

Finally, we search:

```lua
-- Function to set the background model for character select and create screens
function SetBackgroundModel(model, name)
    local nameupper = strupper(name);
    local path = "Interface\\Glues\\Models\\UI_"..name.."\\UI_"..name..".m2";
    if ( model == CharacterCreate ) then
        SetCharCustomizeBackground(path);
    else
        SetCharSelectBackground(path);
    end
    PlayGlueAmbience(GlueAmbienceTracks[nameupper], 4.0);
    SetLighting(model, nameupper)
end
```

And we replace it with this, which will give us the creation wallpaper for our custom races:

```lua
-- Function to set the background model for character select and create screens
function SetBackgroundModel(model, name)
    local nameupper = strupper(name);
        if (name == "Goblin" or name == "GOBLIN") then
            name = "Orc";
        end
        if (name == "Worgen" or name == "WORGEN") then
            name = "HUMAN";
        end
    local path = "Interface\\Glues\\Models\\UI_"..name.."\\UI_"..name..".m2";
    if ( model == CharacterCreate ) then
        SetCharCustomizeBackground(path);
    else
        SetCharSelectBackground(path);
    end
    PlayGlueAmbience(GlueAmbienceTracks[nameupper], 4.0);
    SetLighting(model, nameupper)
end
```

---

### GlueStrings.lua

This file is to define the information related to the characters. We are going to change several things: race information and skill information.

We are looking for this:

```lua
ABILITY_INFO_BLOODELF1 = "- Enchanting skill increased.";
```

And we add above that line this:

```lua
ABILITY_INFO_GOBLIN1 = "- Goblin skills, line 1";
ABILITY_INFO_GOBLIN2 = "- Goblin skills, line 2";
ABILITY_INFO_GOBLIN3 = "- Goblin skills, line 3";
ABILITY_INFO_GOBLIN4 = "- Goblin skills, line 4";
ABILITY_INFO_WORGEN1 = "- Worgen skills, line 1";
ABILITY_INFO_WORGEN2 = "- Worgen skills, line 2";
ABILITY_INFO_WORGEN3 = "- Worgen skills, line 3";
ABILITY_INFO_WORGEN4 = "- Worgen skills, line 4";
```

Now we look for this:

```lua
RACE_CHANGE_IN_PROGRESS = "Updating race...";
```

And then we add:

```lua
RACE_INFO_GOBLIN = "Information about Goblins.";
RACE_INFO_GOBLIN_FEMALE = "Information about female Goblins.";
RACE_INFO_WORGEN = "Information about Worgens.";
RACE_INFO_WORGEN_FEMALE = "Information about female Worgens.";
```

And we’re finally done!!

We would only have to download the following file: [DOWNLOAD](https://mega.nz/file/eQAwRLCJ#jYy5eVWR_ZFG0ftWtF25u6_MEzqIfm-hT1EvPAi51yk). This is saved in the "Interface/Glues/CharacterCreate" path within the patch. The same thing, the icons do not match the coordinates that we have put in the tutorial since I did this file long after doing this tutorial and it has many more icons of more races. For them to match, the Cataclysm client's BLP would have to be used.

The `.lua` files go inside the patch in the "Interface/GlueXML" path.


### Congratulations for your first custom Races!


# More Information
### Support

For support, you can check out these Discord Servers listed below:

https://discord.gg/zD58AbTD7J (WoW Modding Community)

https://discord.gg/FgmWNvnQed (Hex's Community)

or you can DM Hex_Tv#2545

### License

[Attribution-NonCommercial 4.0 International](https://creativecommons.org/licenses/by-nc/4.0/deed.en)

