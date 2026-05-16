@echo off
setlocal EnableDelayedExpansion
title The Electric Kool-Aid Background Remover

:: ============================================================
::  Paths
:: ============================================================
set "APP_DIR=%~dp0"
set "APP_SCRIPT=%APP_DIR%the-electric-kool-aid-background-remover.py"
set "EMBEDDED_DIR=%APP_DIR%_python"
set "EMBEDDED_PY=%EMBEDDED_DIR%\python.exe"
set "REPO=https://github.com/dragnim/The-Electric-Kool-Aid-Background-Remover"

goto :main

:: ============================================================
::  Header subroutine — call :print_header to print and return
:: ============================================================
:print_header
cls
echo.
echo   ================================================
echo     The Electric Kool-Aid Background Remover
echo     by Dragnim
echo     %REPO%
echo   ================================================
echo.
exit /b 0

:: ============================================================
::  Main entry point
:: ============================================================
:main
call :print_header

:: ============================================================
::  Check the app script is present
:: ============================================================
if not exist "%APP_SCRIPT%" (
    echo   ERROR: the-electric-kool-aid-background-remover.py not found.
    echo.
    echo   Both files must be in the same folder:
    echo     launch.bat
    echo     the-electric-kool-aid-background-remover.py
    echo.
    echo   Download a fresh copy from:
    echo     %REPO%
    echo.
    pause
    exit /b 1
)

:: ============================================================
::  Find Python — prefer embedded, then system
:: ============================================================

:: Check for our own embedded Python first
if exist "%EMBEDDED_PY%" (
    set "PYTHON=%EMBEDDED_PY%"
    goto :check_version
)

:: Check for system Python
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=py"
    goto :check_version
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=python"
    goto :check_version
)

:: No Python found at all
goto :no_python

:: ============================================================
::  Check Python version is 3.12+
:: ============================================================
:check_version
set "VER_TMP=%TEMP%\ekbr_pyver.txt"
%PYTHON% -c "import sys; print(sys.version_info.major * 100 + sys.version_info.minor)" > "%VER_TMP%" 2>nul
set /p PY_VER= < "%VER_TMP%"
del "%VER_TMP%" >nul 2>&1

if not defined PY_VER (
    echo   Could not determine Python version.
    goto :no_python
)

:: Strip any whitespace/CR from the version number
set "PY_VER=%PY_VER: =%"

if %PY_VER% LSS 312 (
    echo   Python found but this app needs version 3.12 or newer.
    echo   Your version is too old. Please choose an option:
    echo.
    goto :no_python
)

:: Python is good — get the friendly version string for display
%PYTHON% -c "import sys; print(sys.version.split()[0])" > "%VER_TMP%" 2>nul
set /p PY_DISPLAY= < "%VER_TMP%"
del "%VER_TMP%" >nul 2>&1

:: ============================================================
::  GPU setup — all logic handled by gpu_setup.py
:: ============================================================
echo   Checking installation...
"%PYTHON%" "%APP_DIR%gpu_setup.py" --from-launcher

:: ============================================================
::  Launch the app
:: ============================================================
:launch
echo.
echo   Python %PY_DISPLAY% found. Starting the app...
echo.
echo   To remove this app and everything it installed: run cleanup.bat
echo.

"%PYTHON%" "%APP_SCRIPT%"

if %errorlevel% neq 0 (
    echo.
    echo   The app exited with an error.
    echo.
    echo   For help visit:
    echo     %REPO%
    echo.
    pause
)
exit /b 0

:: ============================================================
::  No Python (or too old) — offer options
:: ============================================================
:no_python
echo   Python is not installed (or is older than 3.12).
echo   This app needs Python to run the AI.
echo.
echo   [1] Install Python here  (~30 MB, this folder only,
echo       nothing outside this folder will be changed)
echo.
echo   [2] I'll install it myself
echo       https://www.python.org/downloads/
echo       Then run launch.bat again.
echo.
echo   [3] Exit
echo.
set /p "CHOICE=Enter 1, 2 or 3: "

if "%CHOICE%"=="1" goto :install_embedded
if "%CHOICE%"=="2" goto :manual_install
if "%CHOICE%"=="3" exit /b 0

echo   Invalid choice. Please enter 1, 2 or 3.
timeout /t 2 >nul
goto :no_python

