@echo off
echo ============================================
echo   WeChat AI Bot - DEBUG BUILD (with console)
echo ============================================
echo.

echo [1/3] Installing dependencies...
python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ pyinstaller flask requests Pillow qrcode[pil] itchat-uos openai==0.28.1
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [2/3] Building DEBUG EXE (console window visible)...
python -m PyInstaller --onefile ^
    --name "WeChatAIBot_debug" ^
    --add-data "../src/db.py;src" ^
    --add-data "../src/token_manager.py;src" ^
    --add-data "../src/config.py;src" ^
    --add-data "../src/patched_bot.py;src" ^
    --add-data "../src/__init__.py;src" ^
    --add-data "token_patch.py;." ^
    --add-data "web_admin.py;." ^
    --add-data "bot_state.py;." ^
    --add-data "data_dir.py;." ^
    --add-data "persona_engine.py;." ^
    --add-data "long_term_memory.py;." ^
    --add-data "skill_manager.py;." ^
    --add-data "personas.json;." ^
    --add-data "whitelist.json;." ^
    --add-data "skills;skills" ^
    --add-data "lib;lib" ^
    --add-data "templates;templates" ^
    --hidden-import "flask" ^
    --hidden-import "openai" ^
    --hidden-import "PIL" ^
    --hidden-import "qrcode" ^
    --hidden-import "lib.itchat" ^
    --hidden-import "lib.itchat.content" ^
    --hidden-import "tkinter" ^
    --hidden-import "json" ^
    --hidden-import "sqlite3" ^
    --hidden-import "requests" ^
    --hidden-import "data_dir" ^
    --hidden-import "token_patch" ^
    --hidden-import "web_admin" ^
    --hidden-import "bot_state" ^
    --hidden-import "persona_engine" ^
    --hidden-import "long_term_memory" ^
    --hidden-import "skill_manager" ^
    --hidden-import "patch_filter" ^
    launcher.py

if %errorlevel% neq 0 (
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo Output: dist\WeChatAIBot_debug.exe
echo.
echo NOTE: This debug version shows a console window.
echo Run it and check the console for error messages,
echo especially about QR code generation.
echo.
pause
