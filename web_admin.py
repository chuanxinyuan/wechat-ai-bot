"""
WeChat Bot Web Admin — Windows 本地版
"""
from flask import Flask, request, jsonify, render_template_string
import json, os, threading, time, sys

app = Flask(__name__)

try:
    from token_patch import get_token_status, get_user_info
except ImportError:
    def get_token_status(): return {'balance': 0, 'total_used': 0, 'call_count': 0}
    def get_user_info(): return {'machine_id': '', 'license_key': ''}

from data_dir import get_data_dir

BASE_DIR = get_data_dir()
# Template path: bundled in EXE (frozen) or project dir (dev)
if getattr(sys, 'frozen', False):
    TEMPLATE_DIR = os.path.join(sys._MEIPASS, 'templates')
else:
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
PERSONAS_PATH = os.path.join(BASE_DIR, "personas.json")
WHITELIST_PATH = os.path.join(BASE_DIR, "whitelist.json")
DATA_DIR = os.path.join(BASE_DIR, "data")

def read_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/")
def index():
    try:
        with open(os.path.join(TEMPLATE_DIR, "admin.html"), "r", encoding="utf-8") as f:
            html = f.read()
        return render_template_string(html)
    except:
        return "<h1>管理后台</h1><p>模板文件未找到</p>"

@app.route("/api/contacts")
def api_contacts():
    import bot_state, traceback
    itchat = bot_state.get_itchat()
    if itchat is None:
        return jsonify({"contacts": [], "personas": {}, "whitelist": [], "err": "未登录微信（bot_state.itchat=None）"})
    try:
        friends = itchat.get_friends(update=False)
    except Exception as e:
        return jsonify({"contacts": [], "personas": {}, "whitelist": [], "err": f"get_friends异常: {str(e)}"})
    whitelist = read_json(WHITELIST_PATH)
    personas = read_json(PERSONAS_PATH)
    contacts = []
    seen = set()
    for f in friends:
        nick = f.get("NickName", "") or ""
        remark = f.get("RemarkName", "") or ""
        uname = f.get("UserName", "")
        sex = f.get("Sex", 0)
        sig = (f.get("Signature") or "")[:50]
        name = remark or nick
        if not name or name in seen:
            continue
        seen.add(name)
        contact_roles = personas.get("联系人角色", {})
        has_persona = name in contact_roles
        persona_data = contact_roles.get(name, {}) if has_persona else {}
        contacts.append({
            "nick": nick, "remark": remark, "name": name, "username": uname,
            "sex": "男" if sex == 1 else "女" if sex == 2 else "未知",
            "signature": sig,
            "whitelisted": name in whitelist or nick in whitelist or remark in whitelist,
            "has_persona": has_persona,
            "persona": {
                "_key": name,
                "微信昵称": persona_data.get("微信昵称", nick),
                "备注名": persona_data.get("备注名", remark),
                "alias": persona_data.get("alias", ""),
                "关系": persona_data.get("关系", ""),
                "对方信息": persona_data.get("对方信息", ""),
                "互动方式": persona_data.get("互动方式", ""),
                "聊天风格": persona_data.get("聊天风格", []),
            } if has_persona else {},
        })
    return jsonify({"contacts": contacts, "personas": personas, "whitelist": whitelist, "err": None})

@app.route("/api/whitelist/toggle", methods=["POST"])
def api_toggle():
    data = request.json
    name, nick, remark = data.get("name",""), data.get("nick",""), data.get("remark","")
    enabled = data.get("enabled", True)
    wl = read_json(WHITELIST_PATH)
    if not isinstance(wl, list): wl = []
    if enabled:
        for n in [name, nick, remark]:
            if n and n not in wl:
                wl.append(n); break
    else:
        for n in [name, nick, remark]:
            while n in wl: wl.remove(n)
    write_json(WHITELIST_PATH, wl)
    return jsonify({"ok": True})

@app.route("/api/personas", methods=["POST"])
def api_persona():
    data = request.json
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"error": "需要角色名称"}), 400
    personas = read_json(PERSONAS_PATH)
    if "联系人角色" not in personas: personas["联系人角色"] = {}
    personas["联系人角色"][key] = {
        "微信昵称": data.get("nick", ""),
        "备注名": data.get("remark", ""),
        "alias": data.get("alias", ""),
        "关系": data.get("relation", ""),
        "对方信息": data.get("their_info", ""),
        "互动方式": data.get("interaction", ""),
        "聊天风格": [s.strip() for s in data.get("chat_style", "").split("\n") if s.strip()],
    }
    write_json(PERSONAS_PATH, personas)
    return jsonify({"ok": True, "key": key})

