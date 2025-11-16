@echo off
:: =============================================================================
:: Simple Launch Script for Instrument Analyzer GUI
:: =============================================================================
:: 楽器解析GUIの簡単起動スクリプト（エラーメッセージなし）
:: =============================================================================

cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" .venv\Scripts\pythonw.exe instrument_analyzer_gui.pyw
) else (
    where pythonw >nul 2>nul
    if errorlevel 0 (
        start "" pythonw instrument_analyzer_gui.pyw
    ) else (
        start "" python instrument_analyzer_gui.pyw
    )
)