"""
Persona engine for wechat-bot-desktop.
Wraps patch_filter.py's persona system for direct itchat use.
Provides hot-reload: reads personas.json and whitelist.json on every call.
"""
import os
import traceback
from data_dir import get_data_dir

BASE_DIR = get_data_dir()

DEFAULT_PROMPT = """你在微信上和朋友聊天。
关系：普通朋友

重要规则：
- 永远不要用括号描述动作或表情
- 就像正常发微信一样，直接说话就行
- 永远不要提自己是AI或机器人，你就是真人
- 回复要简短自然，每次只说一句话，最多15个字
- 不用表情符号，不用波浪号~
- 对方跟你说什么你就顺着聊什么
- 如果对方告诉了你重要信息（名字、年龄、喜好、经历等），在回复末尾用【记忆: 内容】记录下来，例如【记忆: 叫小明，喜欢打篮球】。多条用分号分隔。对方看不到这个标签。"""

# Try to import from patch_filter, fall back gracefully
try:
    from patch_filter import _build_persona_prompt, _get_whitelist, _get_personas
except ImportError:
    def _build_persona_prompt(name, nick, remark):
        return DEFAULT_PROMPT
    def _get_whitelist():
        whitelist_path = os.path.join(BASE_DIR, "whitelist.json")
        try:
            if os.path.exists(whitelist_path):
                import json
                with open(whitelist_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except: pass
        return []
    def _get_personas():
        personas_path = os.path.join(BASE_DIR, "personas.json")
        try:
            if os.path.exists(personas_path):
                import json
                with open(personas_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except: pass
        return {}


def get_persona_prompt(contact_name, nick="", remark=""):
    try:
        prompt = _build_persona_prompt(contact_name, nick, remark)
        if prompt and prompt.strip():
            return prompt
    except Exception:
        traceback.print_exc()
    return DEFAULT_PROMPT


def is_contact_enabled(contact_name):
    try:
        wl = _get_whitelist()
        if not wl:
            return False
        return contact_name in wl
    except Exception:
        traceback.print_exc()
        return False


def get_whitelist():
    return _get_whitelist()


def get_personas():
    return _get_personas()