:: ============================================================
::  Manual install — just point them at python.org and exit
:: ============================================================
:manual_install
echo.
echo   Download Python 3.12 or newer from:
echo     https://www.python.org/downloads/
echo.
echo   During install, tick "Add Python to PATH".
echo   Then run launch.bat again.
echo.
pause
exit /b 0

:: ============================================================
::  Install embedded Python into _python\
:: ============================================================
:install_embedded
call :print_header
echo   About to download Python 3.12 from python.org.
echo   This is the official Python embeddable package — nothing else.
echo.
echo   Download size:    ~30 MB
echo   Install location: %EMBEDDED_DIR%\
echo   Effect on system: none — everything goes in the folder above.
echo.
set /p "CONFIRM=Continue? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo   Cancelled. Run launch.bat again when you are ready.
    pause
    exit /b 0
)

echo.
echo   Downloading Python...

:: Use PowerShell to download — available on all modern Windows
set "PY_ZIP=%TEMP%\python-embed.zip"
set "PY_URL=https://www.python.org/ftp/python/3.12.13/python-3.12.13-embed-amd64.zip"
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'" >nul 2>&1
if %errorlevel% neq 0 goto :download_error

echo   Extracting...
if not exist "%EMBEDDED_DIR%" mkdir "%EMBEDDED_DIR%"
powershell -NoProfile -Command "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%EMBEDDED_DIR%' -Force" >nul 2>&1
if %errorlevel% neq 0 goto :extract_error
del "%PY_ZIP%" >nul 2>&1

:: Enable pip and site-packages in the _pth file
echo   Configuring...
set "PTH_FILE=%EMBEDDED_DIR%\python312._pth"
if not exist "%PTH_FILE%" (
    echo   ERROR: Could not find python312._pth in the extracted package.
    goto :install_error
)

:: Write a new _pth that enables site-packages
(
    echo python312.zip
    echo .
    echo Lib\site-packages
    echo.
    echo import site
) > "%PTH_FILE%"

:: Download and run get-pip.py
echo   Installing pip...
set "GETPIP=%EMBEDDED_DIR%\get-pip.py"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GETPIP%'" >nul 2>&1
if %errorlevel% neq 0 goto :download_error

"%EMBEDDED_PY%" "%GETPIP%" --quiet
if %errorlevel% neq 0 goto :pip_error
del "%GETPIP%" >nul 2>&1

echo.
echo   Python installed successfully.
echo.

:: Now continue to first launch
set "PYTHON=%EMBEDDED_PY%"
"%EMBEDDED_PY%" -c "import sys; print(sys.version.split()[0])" > "%TEMP%\ekbr_pyver.txt" 2>nul
set /p PY_DISPLAY= < "%TEMP%\ekbr_pyver.txt"
del "%TEMP%\ekbr_pyver.txt" >nul 2>&1

call :print_header
echo   Python installed.
echo.

:: Run GPU setup (offers GPU torch if NVIDIA GPU detected)
"%PYTHON%" "%APP_DIR%gpu_setup.py" --from-launcher

echo   On first launch the app will download its AI libraries
echo   (PyTorch, rembg and others). They are free, open source,
echo   licensed for commercial use, and about 2.5 GB in total.
echo   This happens once. You will be asked to confirm first.
echo.
echo   Starting the app...
echo.
echo   To remove this app and everything it installed: run cleanup.bat
echo.

"%PYTHON%" "%APP_SCRIPT%"

if %errorlevel% neq 0 (
    echo.
    echo   The app exited with an error.
    echo   For help visit: %REPO%
    echo.
    pause
)
exit /b 0


:: ============================================================
::  Error handlers
:: ============================================================
:download_error
echo.
echo   Something went wrong: could not download the file.
echo   Check your internet connection and try again.
echo.
echo   For help visit:
echo     %REPO%
echo.
if exist "%PY_ZIP%" del "%PY_ZIP%" >nul 2>&1
pause
exit /b 1

:extract_error
echo.
echo   Something went wrong: could not extract the download.
echo.
echo   For help visit:
echo     %REPO%
echo.
pause
exit /b 1

:pip_error
echo.
echo   Something went wrong: could not install pip.
echo.
echo   For help visit:
echo     %REPO%
echo.
pause
exit /b 1

:install_error
echo.
echo   Something went wrong during Python setup.
echo.
echo   For help visit:
echo     %REPO%
echo.
pause
exit /b 1
