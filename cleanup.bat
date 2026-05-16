@echo off
setlocal EnableDelayedExpansion
title The Electric Kool-Aid Background Remover - Cleanup

set "APP_DIR=%~dp0"
set "EMBEDDED_DIR=%APP_DIR%_python"
set "REPO=https://github.com/dragnim/The-Electric-Kool-Aid-Background-Remover"

goto :main

:: ============================================================
::  Find Python helper
:: ============================================================
:find_python
set "PYTHON="
if exist "%EMBEDDED_DIR%\python.exe" (
    set "PYTHON=%EMBEDDED_DIR%\python.exe"
    exit /b 0
)
where py >nul 2>&1
if %errorlevel% equ 0 ( set "PYTHON=py" & exit /b 0 )
where python >nul 2>&1
if %errorlevel% equ 0 ( set "PYTHON=python" & exit /b 0 )
exit /b 1

:: ============================================================
::  Helper: show a folder path and its size (or "not present")
:: ============================================================
:show_folder
set "FPATH=%~1"
set "FNAME=%~2"
if exist "%FPATH%" (
    for /f "tokens=3" %%s in ('dir /s /-c "%FPATH%" 2^>nul ^| find "File(s)"') do set "FSIZE=%%s"
    echo         %FNAME%: %FPATH%
    if defined FSIZE (
        echo           ^(present - approx !FSIZE! bytes^)
    ) else (
        echo           ^(present^)
    )
) else (
    echo         %FNAME%: not installed
)
exit /b 0

:: ============================================================
::  Main
:: ============================================================
:main
cls
echo.
echo   ================================================
echo     The Electric Kool-Aid Background Remover
echo     by Dragnim
echo     %REPO%
echo   ================================================
echo.
echo   Here is everything this app put on your computer
echo   and how to remove it.
echo.

:: ============================================================
::  Section 1 — AI model weights
:: ============================================================
echo   [1] AI model weights  (300 MB - 1 GB each, downloaded on first use)
echo.
echo       You can remove models one at a time using the trash button
echo       next to each model inside the app.
echo.
echo       To remove all model weights at once, delete these folders:
echo.

set "U2NET=%USERPROFILE%\.u2net"
set "HF=%USERPROFILE%\.cache\huggingface\hub\models--PramaLLC--BEN2"
set "TB=%USERPROFILE%\.transparent-background"

call :show_folder "%U2NET%"       "BiRefNet models"
call :show_folder "%HF%"          "BEN2 model"
call :show_folder "%TB%"          "InSPyReNet model"

echo.

:: ============================================================
::  Section 2 — Python (only if we installed it)
:: ============================================================
echo   [2] Python and AI libraries  (~2.5 GB)
echo.
if exist "%EMBEDDED_DIR%" (
    echo       Python was installed by this app into:
    echo         %EMBEDDED_DIR%
    echo.
    echo       The AI libraries are installed inside that folder too.
    echo       Deleting the folder above removes Python and all libraries.
    echo       The app folder itself will still be present until you delete it.
) else (
    echo       Python was not installed by this app.
    echo       Your existing Python installation will not be touched.
    echo.
    echo       If you want to remove the AI libraries from your Python,
    echo       open a command prompt and run:
    echo         pip uninstall torch rembg opencv-python Pillow
)
echo.

:: ============================================================
::  Section 3 — The app itself
:: ============================================================
echo   [3] The app
echo.
echo       Delete this folder:
echo         %APP_DIR%
echo.

:: ============================================================
::  Section 4 — Switch between CPU and GPU PyTorch
:: ============================================================
echo   [4] Switch between CPU and GPU version of PyTorch
echo.

call :find_python
if not defined PYTHON (
    echo       Python not found - cannot switch versions.
    echo.
    goto :summary
)

:: Check current torch state using gpu_setup.py logic
set "SWITCH_PY=%TEMP%\ekbr_torchcheck.py"
(
    echo import sys
    echo try:
    echo     import torch
    echo     sys.exit^(0 if torch.version.cuda else 1^)
    echo except ImportError:
    echo     sys.exit^(2^)
) > "%SWITCH_PY%"
"%PYTHON%" "%SWITCH_PY%" >nul 2>&1
set "TORCH_CHECK=%errorlevel%"
del "%SWITCH_PY%" >nul 2>&1

if "%TORCH_CHECK%"=="0" (
    echo       Currently installed: GPU version
    echo.
    echo       [S] Switch to CPU version
    echo           Use this if your GPU is unavailable or causing problems.
    echo           Switching will uninstall the GPU version and install CPU.
    echo.
    echo       [N] No change
    echo.
    set /p "SWITCH_CHOICE=Enter S or N: "
    if /i "!SWITCH_CHOICE!"=="S" (
        "%PYTHON%" "%APP_DIR%gpu_setup.py" --from-launcher --force-cpu
    )
) else if "%TORCH_CHECK%"=="1" (
    echo       Currently installed: CPU version
    echo.
    echo       [S] Switch to GPU version
    echo           Offers GPU install if an NVIDIA GPU is detected.
    echo.
    echo       [N] No change
    echo.
    set /p "SWITCH_CHOICE=Enter S or N: "
    if /i "!SWITCH_CHOICE!"=="S" (
        "%PYTHON%" "%APP_DIR%gpu_setup.py" --from-launcher --force-offer
    )
) else (
    echo       PyTorch is not currently installed.
    echo       Run launch.bat to install it.
    echo.
)

:: ============================================================
::  Summary
:: ============================================================
:summary
echo.
echo   ------------------------------------------------
echo   Full removal = delete the three model folders
echo   above (if present) + this app folder.
echo   Nothing else was ever put on your computer.
echo   ------------------------------------------------
echo.
echo   For more details visit:
echo     %REPO%
echo.
pause
exit /b 0
