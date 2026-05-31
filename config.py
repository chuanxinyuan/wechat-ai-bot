"""
Runtime config for chatgpt-on-wechat bot framework.
Reads from config.json in the app directory.
"""
import json
import os
import sys
import threading

_lock = threading.Lock()
_config_data = {}
_config_path = None


def _get_config_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    global _config_data, _config_path
    with _lock:
        if _config_path is None:
            _config_path = os.path.join(_get_config_dir(), 'config.json')
        try:
            if os.path.exists(_config_path):
                with open(_config_path, 'r', encoding='utf-8') as f:
                    _config_data = json.load(f)
        except Exception:
            _config_data = {}


def conf():
    """Return the config dict (lazy-load on first call)."""
    global _config_data
    if not _config_data:
        load_config()
    return _config_data
