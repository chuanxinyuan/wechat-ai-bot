"""
Unified data directory for EXE and dev modes.
EXE mode: %APPDATA%/WeChatAIBot  
Dev mode: project directory
"""
import os
import sys


def get_data_dir():
    """Get the writable data directory.
    EXE: %APPDATA%/WeChatAIBot
    Dev: project root (directory containing data_dir.py)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller: use AppData
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(base, 'WeChatAIBot')
    else:
        # Dev: project directory
        data_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_log_path():
    """Get log file path."""
    return os.path.join(get_data_dir(), 'bot.log')
