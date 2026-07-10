"""
Token management integration for wechat-bot-desktop.
Connects src/ modules (db, token_manager, patched_bot) to the desktop app.
"""
import sys
import os

# --- Path resolution for dev and PyInstaller ---
if getattr(sys, 'frozen', False):
    _MEIPASS = sys._MEIPASS
else:
    _MEIPASS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, _MEIPASS)

from src.db import Database
from src.token_manager import TokenManager
from src.config import get_machine_id, generate_license_key
from src.patched_bot import set_token_manager, apply_patch
from data_dir import get_data_dir

_db = None
_token_manager = None

def _load_patch_api_key():
    """Load DeepSeek API key from config.json (no hardcoded key)."""
    try:
        from data_dir import get_data_dir
        import json, os
        cfg_path = os.path.join(get_data_dir(), 'config.json')
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            return cfg.get('open_ai_api_key', '')
    except:
        pass
    return ''

DEEPSEEK_API_KEY = _load_patch_api_key()
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"


def init_token_system(base_dir=None):
    """Initialize DB, TokenManager, create/get user, apply monkey patch."""
    global _db, _token_manager

    if base_dir is None:
        base_dir = get_data_dir()

    db_path = os.path.join(base_dir, 'wechat_bot.db')
    _db = Database(db_path)
    _token_manager = TokenManager(_db, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE)

    machine_id = get_machine_id()
    existing = _db.get_user(machine_id=machine_id)
    is_new = existing is None

    if is_new:
        license_key = generate_license_key()
    else:
        license_key = existing['license_key']

    user = _token_manager.initialize_user(machine_id, license_key)

    set_token_manager(_token_manager)
    apply_patch()

    return {
        'machine_id': machine_id,
        'license_key': license_key,
        'balance': user['token_balance'],
        'total_used': user['total_used'],
        'is_new': is_new,
    }


def get_token_status():
    if _token_manager is None:
        return {'balance': 0, 'total_used': 0, 'call_count': 0}
    return _token_manager.get_usage_info()


def add_user_tokens(amount):
    if _token_manager is None or _token_manager.current_user is None:
        return 0
    return _db.add_tokens(_token_manager.current_user['id'], amount)


def get_user_info():
    if _token_manager is None or _token_manager.current_user is None:
        return {'machine_id': '', 'license_key': ''}
    return {
        'machine_id': _token_manager.current_user['machine_id'],
        'license_key': _token_manager.current_user['license_key'],
    }


def get_app_dir():
    return get_data_dir()