@app.route("/api/personas/delete", methods=["POST"])
def api_persona_delete():
    key = request.json.get("key", "")
    personas = read_json(PERSONAS_PATH)
    if key in personas.get("联系人角色", {}):
        del personas["联系人角色"][key]
        write_json(PERSONAS_PATH, personas)
    return jsonify({"ok": True})

@app.route("/api/shared", methods=["POST"])
def api_shared():
    data = request.json
    personas = read_json(PERSONAS_PATH)
    personas["共享信息"] = {
        "name": data.get("name", ""),
        "age": data.get("age", ""),
        "birth_year": data.get("birth_year", ""),
        "status": data.get("status", ""),
    }
    personas["人设规则"] = {
        "通用规则": [s.strip() for s in data.get("rules", "").split("\n") if s.strip()]
    }
    write_json(PERSONAS_PATH, personas)
    return jsonify({"ok": True})


@app.route("/token")
def token_page():
    status = get_token_status()
    info = get_user_info()
    balance = status.get('balance', 0)
    total_used = status.get('total_used', 0)
    call_count = status.get('call_count', 0)
    machine_id = info.get('machine_id', '')
    license_key = info.get('license_key', '')

    color = '#27ae60' if balance > 100000 else '#e74c3c'

    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token管理 - 微信AI助手</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", sans-serif; background: #f5f5f5; color: #333; }
.header { background: ''' + color + '''; color: white; padding: 20px; text-align: center; }
.header h1 { font-size: 22px; }
.balance-card {
  background: white; margin: 20px auto; max-width: 500px;
  border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; text-align: center;
}
.balance-number { font-size: 48px; font-weight: bold; color: ''' + color + '''; font-family: Consolas, monospace; }
.balance-label { color: #888; font-size: 14px; margin-bottom: 10px; }
.stats { display: flex; justify-content: center; gap: 40px; margin: 20px 0; }
.stat-item { text-align: center; }
.stat-value { font-size: 20px; font-weight: bold; color: #555; }
.stat-label { font-size: 12px; color: #999; }
.info-card {
  background: white; margin: 15px auto; max-width: 500px;
  border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px;
}
.info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.info-row:last-child { border-bottom: none; }
.info-key { color: #888; }
.info-val { color: #333; font-family: Consolas, monospace; }
.purchase-card {
  background: #fff3cd; margin: 15px auto; max-width: 500px;
  border-radius: 8px; border: 1px solid #ffc107; padding: 20px; text-align: center;
}
.purchase-card h3 { color: #856404; margin-bottom: 10px; }
.purchase-card p { color: #856404; font-size: 14px; }
.nav { text-align: center; margin: 15px; }
.nav a { color: #3498db; text-decoration: none; font-size: 14px; }
.nav a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="header"><h1>Token管理</h1></div>
<div class="balance-card">
  <div class="balance-label">剩余Token</div>
  <div class="balance-number">''' + f'{balance:,}' + '''</div>
</div>
<div class="stats">
  <div class="stat-item"><div class="stat-value">''' + f'{total_used:,}' + '''</div><div class="stat-label">已使用</div></div>
  <div class="stat-item"><div class="stat-value">''' + str(call_count) + '''</div><div class="stat-label">调用次数</div></div>
</div>
<div class="info-card">
  <div class="info-row"><span class="info-key">许可证</span><span class="info-val">''' + license_key + '''</span></div>
  <div class="info-row"><span class="info-key">机器码</span><span class="info-val">''' + machine_id + '''</span></div>
</div>
<div class="purchase-card">
  <h3>购买Token</h3>
  <p>Token用完了？点击下方联系购买</p>
  <a href="https://yuhan.chat/contact.html" target="_blank" style="display:inline-block;margin-top:8px;padding:8px 20px;background:#1677ff;color:#fff;border-radius:6px;text-decoration:none;font-size:13px">📞 联系客服</a>
</div>
<div class="nav"><a href="/">← 返回管理后台</a></div>
</body>
</html>'''
    return render_template_string(html)


@app.route("/api/token")
def api_token():
    status = get_token_status()
    info = get_user_info()
    return jsonify({
        'balance': status.get('balance', 0),
        'total_used': status.get('total_used', 0),
        'call_count': status.get('call_count', 0),
        'machine_id': info.get('machine_id', ''),
        'license_key': info.get('license_key', ''),
    })


@app.route("/api/status")
def api_status():
    import bot_state
    bs = bot_state.get_status()
    return jsonify({
        'logged_in': bs['logged_in'],
        'login_status': bs['login_status'],
        'last_error': bs['last_error'],
        'token_status': get_token_status(),
    })
