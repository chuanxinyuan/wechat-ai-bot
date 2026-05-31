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
    pattern = r'【记忆:\s*(.*?)】'
    matches = re.findall(pattern, reply_text, re.DOTALL)
    for match in matches:
        for fact in re.split(r'[；;]', match):
            fact = fact.strip()
            if fact:
                add_fact(contact_name, fact)
    clean = re.sub(pattern, '', reply_text).strip()
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
