"""Shared bot state between launcher and web admin."""
import threading

# The itchat module instance (set by launcher after login)
itchat_module = None
last_error = None
login_status = "not_started"  # not_started, scanning, logged_in, failed

# Thread-safe lock
_lock = threading.Lock()


def set_itchat(instance):
    """Called by launcher after itchat login."""
    global itchat_module, login_status
    with _lock:
        itchat_module = instance
        login_status = "logged_in"


def set_error(err):
    """Record last error."""
    global last_error
    with _lock:
        last_error = str(err)


def set_scanning():
    global login_status
    with _lock:
        login_status = "scanning"


def set_failed(err):
    global login_status, last_error
    with _lock:
        login_status = "failed"
        last_error = str(err)


def get_itchat():
    """Called by web_admin to get the shared itchat instance."""
    with _lock:
        return itchat_module


def is_logged_in():
    """Check if bot is logged in."""
    return get_itchat() is not None


def get_status():
    """Get full status for diagnostics."""
    with _lock:
        return {
            "logged_in": itchat_module is not None,
            "login_status": login_status,
            "last_error": last_error,
        }
