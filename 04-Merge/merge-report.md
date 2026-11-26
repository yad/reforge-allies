# Rapport de merge

## Races

| Race | Source Esteria | ID final | Faction | Token glue | Classes |
|---|---|---|---|---|---|
| High Elf | 14 | 23 | Alliance | HIGH_ELF | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Broken | 22 | 14 | Horde | BROKEN | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Goblin | 9 | 9 | Horde | GOBLIN | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Worgen | 13 | 22 | Alliance | WORGEN | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Pandaren | 20 | 25 | Alliance | PANDAREN | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Naga | 21 | 13 | Horde | NAGA_ | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Zandalari Troll | 12 | 31 | Horde | ZANDALARI_TROLL | [1, 3, 4, 5, 6, 7, 8] |
| Forest Troll | 24 | 18 | Horde | FOREST_TROLL | [1, 3, 4, 5, 6, 7, 8] |
| Ice Troll | 25 | 21 | Horde | ICE_TROLL | [1, 3, 4, 5, 6, 7, 8] |
| Drakkari Troll | 28 | 26 | Horde | DRAKKARI_TROLL | [1, 3, 4, 5, 6, 7, 8] |
| Fel Orc | 23 | 12 | Horde | FEL_ORC | [1, 3, 4, 6, 7, 9] |
| Mag'har Orc | 49 | 29 | Horde | MAGHAR_ORC | [1, 3, 4, 6, 7, 9] |
| Kul Tiran | 16 | 32 | Alliance | KUL_TIRAN | [1, 2, 4, 5, 6, 8, 9] |
| Dark Iron Dwarf | 48 | 30 | Alliance | DARK_IRON_DWARF | [1, 2, 3, 4, 5, 6] |
| Highmountain Tauren | 66 | 28 | Horde | HIGHMOUNTAIN_TAUREN | [1, 3, 6, 7, 11] |
| Murloc | 30 | 24 | Alliance | MURLOC | [1, 2, 3, 4, 5, 7, 8, 9, 11] |
| Ogre | 53 | 27 | Horde | OGRE | [1, 2, 3, 4, 5, 7, 8, 9, 11] |

## Races de base déplacées


## Races PNJ remplacées

Les modèles et displays sont conservés, mais l'apparence des PNJ utilisant ces anciennes définitions de race peut changer.
- ID 14 : Roué -> Broken
- ID 9 : Gobelin -> Goblin
- ID 13 : Naga -> Naga
- ID 18 : Troll des forêts -> Forest Troll
- ID 21 : Troll des glaces -> Ice Troll
- ID 12 : Gangr'orc -> Fel Orc

## Patch différentiel

- 13771 fichiers nouveaux ou modifiés conservés.
- 19125 fichiers identiques à la base HD exclus (1654.8 Mo).
- La base HD doit être installée et chargée avant ce patch.

## Modèles et skins absents de la base HD et du patch

Vérifiés avant exclusion des fichiers hérités. Un fichier présent uniquement dans asset_roots ne prouve pas sa disponibilité dans le client cible.

## Vérification des ressources

- 01-HD : sortie fusionnée de l'extraction, ou dossiers *.mpq extraits.
- 02-HD-Clean : base configurée `02-HD-Clean/patch-X.mpq`.
- 03-Races : tous les dossiers de races dans `03-Races`, sélectionnés ou non.
- Chemins comparés sans tenir compte de la casse ; ressources du résultat effectif également disponibles.

Les ressources listées ci-dessous sont absentes des trois sources et du résultat effectif.

## Journal

