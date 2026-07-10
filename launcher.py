"""
WeChat AI Bot - Desktop Launcher
Tkinter GUI with token management, QR code login, and admin panel.
"""
import sys
import os
import json
import threading
import time
import webbrowser
import random
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from qrcode import QRCode

# --- Path resolution for dev and PyInstaller ---
if getattr(sys, 'frozen', False):
    _MEIPASS = sys._MEIPASS
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _MEIPASS = os.path.dirname(os.path.abspath(__file__))
    _APP_DIR = _MEIPASS

sys.path.insert(0, _MEIPASS)
sys.path.insert(0, os.path.dirname(_MEIPASS))

# --- First-run: copy bundled config files to data dir ---
def _first_run_init():
    data_dir = get_data_dir()
    bundled_files = ['personas.json', 'whitelist.json']
    bundled_dirs = ['skills']
    for fname in bundled_files:
        dest = os.path.join(data_dir, fname)
        if not os.path.exists(dest):
            src = os.path.join(_MEIPASS, fname)
            if not os.path.exists(src):
                src = os.path.join(os.path.dirname(_MEIPASS), fname)
            if os.path.exists(src):
                import shutil
                shutil.copy(src, dest)

    for dname in bundled_dirs:
        dest_dir = os.path.join(data_dir, dname)
        if not os.path.exists(dest_dir):
            src_dir = os.path.join(_MEIPASS, dname)
            if not os.path.exists(src_dir):
                src_dir = os.path.join(os.path.dirname(_MEIPASS), dname)
            if os.path.exists(src_dir):
                import shutil
                shutil.copytree(src_dir, dest_dir)

    # Clean old files from EXE directory (migrated to data dir)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        old_files = ['wechat_bot.db', 'config.json', 'bot.log',
                     'personas.json', 'whitelist.json', 'contact_facts.json']
        for fname in old_files:
            path = os.path.join(exe_dir, fname)
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
        old_dirs = ['qr_cache', 'data', '__pycache__']
        for dname in old_dirs:
            path = os.path.join(exe_dir, dname)
            if os.path.exists(path):
                try:
                    import shutil
                    shutil.rmtree(path, ignore_errors=True)
                except: pass

# No hardcoded API key — loaded from config.json only
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"

import openai
openai.api_base = DEEPSEEK_API_BASE

# Track if user has been notified about expired key
_key_expired_notified = False

from token_patch import (
    init_token_system, get_token_status, add_user_tokens,
    get_user_info, get_app_dir
)
import bot_state
import persona_engine
import skill_manager
from data_dir import get_data_dir, get_log_path

