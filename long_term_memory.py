"""
Long-term memory: store important facts per contact in JSON.
"""
import os
import json
import re
from data_dir import get_data_dir

FACTS_FILE = os.path.join(get_data_dir(), "contact_facts.json")


def _load_facts():
    try:
        if os.path.exists(FACTS_FILE):
            with open(FACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return {}


def _save_facts(facts):
    os.makedirs(os.path.dirname(FACTS_FILE), exist_ok=True)
    with open(FACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)


def get_facts(contact_name):
    facts = _load_facts()
    return facts.get(contact_name, [])


def add_fact(contact_name, fact):
    facts = _load_facts()
    if contact_name not in facts:
        facts[contact_name] = []
    fact = fact.strip()
    if fact and fact not in facts[contact_name]:
        facts[contact_name].append(fact)
        _save_facts(facts)
        return True
    return False


def parse_and_store_facts(contact_name, reply_text):
    import re
    import json

    # 1. 处理【记忆:】标签（自然语言事实）
    memory_pattern = r'【记忆:\s*(.*?)】'
    memory_matches = re.findall(memory_pattern, reply_text, re.DOTALL)
    for match in memory_matches:
        for fact in re.split(r'[；;]', match):
            fact = fact.strip()
            if fact:
                add_fact(contact_name, fact)

    # 2. 处理【学习: {...JSON...}】标签（人设进化数据）
    learn_pattern = r'【学习:\s*(\{.*?\})】'
    learn_match = re.search(learn_pattern, reply_text, re.DOTALL)
    if learn_match:
        try:
            learn_data = json.loads(learn_match.group(1))
            # 保存"记忆"中的事实
            for fact in learn_data.get("记忆", []):
                if fact.strip():
                    add_fact(contact_name, fact.strip())
            # 尝试更新 personas.json 的对方信息、关系、互动方式
            try:
                from data_dir import get_data_dir
                p_path = os.path.join(get_data_dir(), "personas.json")
                if os.path.exists(p_path):
                    with open(p_path, "r", encoding="utf-8") as f:
                        personas = json.load(f)
                    contacts = personas.get("联系人角色", {})
                    if contact_name in contacts:
                        changed = False
                        for field in ["对方信息", "关系", "互动方式"]:
                            val = learn_data.get(field, "")
                            if val and val != contacts[contact_name].get(field, ""):
                                contacts[contact_name][field] = val
                                changed = True
                        if changed:
                            with open(p_path, "w", encoding="utf-8") as f:
                                json.dump(personas, f, ensure_ascii=False, indent=2)
            except:
                pass
        except json.JSONDecodeError:
            pass

    # 3. 剥离所有标签后返回
    clean = re.sub(memory_pattern, '', reply_text).strip()
    clean = re.sub(learn_pattern, '', clean).strip()
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    return clean


def build_facts_prompt(contact_name):
    facts = get_facts(contact_name)
    if not facts:
        return ""
    lines = ["\n关于对方你知道这些重要信息："]
    for f in facts[-10:]:
        lines.append(f"- {f}")
    return "\n".join(lines)