- **info** patch-X.mpq copié vers D:\repo\reforge-allies\04-Merge\patch-Z.mpq pour préparer le patch différentiel
- **warn** race PNJ 'Roué' (ID 14) remplacée par Broken ; les displays PNJ sont conservés mais leur apparence peut changer
- **warn** race PNJ 'Gobelin' (ID 9) remplacée par Goblin ; les displays PNJ sont conservés mais leur apparence peut changer
- **warn** race PNJ 'Naga' (ID 13) remplacée par Naga ; les displays PNJ sont conservés mais leur apparence peut changer
- **warn** race PNJ 'Troll des forêts' (ID 18) remplacée par Forest Troll ; les displays PNJ sont conservés mais leur apparence peut changer
- **warn** race PNJ 'Troll des glaces' (ID 21) remplacée par Ice Troll ; les displays PNJ sont conservés mais leur apparence peut changer
- **warn** race PNJ 'Gangr'orc' (ID 12) remplacée par Fel Orc ; les displays PNJ sont conservés mais leur apparence peut changer
- **info** High Elf: apparence de la race 10 dans D:\repo\reforge-allies\04-Merge\patch-Z.mpq ; modèles et personnalisations de la race source remplacés
- **info** High Elf: 645 textures de visage recolorées en bleu
- **info** High Elf: tenues de départ des classes [3, 7, 11] copiées d'une autre race de la même faction
- **warn** High Elf: ClientFileString 'BloodElf' en conflit, remplacement par HIGH_ELF
- **info** High Elf: 14 -> 23 (Alliance), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 1067, 'CharHairGeosets': 36, 'CharacterFacialHairStyles': 21, 'CharStartOutfit': 18}, 2 fichiers copiés (2 remplacés)
- **info** Broken: tenues de départ des classes [2, 5, 8, 11] copiées d'une autre race de la même faction
- **info** Broken: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Broken: 22 -> 14 (Horde), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 831, 'CharHairGeosets': 30, 'CharacterFacialHairStyles': 15, 'CharStartOutfit': 18}, 1100 fichiers copiés (129 remplacés)
- **info** Goblin: apparence de la race 9 dans D:\repo\reforge-allies\04-Merge\patch-Z.mpq ; modèles et personnalisations de la race source remplacés
- **info** Goblin: tenues de départ des classes [2, 5, 8, 11] copiées d'une autre race de la même faction
- **info** Goblin: 10 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Goblin: 9 -> 9 (Horde), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 1028, 'CharHairGeosets': 35, 'CharacterFacialHairStyles': 50, 'CharStartOutfit': 18, 'SkillLineAbility': 2, 'SkillRaceClassInfo': 0}, 0 fichiers copiés (0 remplacés)
- **info** Worgen: tenues de départ des classes [3, 7, 11] copiées d'une autre race de la même faction
- **info** Worgen: 8 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Worgen: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Worgen: 13 -> 22 (Alliance), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 741, 'CharHairGeosets': 28, 'CharacterFacialHairStyles': 36, 'CharStartOutfit': 18, 'SkillRaceClassInfo': 0}, 1095 fichiers copiés (1 remplacés)
- **info** Pandaren: tenues de départ des classes [3, 7, 11] copiées d'une autre race de la même faction
- **info** Pandaren: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Pandaren: 20 -> 25 (Alliance), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 1387, 'CharHairGeosets': 28, 'CharacterFacialHairStyles': 10, 'CharStartOutfit': 18}, 2325 fichiers copiés (0 remplacés)
- **info** Naga: tenues de départ des classes [2, 5, 8, 11] copiées d'une autre race de la même faction
- **info** Naga: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Naga: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Naga: 21 -> 13 (Horde), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 1315, 'CharHairGeosets': 10, 'CharacterFacialHairStyles': 336, 'CharStartOutfit': 18, 'SkillRaceClassInfo': 0}, 508 fichiers copiés (0 remplacés)
- **info** Zandalari Troll: tenues de départ des classes [5, 8] copiées d'une autre race de la même faction
- **info** Zandalari Troll: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Zandalari Troll: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Zandalari Troll: 12 -> 31 (Horde), classes [1, 3, 4, 5, 6, 7, 8], lignes {'CharSections': 2832, 'CharHairGeosets': 22, 'CharacterFacialHairStyles': 315, 'CharStartOutfit': 14, 'SkillLineAbility': 2, 'SkillRaceClassInfo': 0}, 799 fichiers copiés (0 remplacés)
- **info** Forest Troll: apparence de la race 28 dans D:\repo\reforge-allies\03-Races\28-Drakkari-Troll ; modèles et personnalisations de la race source remplacés
- **info** Forest Troll: 186 textures HD adaptées (forest)
- **info** Forest Troll: tenues de départ des classes [5, 8] copiées d'une autre race de la même faction
- **info** Forest Troll: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Forest Troll: 24 -> 18 (Horde), classes [1, 3, 4, 5, 6, 7, 8], lignes {'CharSections': 243, 'CharHairGeosets': 21, 'CharacterFacialHairStyles': 17, 'CharStartOutfit': 14, 'SkillRaceClassInfo': 0}, 613 fichiers copiés (0 remplacés)
- **info** Ice Troll: apparence de la race 28 dans D:\repo\reforge-allies\03-Races\28-Drakkari-Troll ; modèles et personnalisations de la race source remplacés
- **info** Ice Troll: 186 textures HD adaptées (ice)
- **info** Ice Troll: tenues de départ des classes [5, 8] copiées d'une autre race de la même faction
- **info** Ice Troll: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Ice Troll: 25 -> 21 (Horde), classes [1, 3, 4, 5, 6, 7, 8], lignes {'CharSections': 243, 'CharHairGeosets': 21, 'CharacterFacialHairStyles': 17, 'CharStartOutfit': 14, 'SkillRaceClassInfo': 0}, 613 fichiers copiés (613 remplacés)
- **info** Drakkari Troll: tenues de départ des classes [5, 8] copiées d'une autre race de la même faction
- **info** Drakkari Troll: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Drakkari Troll: 28 -> 26 (Horde), classes [1, 3, 4, 5, 6, 7, 8], lignes {'CharSections': 291, 'CharHairGeosets': 21, 'CharacterFacialHairStyles': 17, 'CharStartOutfit': 14, 'SkillRaceClassInfo': 0}, 613 fichiers copiés (613 remplacés)
- **info** Fel Orc: apparence de la race 2 dans D:\repo\reforge-allies\04-Merge\patch-Z.mpq ; modèles et personnalisations de la race source remplacés
- **info** Fel Orc: 764 textures HD adaptées (red)
- **info** Fel Orc: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Fel Orc: 23 -> 12 (Horde), classes [1, 3, 4, 6, 7, 9], lignes {'CharSections': 794, 'CharHairGeosets': 25, 'CharacterFacialHairStyles': 18, 'CharStartOutfit': 12, 'SkillRaceClassInfo': 0}, 0 fichiers copiés (0 remplacés)
- **info** Mag'har Orc: apparence de la race 2 dans D:\repo\reforge-allies\04-Merge\patch-Z.mpq ; modèles et personnalisations de la race source remplacés
- **info** Mag'har Orc: 764 textures HD adaptées (brown)
- **info** Mag'har Orc: 49 -> 29 (Horde), classes [1, 3, 4, 6, 7, 9], lignes {'CharSections': 794, 'CharHairGeosets': 25, 'CharacterFacialHairStyles': 18, 'CharStartOutfit': 12}, 0 fichiers copiés (0 remplacés)
- **info** Kul Tiran: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Kul Tiran: 16 -> 32 (Alliance), classes [1, 2, 4, 5, 6, 8, 9], lignes {'CharSections': 264, 'CharHairGeosets': 12, 'CharacterFacialHairStyles': 73, 'CharStartOutfit': 14, 'SkillRaceClassInfo': 0}, 702 fichiers copiés (0 remplacés)
- **info** Dark Iron Dwarf: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Dark Iron Dwarf: 48 -> 30 (Alliance), classes [1, 2, 3, 4, 5, 6], lignes {'CharSections': 874, 'CharHairGeosets': 19, 'CharacterFacialHairStyles': 15, 'CharStartOutfit': 12}, 511 fichiers copiés (0 remplacés)
- **info** Highmountain Tauren: 66 -> 28 (Horde), classes [1, 3, 6, 7, 11], lignes {'CharSections': 1408, 'CharHairGeosets': 2, 'CharacterFacialHairStyles': 2, 'CharStartOutfit': 10}, 2771 fichiers copiés (0 remplacés)
- **info** Murloc: tenues de départ des classes [3, 7, 11] copiées d'une autre race de la même faction
- **info** Murloc: 7 lignes SkillRaceClassInfo ignorées (absentes de la base, ex. sorts raciaux : voir Spell.dbc)
- **info** Murloc: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Murloc: 30 -> 24 (Alliance), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 75, 'CharHairGeosets': 5, 'CharacterFacialHairStyles': 30, 'CharStartOutfit': 18, 'SkillRaceClassInfo': 0}, 228 fichiers copiés (0 remplacés)
- **info** Ogre: tenues de départ des classes [2, 5, 8, 11] copiées d'une autre race de la même faction
- **info** Ogre: modèles, personnalisations et portraits masculin/féminin permutés
- **info** Ogre: 2 fichiers sans lien avec les displays joueur ignorés (ancienne extraction incluant des PNJ possible)
- **info** Ogre: 53 -> 27 (Horde), classes [1, 2, 3, 4, 5, 7, 8, 9, 11], lignes {'CharSections': 52, 'CharHairGeosets': 2, 'CharacterFacialHairStyles': 2, 'CharStartOutfit': 18}, 608 fichiers copiés (0 remplacés)
- **info** slots de la création de perso : Alliance [1, 3, 4, 7, 11, 22, 23, 24, 25, 30, 32] / Horde [2, 5, 6, 8, 9, 10, 12, 13, 14, 18, 21, 26, 27, 28, 29, 31] (MAX_RACES=27)
- **info** disposition réappliquée à l'exécution selon les tokens de GetAvailableRaces ; IDs de boutons conservés
- **info** ordre visuel des races : Alliance [1, 3, 4, 7, 11, 23, 22, 25, 24] / Horde [2, 5, 6, 8, 14, 10, 9, 27, 13]
- **info** boutons de races régénérés : 9 Alliance (gauche) / 9 Horde (droite), espacement -12
- **info** Broken: ui_broken_zoom créé (décor Tauren, caméra x0.5)
- **info** Goblin: ui_goblin_zoom créé (décor Troll, caméra x0.9)
- **info** Worgen: ui_worgen_zoom créé (décor Human, caméra x0.5)
- **info** Pandaren: ui_pandaren_zoom créé (décor Dwarf, caméra x0.5)
- **info** Naga: ui_naga__zoom créé (décor Troll, caméra x0.9)
- **info** Kul Tiran: ui_kul_tiran_zoom créé (décor Human, caméra x0.5)
- **info** atlas d'icônes de races : UI-CHARACTERCREATE-RACES_Round.blp
- **info** atlas de création agrandi : 1024x512 -> 2048x512 ; atlas d'origine conservé
- **info** icône HIGH_ELF_MALE <- 03-Races\14-High-Elf\Portraits\male.png
- **info** icône HIGH_ELF_FEMALE <- 03-Races\14-High-Elf\Portraits\female.png
- **info** icône BROKEN_MALE <- 03-Races\22-Broken\Portraits\male.png
- **info** icône BROKEN_FEMALE <- 03-Races\22-Broken\Portraits\female.png
- **info** icône GOBLIN_MALE <- 03-Races\09-Goblin\Portraits\male.png
- **info** icône GOBLIN_FEMALE <- 03-Races\09-Goblin\Portraits\female.png
- **info** icône WORGEN_MALE <- 03-Races\13-Worgen\Portraits\male.png
- **info** icône WORGEN_FEMALE <- 03-Races\13-Worgen\Portraits\female.png
- **info** icône PANDAREN_MALE <- 03-Races\20-Pandaren\Portraits\male.png
- **info** icône PANDAREN_FEMALE <- 03-Races\20-Pandaren\Portraits\female.png
- **info** icône NAGA__MALE <- 03-Races\21-Naga\Portraits\male.png
- **info** icône NAGA__FEMALE <- 03-Races\21-Naga\Portraits\female.png
- **info** icône MURLOC_MALE <- 03-Races\30-Murloc\Portraits\male.png
- **info** icône MURLOC_FEMALE <- 03-Races\30-Murloc\Portraits\female.png
- **info** icône OGRE_MALE <- 03-Races\53-Ogre\Portraits\female.png
- **info** icône OGRE_FEMALE <- 03-Races\53-Ogre\Portraits\male.png
- **info** atlas UI-CHARACTERCREATE-RACES_Round-Merged.blp réécrit en BLP2 ARGB non compressé ; PNG de contrôle : D:\repo\reforge-allies\04-Merge\_manual\UI-CHARACTERCREATE-RACES_Round-Merged.png
- **warn** Goblin: 7 ressources référencées absentes de 01-HD, 02-HD-Clean et 03-Races (liste complète dans le rapport)
- **warn** Worgen: 90 ressources référencées absentes de 01-HD, 02-HD-Clean et 03-Races (liste complète dans le rapport)
- **warn** Naga: 2 ressources référencées absentes de 01-HD, 02-HD-Clean et 03-Races (liste complète dans le rapport)
- **warn** Zandalari Troll: 7 ressources référencées absentes de 01-HD, 02-HD-Clean et 03-Races (liste complète dans le rapport)
- **info** patch différentiel : 13771 fichiers nouveaux/modifiés conservés ; 19125 fichiers hérités de la base HD exclus (1654.8 Mo)
- **info** MPQ créé : C:\Jeux\World of Warcraft 3.3.5\Data\patch-Z-WotLK-Allies.mpq (13771 fichiers, compression zlib)