# Load saved API key from config.json (no hardcoded fallback)
def _load_api_key():
    cfg_path = os.path.join(get_data_dir(), 'config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            return saved.get('open_ai_api_key', '')
        except:
            pass
    return ''

openai.api_key = _load_api_key()

# --- Globals ---
_token_info = None
_logged_in = False
_itchat_instance = None
_scanning = False


def format_number(n):
    """Format number with commas: 1000000 -> '1,000,000'"""
    return f"{n:,}"


# ============================================================
# Flask Admin Server
# ============================================================

def start_admin_server(port=5001):
    """Start Flask admin server in a daemon thread."""
    from web_admin import app
    t = threading.Thread(target=lambda: app.run(
        host='127.0.0.1', port=port, debug=False, use_reloader=False
    ), daemon=True)
    t.start()
    return t


# ============================================================
# WeChat Bot via itchat
# ============================================================

def bot_thread_main(qr_dir, on_qr_ready, on_login_ok, on_logout_handler):
    """Run itchat login and message loop in background thread."""
    global _itchat_instance, _logged_in, _scanning

    os.environ["WECHAT_TYPE"] = "uos"

    sys.path.insert(0, _MEIPASS)
    from lib import itchat

    from itchat.content import TEXT
    _itchat_instance = itchat

    # Conversation memory: last 20 messages per contact
    from collections import OrderedDict
    conversation_history = OrderedDict()
    MAX_HISTORY = 20
    import long_term_memory

    @itchat.msg_register(TEXT)
    def _handle_text(msg):
        try:
            text = msg.get('Text', '')
            from_user = msg.get('FromUserName', '')
            if not text.strip():
                return

            # Get contact info for persona
            user_info = msg.get('User', {}) or {}
            contact_name = user_info.get('NickName', '') or ''
            remark = user_info.get('RemarkName', '') or ''
            display_name = remark or contact_name

            print(f"[Bot] Msg from '{display_name}' text='{text[:30]}'")

            # Check whitelist
            enabled = persona_engine.is_contact_enabled(display_name)
            print(f"[Bot] Whitelist check: {display_name} -> enabled={enabled}")
            if display_name and not enabled:
                print(f"[Bot] Skipping (not in whitelist)")
                return

            # Build persona prompt with long-term facts + skills
            system_prompt = persona_engine.get_persona_prompt(
                display_name, nick=contact_name, remark=remark
            )
            # Add global skills
            global_skills = skill_manager.get_global_skills_prompt()
            if global_skills:
                system_prompt += "\n" + global_skills
            # Add per-contact skills
            contact_skills = skill_manager.get_contact_skills_prompt(display_name)
            if contact_skills:
                system_prompt += "\n" + contact_skills
            # Add long-term facts
            facts_prompt = long_term_memory.build_facts_prompt(display_name)
            if facts_prompt:
                system_prompt += "\n" + facts_prompt
            print(f"[Bot] System prompt len={len(system_prompt)}")

            # Get conversation history for this contact
            if display_name not in conversation_history:
                conversation_history[display_name] = []
            history = conversation_history[display_name]

            # Build messages: system + history + current
            messages = [{'role': 'system', 'content': system_prompt}]
            messages.extend(history[-MAX_HISTORY:])
            messages.append({'role': 'user', 'content': text})

            response = openai.ChatCompletion.create(
                model='deepseek-chat',
                messages=messages,
            )
            reply_text = response.choices[0].message.content
            print(f"[Bot] Reply: {reply_text[:50]}")

            # Parse and store long-term facts from reply
            reply_text = long_term_memory.parse_and_store_facts(display_name, reply_text)

            # Save to history
            history.append({'role': 'user', 'content': text})
            history.append({'role': 'assistant', 'content': reply_text})
            # Trim history
            if len(history) > MAX_HISTORY * 2:
                conversation_history[display_name] = history[-(MAX_HISTORY * 2):]
            print(f"[Bot] History for '{display_name}': {len(history)//2} turns")

            # Human-like delay
            reply_len = len(reply_text)
            total_delay = random.uniform(2.0, 6.0) + reply_len * random.uniform(0.1, 0.3)
            print(f"[Bot] Delaying {total_delay:.1f}s")
            time.sleep(total_delay)

            if from_user:
                itchat.send(reply_text, toUserName=from_user)
                print(f"[Bot] Sent!")

            root.after(0, lambda: update_balance_display())
        except Exception as e:
            import traceback
            err_str = str(e)
            print(f"[Bot] ERROR: {err_str}")
            traceback.print_exc()

            # Detect insufficient balance and prompt user to update API key
            if 'Insufficient Balance' in err_str or 'insufficient' in err_str.lower():
                global _key_expired_notified
                if not _key_expired_notified:
                    _key_expired_notified = True
                    root.after(0, lambda: _prompt_new_api_key())

    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, 'QR.png')
    pkl_path = os.path.join(qr_dir, 'itchat.pkl')

    def qr_callback(uuid, status, qrcode):
        if status == "0" and qrcode:
            with open(qr_path, 'wb') as f:
                f.write(qrcode)
        print(f"[Bot] QR status={status}")

    _scanning = True
    bot_state.set_scanning()
    print("[Bot] Starting auto_login...")
    try:
        itchat.auto_login(
            hotReload=os.path.exists(pkl_path),
            qrCallback=qr_callback,
            loginCallback=lambda: print("[Bot] loginCallback"),
            statusStorageDir=pkl_path,
        )
    except Exception as e:
        print(f"[Bot] auto_login failed: {e}")
        import traceback
        traceback.print_exc()
        _scanning = False
        bot_state.set_failed(str(e))
        root.after(0, on_qr_ready, None)
        return

    _scanning = False
    _logged_in = True
    bot_state.set_itchat(itchat)
    print("[Bot] Login successful!")
    try:
        if remember_var.get():
            itchat.dump_login_status(pkl_path)
            print(f"[Bot] Session saved: {pkl_path}")
    except Exception as e:
        print(f"[Bot] save session warning: {e}")
    root.after(0, on_login_ok)

    try:
        itchat.run()
    except Exception:
        _logged_in = False
        root.after(0, logout)


