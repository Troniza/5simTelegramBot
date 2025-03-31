@echo off
chcp 65001
title Telegram Bot - 5sim Number Seller
color 0A

echo [%time%] Starting bot initialization...
echo.

:check_python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [%time%] ERROR: Python is not installed!
    echo Download from: https://www.python.org/downloads/
    pause
    exit
)
echo [%time%] Python check: OK

:check_requirements
echo [%time%] Checking required libraries...
python -c "import telebot" >nul 2>&1
if %errorlevel% neq 0 (
    echo [%time%] Installing required libraries...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [%time%] ERROR: Failed to install requirements!
        pause
        exit
    )
    echo [%time%] Libraries installed successfully
) else (
    echo [%time%] Required libraries already installed
)

:check_files
echo [%time%] Checking required files...
if not exist "bot.py" (
    echo [%time%] ERROR: bot.py not found!
    pause
    exit
)
if not exist "config.py" (
    echo [%time%] ERROR: config.py not found!
    pause
    exit
)
echo [%time%] File check: OK

:setup_database
echo [%time%] Setting up database...
python -c "from database import setup_databases; setup_databases()" >nul 2>&1
if %errorlevel% neq 0 (
    echo [%time%] WARNING: Database setup might have issues
) else (
    echo [%time%] Database setup: OK
)

:start_bot
cls
echo [%time%] Bot is starting...
echo.
echo ========================================
echo Bot Status:
echo ----------------------------------------
echo Press Ctrl+C to stop the bot
echo View logs below:
echo ========================================
echo.

:run_bot
python bot.py
set EXIT_CODE=%errorlevel%

if %EXIT_CODE% equ 0 (
    echo.
    echo [%time%] Bot stopped normally
    echo Press any key to exit...
    pause >nul
    exit
) else (
    echo.
    echo [%time%] ERROR: Bot crashed with code %EXIT_CODE%
    echo [%time%] Restarting in 5 seconds...
    timeout /t 5 /nobreak >nul
    echo [%time%] Restarting bot...
    goto run_bot
) 