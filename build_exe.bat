@echo off
REM ============================================================================
REM Synty Shader Converter - Build Executable
REM ============================================================================
REM This script builds a standalone Windows executable for the Synty Converter GUI.
REM
REM Requirements:
REM   - Python 3.10+
REM   - pip (Python package manager)
REM
REM Output:
REM   - dist/SyntyConverter.exe
REM ============================================================================

setlocal enabledelayedexpansion

echo ============================================================================
echo Synty Shader Converter - Build Script
echo ============================================================================
echo.

REM Check for Python
echo [1/4] Checking for Python...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found in PATH.
    echo Please install Python 3.10+ and add it to your PATH.
    echo Download from: https://www.python.org/downloads/
    exit /b 1
)

REM Display Python version
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found: %PYTHON_VERSION%
echo.

REM Check for pip
echo [2/4] Checking for pip...
python -m pip --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip not found.
    echo Please ensure pip is installed with Python.
    exit /b 1
)
echo pip is available.
echo.

REM Install/upgrade requirements
echo [3/4] Installing dependencies...
echo Installing GUI requirements...
python -m pip install -r requirements-gui.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install GUI requirements.
    exit /b 1
)
echo GUI requirements installed.

echo Checking PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller --quiet
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to install PyInstaller.
        exit /b 1
    )
)
echo PyInstaller is ready.
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo.

REM Run PyInstaller
echo [4/4] Building executable...
echo This may take a few minutes...
echo.
python -m PyInstaller synty_converter.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo.
    echo ============================================================================
    echo BUILD FAILED
    echo ============================================================================
    echo Check the output above for error details.
    exit /b 1
)

echo.
echo ============================================================================
echo BUILD SUCCESSFUL
echo ============================================================================
echo.
echo Executable created: dist\SyntyConverter.exe
echo.

REM Check file size
if exist "dist\SyntyConverter.exe" (
    for %%A in ("dist\SyntyConverter.exe") do (
        set SIZE=%%~zA
        set /a SIZE_MB=!SIZE! / 1048576
        echo File size: !SIZE_MB! MB
    )
)
echo.

REM Offer to run
echo To run the converter:
echo   dist\SyntyConverter.exe
echo.

pause