def poll_qr_code(qr_dir):
    """Poll for QR code file and display it when ready."""
    qr_path = os.path.join(qr_dir, 'QR.png')
    if os.path.exists(qr_path) and os.path.getsize(qr_path) > 0:
        try:
            img = Image.open(qr_path)
            img = img.resize((280, 280), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            qr_label.config(image=photo)
            qr_label.image = photo
            qr_status_label.config(text='请使用微信扫描二维码登录（2分钟内有效）', foreground='#333')
        except Exception:
            pass

    if _scanning:
        root.after(1000, poll_qr_code, qr_dir)  # Keep polling


# ============================================================
# API Key Verification
# ============================================================

def verify_deepseek_key(api_key):
    """Test if the API key is valid with sufficient balance.
    Returns True if OK, False if insufficient balance or error."""
    import requests
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        data = {
            'model': 'deepseek-chat',
            'messages': [{'role': 'user', 'content': 'Hi'}],
            'max_tokens': 1
        }
        resp = requests.post(
            f'{DEEPSEEK_API_BASE}/chat/completions',
            headers=headers, json=data, timeout=10
        )
        if resp.status_code == 200:
            return True
        if resp.status_code == 402:
            print("[KeyCheck] DeepSeek API: Insufficient Balance")
            return False
        print(f"[KeyCheck] DeepSeek API: HTTP {resp.status_code}")
        return False
    except Exception as e:
        print(f"[KeyCheck] Connection error: {e}")
        return True  # Assume key OK, network issue


def show_api_key_dialog():
    """Show a Tkinter dialog asking user to input a new DeepSeek API key.
    Returns the new key string, or None if cancelled."""
    dialog = tk.Toplevel(root)
    dialog.title('Token 余额不足')
    dialog.geometry('500x320')
    dialog.resizable(False, False)
    dialog.configure(bg='#f5f5f5')
    dialog.transient(root)
    dialog.grab_set()

    root.update_idletasks()
    try:
        px = root.winfo_x() + (root.winfo_width() - 500) // 2
        py = root.winfo_y() + (root.winfo_height() - 320) // 2
        dialog.geometry(f'+{max(0,px)}+{max(0,py)}')
    except:
        pass

    header = tk.Frame(dialog, bg='#e74c3c', height=50)
    header.pack(fill='x')
    header.pack_propagate(False)
    tk.Label(header, text='⚠️ DeepSeek API Key 余额不足',
             font=('Microsoft YaHei', 13, 'bold'), fg='white', bg='#e74c3c').pack(expand=True)

    content = tk.Frame(dialog, bg='white')
    content.pack(fill='both', expand=True, padx=20, pady=16)

    msg = ('当前 DeepSeek API Key 余额已用完，\n'
           '机器人将无法回复消息。\n\n'
           '请输入一个新的 API Key 继续使用：')
    tk.Label(content, text=msg, font=('Microsoft YaHei', 10),
             fg='#555', bg='white', wraplength=440, justify='left').pack(anchor='w')

    tk.Label(content, text='DeepSeek API Key：', font=('Microsoft YaHei', 10),
             fg='#333', bg='white').pack(anchor='w', pady=(10, 4))

    entry = tk.Entry(content, font=('Consolas', 11), bg='#fafafa',
                     relief='solid', bd=1)
    entry.pack(fill='x', ipady=6)
    entry.focus_set()

    def toggle_show():
        if entry.cget('show') == '*':
            entry.config(show='')
            toggle_btn.config(text='隐藏')
        else:
            entry.config(show='*')
            toggle_btn.config(text='显示')
    toggle_btn = tk.Button(content, text='显示', font=('Microsoft YaHei', 9),
                           bg='#f0f0f0', relief='flat', command=toggle_show,
                           cursor='hand2', bd=0)
    toggle_btn.pack(anchor='e', pady=(4, 0))

    tk.Label(content, text='获取 Key: https://platform.deepseek.com/',
             font=('Microsoft YaHei', 9), fg='#1677ff', bg='white').pack(anchor='w')

    result = {'key': None}

    def on_submit():
        key = entry.get().strip()
        if not key:
            messagebox.showwarning('提示', '请输入 API Key', parent=dialog)
            return
        if not key.startswith('sk-'):
            if not messagebox.askyesno('确认',
                    'Key 似乎不是以 sk- 开头，确定要继续吗？', parent=dialog):
                return
        result['key'] = key
        dialog.destroy()

    def on_cancel():
        result['key'] = None
        dialog.destroy()

    btn_frame = tk.Frame(content, bg='white')
    btn_frame.pack(fill='x', pady=(16, 0))

    tk.Button(btn_frame, text='稍后再说', command=on_cancel,
              font=('Microsoft YaHei', 10), bg='#e0e0e0', fg='#666',
              relief='flat', padx=16, pady=6, cursor='hand2').pack(side='left')
    tk.Button(btn_frame, text='💾 保存并使用', command=on_submit,
              font=('Microsoft YaHei', 10, 'bold'), bg='#1677ff', fg='white',
              relief='flat', padx=16, pady=6, cursor='hand2').pack(side='right')

    dialog.protocol('WM_DELETE_WINDOW', on_cancel)
    root.wait_window(dialog)
    return result['key']


def save_api_key(new_key):
    """Save API key to config.json and update openai.api_key."""
    config_path = os.path.join(get_data_dir(), 'config.json')
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except:
            pass
    config['open_ai_api_key'] = new_key
    config['open_ai_api_base'] = DEEPSEEK_API_BASE
    config['model'] = 'deepseek-chat'
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    openai.api_key = new_key
    print(f"[KeyCheck] Saved new API key to {config_path}")


def _prompt_new_api_key():
    """Called from bot thread when Insufficient Balance detected."""
    global _key_expired_notified
    new_key = show_api_key_dialog()
    if new_key:
        save_api_key(new_key)
        _key_expired_notified = False
        update_balance_display()
        messagebox.showinfo('已更新', '新 API Key 已保存，机器人将继续工作。')
    else:
        _key_expired_notified = True


# ============================================================
# UI Update Handlers
# ============================================================

def update_balance_display():
    """Refresh token balance on screen."""
    status = get_token_status()
    balance = status.get('balance', 0)
    total_used = status.get('total_used', 0)
    call_count = status.get('call_count', 0)

    color = '#27ae60' if balance > 100000 else '#e74c3c'
    balance_label.config(text=format_number(balance), foreground=color)
    used_label.config(text=f"已使用: {format_number(total_used)} tokens | 调用次数: {call_count}")

    if balance <= 0:
        balance_warning_label.config(text='Token已用完，请购买续费')
        balance_warning_label.pack()
    else:
        balance_warning_label.pack_forget()


def on_qr_ready(qr_path):
    """Called when QR code is ready to display."""
    if qr_path is None:
        qr_status_label.config(text='QR生成失败，请检查网络连接', foreground='#e74c3c')
        return
    poll_qr_code(os.path.dirname(qr_path))


def on_login_ok():
    """Called after successful WeChat login."""
    global _logged_in
    _logged_in = True
    qr_status_label.config(text='✅ 已登录', foreground='#27ae60')
    login_btn.config(text='已登录', state='disabled')
    status_bar.config(text=f'微信AI助手 - 已连接 | 剩余Token: {format_number(get_token_status().get("balance", 0))}')


def logout():
    """Log out and clear saved session."""
    global _logged_in, _itchat_instance
    if _itchat_instance:
        try:
            _itchat_instance.logout()
        except:
            pass
        _itchat_instance = None
    _logged_in = False
    bot_state.set_itchat(None)
    # Delete saved session file
    qr_dir = os.path.join(get_data_dir(), 'qr_cache')
    pkl_path = os.path.join(qr_dir, 'itchat.pkl')
    if os.path.exists(pkl_path):
        os.remove(pkl_path)
        print("[Bot] Login session file deleted")
    qr_status_label.config(text='已退出登录', foreground='#e74c3c')
    login_btn.config(text='扫码登录', state='normal')
    status_bar.config(text='微信AI助手 - 未连接')
    print("[Bot] Logged out")


def start_bot():
    """Start bot login thread."""
    global _scanning
    if _scanning or _logged_in:
        return

    qr_dir = os.path.join(get_data_dir(), 'qr_cache')
    qr_status_label.config(text='正在生成二维码...', foreground='#333')
    login_btn.config(state='disabled')

    t = threading.Thread(
        target=bot_thread_main,
        args=(qr_dir, on_qr_ready, on_login_ok, logout),
        daemon=True,
    )
    t.start()
    root.after(1000, poll_qr_code, qr_dir)


def open_admin_panel():
    """Open admin panel in browser."""
    webbrowser.open('http://localhost:5001')


def show_about():
    """Show about dialog."""
    info = get_user_info()
    messagebox.showinfo(
        '关于',
        f'微信AI助手 v1.0\n\n'
        f'新用户赠送100万Token\n'
        f'基于DeepSeek大语言模型\n\n'
        f'机器码: {info.get("machine_id", "")}\n'
        f'许可证: {info.get("license_key", "")}'
    )


# ============================================================
# Splash Screen
# ============================================================

def show_splash():
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.title('')

    sw, sh = 400, 200
    ws = splash.winfo_screenwidth()
    hs = splash.winfo_screenheight()
    x = (ws // 2) - (sw // 2)
    y = (hs // 2) - (sh // 2)
    splash.geometry(f'{sw}x{sh}+{x}+{y}')
    splash.configure(bg='#27ae60')

    frame = tk.Frame(splash, bg='#27ae60')
    frame.pack(expand=True, fill='both')

    tk.Label(
        frame, text='微信AI助手', font=('Microsoft YaHei', 22, 'bold'),
        fg='white', bg='#27ae60'
    ).pack(pady=(40, 5))

    tk.Label(
        frame, text='正在初始化...', font=('Microsoft YaHei', 11),
        fg='#d5f5e3', bg='#27ae60'
    ).pack()

    progress = ttk.Progressbar(frame, mode='indeterminate', length=250)
    progress.pack(pady=15)
    progress.start(15)

    splash.update()
    return splash


# ============================================================
# Main Window
# ============================================================

def build_main_window():
    """Build the main Tkinter window."""
    global root, balance_label, used_label, balance_warning_label
    global qr_label, qr_status_label, login_btn, status_bar, remember_var

    root.title('微信AI助手')
    root.geometry('480x700')
    root.minsize(420, 600)
    root.configure(bg='#f5f5f5')

    try:
        root.iconbitmap(os.path.join(_MEIPASS, 'icon.ico'))
    except Exception:
        pass

    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws // 2) - 240
    y = (hs // 2) - 350
    root.geometry(f'480x700+{x}+{y}')

    # --- Title Bar ---
    title_frame = tk.Frame(root, bg='#27ae60', height=60)
    title_frame.pack(fill='x')
    title_frame.pack_propagate(False)

    tk.Label(
        title_frame, text='🤖 微信AI助手', font=('Microsoft YaHei', 16, 'bold'),
        fg='white', bg='#27ae60'
    ).pack(expand=True)

    # --- Token Balance Card ---
    card_frame = tk.Frame(root, bg='white', relief='solid', bd=1)
    card_frame.pack(fill='x', padx=15, pady=(15, 5))

    tk.Label(
        card_frame, text='剩余Token', font=('Microsoft YaHei', 11),
        fg='#888', bg='white'
    ).pack(pady=(12, 0))

    balance_label = tk.Label(
        card_frame, text='0', font=('Consolas', 32, 'bold'),
        fg='#27ae60', bg='white'
    )
    balance_label.pack(pady=(0, 2))

    used_label = tk.Label(
        card_frame, text='已使用: 0 tokens | 调用次数: 0',
        font=('Microsoft YaHei', 9), fg='#999', bg='white'
    )
    used_label.pack(pady=(0, 5))

    balance_warning_label = tk.Label(
        card_frame, text='Token已用完，请购买续费',
        font=('Microsoft YaHei', 10, 'bold'), fg='#e74c3c', bg='white'
    )

    # --- User Info ---
    info = get_user_info()
    info_frame = tk.Frame(root, bg='#f5f5f5')
    info_frame.pack(fill='x', padx=15, pady=(0, 10))

    tk.Label(
        info_frame, text=f'机器码: {info.get("machine_id", "")}',
        font=('Consolas', 8), fg='#bbb', bg='#f5f5f5'
    ).pack(side='left')

    tk.Label(
        info_frame, text=f'许可: {info.get("license_key", "")}',
        font=('Consolas', 8), fg='#bbb', bg='#f5f5f5'
    ).pack(side='right')

    # --- QR Code Area ---
    qr_frame = tk.Frame(root, bg='white', relief='solid', bd=1)
    qr_frame.pack(fill='both', expand=True, padx=15, pady=5)

    qr_label = tk.Label(qr_frame, bg='white', text='', font=('Microsoft YaHei', 11))
    qr_label.pack(expand=True)

    qr_placeholder = tk.Label(
        qr_frame, text='📱\n点击下方按钮扫码登录',
        font=('Microsoft YaHei', 13), fg='#ccc', bg='white'
    )
    qr_placeholder.pack(expand=True)

    qr_status_label = tk.Label(
        qr_frame, text='未登录', font=('Microsoft YaHei', 10),
        fg='#999', bg='white'
    )
    qr_status_label.pack(pady=(0, 10))

    # --- Buttons ---
    btn_frame = tk.Frame(root, bg='#f5f5f5')
    btn_frame.pack(fill='x', padx=15, pady=(5, 10))

    login_btn = tk.Button(
        btn_frame, text='扫码登录', command=start_bot,
        font=('Microsoft YaHei', 11), bg='#27ae60', fg='white',
        activebackground='#219a52', activeforeground='white',
        relief='flat', padx=20, pady=8, cursor='hand2'
    )
    login_btn.pack(side='left', fill='x', expand=True, padx=(0, 5))

    admin_btn = tk.Button(
        btn_frame, text='打开管理后台', command=open_admin_panel,
        font=('Microsoft YaHei', 11), bg='#3498db', fg='white',
        activebackground='#2980b9', activeforeground='white',
        relief='flat', padx=20, pady=8, cursor='hand2'
    )
    admin_btn.pack(side='left', fill='x', expand=True, padx=5)

    about_btn = tk.Button(
        btn_frame, text='关于', command=show_about,
        font=('Microsoft YaHei', 11), bg='#95a5a6', fg='white',
        activebackground='#7f8c8d', activeforeground='white',
        relief='flat', padx=20, pady=8, cursor='hand2'
    )
    about_btn.pack(side='left', fill='x', expand=True, padx=(5, 0))

    # --- Remember & Logout row ---
    option_frame = tk.Frame(root, bg='#f5f5f5')
    option_frame.pack(fill='x', padx=15, pady=(0, 10))

    remember_var = tk.BooleanVar(value=True)
    remember_cb = tk.Checkbutton(
        option_frame, text='记住登录状态（下次自动登录）',
        variable=remember_var,
        font=('Microsoft YaHei', 9), fg='#666', bg='#f5f5f5',
        activebackground='#f5f5f5', selectcolor='#f5f5f5'
    )
    remember_cb.pack(side='left')

    logout_btn = tk.Button(
        option_frame, text='退出登录', command=logout,
        font=('Microsoft YaHei', 9), bg='#e74c3c', fg='white',
        activebackground='#c0392b', activeforeground='white',
        relief='flat', padx=12, pady=4, cursor='hand2'
    )
    logout_btn.pack(side='right')

    # --- Status Bar ---
    status_frame = tk.Frame(root, bg='#ecf0f1', height=28)
    status_frame.pack(fill='x', side='bottom')
    status_frame.pack_propagate(False)

    status_bar = tk.Label(
        status_frame, text='微信AI助手 - 就绪',
        font=('Microsoft YaHei', 9), fg='#555', bg='#ecf0f1', anchor='w'
    )
    status_bar.pack(fill='x', padx=10, pady=4)

    # Replace placeholder with real QR label when available
    qr_placeholder.bind('<Destroy>', lambda e: None)


# ============================================================
# Config Setup
# ============================================================

def setup_config():
    """Write config.json for chatgpt-on-wechat compatibility."""
    config_path = os.path.join(get_data_dir(), 'config.json')
    if os.path.exists(config_path):
        return
    config = {
        "channel_type": "wx",
        "model": "deepseek-chat",
        "open_ai_api_key": DEEPSEEK_API_KEY,
        "open_ai_api_base": DEEPSEEK_API_BASE,
        "proxy": "",
        "hot_reload": False,
        "single_chat_prefix": [""],
        "single_chat_reply_prefix": "",
        "group_chat_prefix": ["@bot"],
        "group_name_white_list": [],
        "image_create_prefix": ["画"],
        "speech_recognition": False,
        "group_speech_recognition": False,
        "voice_reply_voice": False,
        "conversation_max_tokens": 2500,
        "expires_in_seconds": 3600,
        "character_desc": "你是基于DeepSeek大语言模型的AI智能助手。",
        "temperature": 0.7,
        "subscribe_msg": "感谢关注！这里是AI智能助手。",
        "use_linkai": False,
        "linkai_api_key": "",
        "linkai_app_code": ""
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ============================================================
# Entry Point
# ============================================================

root = None
balance_label = None
used_label = None
balance_warning_label = None
qr_label = None
qr_status_label = None
login_btn = None
status_bar = None
remember_var = None


def main():
    global root

    # Fix PyInstaller windowed mode: redirect stdout/stderr to file
    # (itchat needs stdout to exist, even in windowed mode)
    if getattr(sys, 'frozen', False):
        import io
        sys.stdout = open(get_log_path(), 'a', encoding='utf-8', buffering=1)
        sys.stderr = sys.stdout

    root = tk.Tk()

    # First-run init: copy config files to data dir
    _first_run_init()

    # Show splash
    splash = show_splash()
    root.withdraw()

    # Initialize
    splash.update()
    time.sleep(0.3)

    try:
        token_info = init_token_system()
        global _token_info
        _token_info = token_info
    except Exception as e:
        splash.destroy()
        root.deiconify()
        messagebox.showerror('初始化失败', f'Token系统初始化失败:\n{str(e)}')
        root.destroy()
        return

    setup_config()

    # Start admin server
    start_admin_server(5001)

    # Build main window
    splash.destroy()
    root.deiconify()
    root.after(0, build_main_window)
    root.after(200, update_balance_display)

    # Show welcome message for new users
    if token_info.get('is_new'):
        root.after(500, lambda: messagebox.showinfo(
            '欢迎', f'🎉 您是新用户！\n\n已赠送 {format_number(1000000)} Token（100万）\n\n'
                     f'机器码: {token_info.get("machine_id", "")}\n'
                     f'许可证: {token_info.get("license_key", "")}'
        ))

    # Periodic balance refresh
    def refresh_balance():
        if _logged_in:
            update_balance_display()
        root.after(30000, refresh_balance)

    root.after(35000, refresh_balance)
    root.mainloop()


if __name__ == '__main__':
    main()
