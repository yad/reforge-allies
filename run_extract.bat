@echo off
setlocal
cd /d "%~dp0"

python execution_log.py
if errorlevel 1 exit /b 1
set "REFORGE_PIPELINE_LOGS=1"

rem ======================================================================
rem  Extraction + fusion : profil coa puis profil hd, l'un après l'autre.
rem
rem  Dossiers : laisser vide = valeurs par défaut du script (PROFILES).
rem  Sinon renseigner SANS guillemets (les espaces sont gérés).
rem
rem  Options supplémentaires du .bat (transmises aux deux appels) :
rem    run_extract.bat --force --copy --ignore patch-Z
rem  Exclusions : ignore-coa.txt / ignore-hd.txt (un motif par ligne).
rem ======================================================================

set "WORKERS=4"

rem --- profil coa ---
set "COA_SRC=C:\Jeux\Conquest of Azeroth\Data"
set "COA_PATCHS=D:\repo\reforge-allies\01-CoA-Patchs"
set "COA_OUT=D:\repo\reforge-allies\01-CoA"

rem --- profil hd ---
set "HD_SRC=C:\Jeux\World of Warcraft 3.3.5\Data"
set "HD_PATCHS=D:\repo\reforge-allies\01-HD-Patchs"
set "HD_OUT=D:\repo\reforge-allies\01-HD"

rem ----------------------------------------------------------------------
set "ARGS_COA="
if defined COA_SRC    set ARGS_COA=%ARGS_COA% --data-dir "%COA_SRC%"
if defined COA_PATCHS set ARGS_COA=%ARGS_COA% --patchs-dir "%COA_PATCHS%"
if defined COA_OUT    set ARGS_COA=%ARGS_COA% --out-dir "%COA_OUT%"

set "ARGS_HD="
if defined HD_SRC     set ARGS_HD=%ARGS_HD% --data-dir "%HD_SRC%"
if defined HD_PATCHS  set ARGS_HD=%ARGS_HD% --patchs-dir "%HD_PATCHS%"
if defined HD_OUT     set ARGS_HD=%ARGS_HD% --out-dir "%HD_OUT%"

python extract_mpq.py coa --workers %WORKERS%%ARGS_COA% %* --force
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
python extract_mpq.py hd --workers %WORKERS%%ARGS_HD% %* --force --ignore "patch-Z-*"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
python clean_hd.py
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
python extract_races.py
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
python merge_races.py
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
pushd "D:\repo\ezrothcore"
if errorlevel 1 exit /b %ERRORLEVEL%
call build_client_patches.bat
set "RESULT=%ERRORLEVEL%"
popd
if not "%RESULT%"=="0" exit /b %RESULT%

echo.
echo Termine.
pause
exit /b 0