## Fichiers introuvables : Goblin

7 ressources référencées introuvables.

- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_100.blp
- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_101.blp
- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_102.blp
- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_103.blp
- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_104.blp
- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_105.blp
- Character/Goblin/Male/GoblinMaleNakedPelvisSkin00_106.blp

## Fichiers introuvables : Worgen

90 ressources référencées introuvables.

- Character/Worgen/FacialLowerHair00_00.blp
- Character/Worgen/FacialLowerHair00_01.blp
- Character/Worgen/FacialLowerHair00_02.blp
- Character/Worgen/FacialLowerHair00_03.blp
- Character/Worgen/FacialLowerHair00_04.blp
- Character/Worgen/FacialLowerHair01_00.blp
- Character/Worgen/FacialLowerHair01_01.blp
- Character/Worgen/FacialLowerHair01_02.blp
- Character/Worgen/FacialLowerHair01_03.blp
- Character/Worgen/FacialLowerHair01_04.blp
- Character/Worgen/FacialLowerHair02_00.blp
- Character/Worgen/FacialLowerHair02_01.blp
- Character/Worgen/FacialLowerHair02_02.blp
- Character/Worgen/FacialLowerHair02_03.blp
- Character/Worgen/FacialLowerHair02_04.blp
- Character/Worgen/FacialLowerHair03_00.blp
- Character/Worgen/FacialLowerHair03_01.blp
- Character/Worgen/FacialLowerHair03_02.blp
- Character/Worgen/FacialLowerHair03_03.blp
- Character/Worgen/FacialLowerHair03_04.blp
- Character/Worgen/FacialLowerHair04_00.blp
- Character/Worgen/FacialLowerHair04_01.blp
- Character/Worgen/FacialLowerHair04_02.blp
- Character/Worgen/FacialLowerHair04_03.blp
- Character/Worgen/FacialLowerHair04_04.blp
- Character/Worgen/FacialLowerHair05_00.blp
- Character/Worgen/FacialLowerHair05_01.blp
- Character/Worgen/FacialLowerHair05_02.blp
- Character/Worgen/FacialLowerHair05_03.blp
- Character/Worgen/FacialLowerHair05_04.blp
- Character/Worgen/FacialLowerHair06_00.blp
- Character/Worgen/FacialLowerHair06_01.blp
- Character/Worgen/FacialLowerHair06_02.blp
- Character/Worgen/FacialLowerHair06_03.blp
- Character/Worgen/FacialLowerHair06_04.blp
- Character/Worgen/FacialLowerHair07_00.blp
- Character/Worgen/FacialLowerHair07_01.blp
- Character/Worgen/FacialLowerHair07_02.blp
- Character/Worgen/FacialLowerHair07_03.blp
- Character/Worgen/FacialLowerHair07_04.blp
- Character/Worgen/FacialLowerHair08_00.blp
- Character/Worgen/FacialLowerHair08_01.blp
- Character/Worgen/FacialLowerHair08_02.blp
- Character/Worgen/FacialLowerHair08_03.blp
- Character/Worgen/FacialLowerHair08_04.blp
- Character/Worgen/FacialUpperHair00_00.blp
- Character/Worgen/FacialUpperHair00_01.blp
- Character/Worgen/FacialUpperHair00_02.blp
- Character/Worgen/FacialUpperHair00_03.blp
- Character/Worgen/FacialUpperHair00_04.blp
- Character/Worgen/FacialUpperHair01_00.blp
- Character/Worgen/FacialUpperHair01_01.blp
- Character/Worgen/FacialUpperHair01_02.blp
- Character/Worgen/FacialUpperHair01_03.blp
- Character/Worgen/FacialUpperHair01_04.blp
- Character/Worgen/FacialUpperHair02_00.blp
- Character/Worgen/FacialUpperHair02_01.blp
- Character/Worgen/FacialUpperHair02_02.blp
- Character/Worgen/FacialUpperHair02_03.blp
- Character/Worgen/FacialUpperHair02_04.blp
- Character/Worgen/FacialUpperHair03_00.blp
- Character/Worgen/FacialUpperHair03_01.blp
- Character/Worgen/FacialUpperHair03_02.blp
- Character/Worgen/FacialUpperHair03_03.blp
- Character/Worgen/FacialUpperHair03_04.blp
- Character/Worgen/FacialUpperHair04_00.blp
- Character/Worgen/FacialUpperHair04_01.blp
- Character/Worgen/FacialUpperHair04_02.blp
- Character/Worgen/FacialUpperHair04_03.blp
- Character/Worgen/FacialUpperHair04_04.blp
- Character/Worgen/FacialUpperHair05_00.blp
- Character/Worgen/FacialUpperHair05_01.blp
- Character/Worgen/FacialUpperHair05_02.blp
- Character/Worgen/FacialUpperHair05_03.blp
- Character/Worgen/FacialUpperHair05_04.blp
- Character/Worgen/FacialUpperHair06_00.blp
- Character/Worgen/FacialUpperHair06_01.blp
- Character/Worgen/FacialUpperHair06_02.blp
- Character/Worgen/FacialUpperHair06_03.blp
- Character/Worgen/FacialUpperHair06_04.blp
- Character/Worgen/FacialUpperHair07_00.blp
- Character/Worgen/FacialUpperHair07_01.blp
- Character/Worgen/FacialUpperHair07_02.blp
- Character/Worgen/FacialUpperHair07_03.blp
- Character/Worgen/FacialUpperHair07_04.blp
- Character/Worgen/FacialUpperHair08_00.blp
- Character/Worgen/FacialUpperHair08_01.blp
- Character/Worgen/FacialUpperHair08_02.blp
- Character/Worgen/FacialUpperHair08_03.blp
- Character/Worgen/FacialUpperHair08_04.blp

## Fichiers introuvables : Naga

2 ressources référencées introuvables.

- custom/naga/sirus/female/DragonSkin1Green
- custom/naga/sirus/male/DragonSkin1Green

## Fichiers introuvables : Zandalari Troll

7 ressources référencées introuvables.

- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_00.blp
- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_01.blp
- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_02.blp
- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_03.blp
- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_04.blp
- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_05.blp
- character/zandalaritroll/male/zandalaritrollmalenakedtorsoskin00_06.blp
