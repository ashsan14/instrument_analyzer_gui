@echo off
setlocal EnableDelayedExpansion

:: =============================================================================
:: Instrument Analyzer GUI Launch Script
:: =============================================================================
:: 楽器解析GUIを起動するためのバッチファイル
:: Python環境の自動検出と依存関係チェックを行います
:: =============================================================================

echo Starting Instrument Analyzer GUI...
echo.

:: 現在のディレクトリをスクリプトの場所に設定
cd /d "%~dp0"

:: 仮想環境の確認と有効化
set PYTHON_EXE=
set PYTHONW_EXE=
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
    set PYTHONW_EXE=.venv\Scripts\pythonw.exe
    echo Found virtual environment: .venv
    goto check_version
)

:: Python実行可能ファイルを検索（優先順位: python.exe, py.exe）
where python >nul 2>nul
if !errorlevel! equ 0 (
    set PYTHON_EXE=python
    set PYTHONW_EXE=pythonw
    echo Python found: python ^(system installation^)
    goto check_version
)

where py >nul 2>nul
if !errorlevel! equ 0 (
    set PYTHON_EXE=py
    set PYTHONW_EXE=py
    echo Python found: py ^(system installation^)
    goto check_version
)

echo ERROR: Python not found
echo Please install Python 3.8+ or create a virtual environment
pause
exit /b 1

:check_version
:: Pythonバージョン確認
echo Checking Python version...
%PYTHON_EXE% -c "import sys; print(f'Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>nul
if !errorlevel! neq 0 (
    echo ERROR: Failed to check Python version
    pause
    exit /b 1
)

:: 必要なパッケージの確認
echo Checking required packages...
set MISSING_PACKAGES=

%PYTHON_EXE% -c "import tkinter" >nul 2>nul
if !errorlevel! neq 0 (
    set MISSING_PACKAGES=!MISSING_PACKAGES! tkinter
)

%PYTHON_EXE% -c "import sounddevice" >nul 2>nul
if !errorlevel! neq 0 (
    set MISSING_PACKAGES=!MISSING_PACKAGES! sounddevice
)

%PYTHON_EXE% -c "import numpy" >nul 2>nul
if !errorlevel! neq 0 (
    set MISSING_PACKAGES=!MISSING_PACKAGES! numpy
)

%PYTHON_EXE% -c "import librosa" >nul 2>nul
if !errorlevel! neq 0 (
    set MISSING_PACKAGES=!MISSING_PACKAGES! librosa
)

if not "!MISSING_PACKAGES!"=="" (
    echo ERROR: Missing required packages:!MISSING_PACKAGES!
    echo.
    echo To install missing packages, run:
    echo %PYTHON_EXE% -m pip install!MISSING_PACKAGES!
    echo.
    pause
    exit /b 1
)

echo All required packages are available.
echo.

:: アプリケーションファイルの存在確認
if not exist "instrument_analyzer_gui.pyw" (
    echo ERROR: instrument_analyzer_gui.pyw not found
    echo Please ensure this batch file is in the same directory as the application
    pause
    exit /b 1
)

:: ログディレクトリ作成（存在しない場合）
if not exist "logs" mkdir logs
if not exist "test_results" mkdir test_results

::  アプリケーション起動
echo Launching Instrument Analyzer GUI...
echo.

:: pythonwを使用してGUIアプリケーションを起動（コンソールウィンドウを非表示）
if exist ".venv\Scripts\pythonw.exe" (
    start "" .venv\Scripts\pythonw.exe instrument_analyzer_gui.pyw
    echo ✓ GUI started successfully using virtual environment
    echo   Check taskbar or desktop for the application window.
    goto finish
)

where pythonw >nul 2>nul
if !errorlevel! equ 0 (
    start "" pythonw instrument_analyzer_gui.pyw
    echo ✓ GUI started successfully
    echo   Check taskbar or desktop for the application window.
    goto finish
)

:: pythonwが利用できない場合は通常のpythonで起動
echo Starting GUI with console window (pythonw not available)...
%PYTHON_EXE% instrument_analyzer_gui.pyw

:finish
echo.
echo GUI application started successfully!
echo If you encounter any issues, check the logs directory for error details.
echo.
echo Closing console in 3 seconds...
timeout /t 3 >nul
exit /b 0