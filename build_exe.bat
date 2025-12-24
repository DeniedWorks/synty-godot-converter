@echo off
REM Build Synty Converter as standalone .exe
REM Requires: pip install pyinstaller

echo ========================================
echo Building Synty Converter .exe
echo ========================================
echo.

REM Check if pyinstaller is installed
where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller not found. Installing...
    py -m pip install pyinstaller
)

REM Navigate to repo directory
cd /d "%~dp0"

REM Clean previous builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo Building with PyInstaller...
echo.

REM Build using spec file
pyinstaller SyntyConverter.spec --noconfirm

echo.
if exist "dist\SyntyConverter.exe" (
    echo ========================================
    echo BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Output: %~dp0dist\SyntyConverter.exe
    echo.
    echo You can distribute this single .exe file.
    echo Users will also need Blender installed for
    echo size normalization feature.
    echo.
) else (
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo Check the error messages above.
)

pause
