"""
Skill Manager - load skill markdown files and inject into system prompts.
Supports global skills (applied to all) and per-contact skills.
"""
import os
import json
from data_dir import get_data_dir

SKILLS_DIR = os.path.join(get_data_dir(), "skills")
SKILLS_CONFIG = os.path.join(get_data_dir(), "skills_config.json")


def _parse_skill(filepath):
    """Parse a SKILL.md file, extract YAML frontmatter and body."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                # Simple YAML-like parsing: name: value
                meta = {}
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = parts[2].strip()
                return meta, body
        return {}, content
    except Exception:
        return {}, ""


def list_skills():
    """List all available skills."""
    skills = []
    if not os.path.exists(SKILLS_DIR):
        return skills
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if fname.endswith(".md"):
            filepath = os.path.join(SKILLS_DIR, fname)
            meta, _ = _parse_skill(filepath)
            skills.append({
                "id": fname.replace(".md", ""),
                "name": meta.get("name", fname),
                "description": meta.get("description", ""),
                "file": fname,
            })
    return skills


def get_skill_prompt(skill_id):
    """Get the prompt body for a specific skill."""
    filepath = os.path.join(SKILLS_DIR, f"{skill_id}.md")
    if not os.path.exists(filepath):
        return ""
    _, body = _parse_skill(filepath)
    return body


def load_skills_config():
    """Load which skills are assigned globally and per-contact."""
    try:
        if os.path.exists(SKILLS_CONFIG):
            import json
            with open(SKILLS_CONFIG, "r", encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return {"global": [], "contacts": {}}


def save_skills_config(config):
    """Save skills assignment config."""
    os.makedirs(os.path.dirname(SKILLS_CONFIG), exist_ok=True)
    import json
    with open(SKILLS_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_global_skills_prompt():
    """Get combined prompt from all globally assigned skills."""
    config = load_skills_config()
    parts = []
    for skill_id in config.get("global", []):
        prompt = get_skill_prompt(skill_id)
        if prompt:
            parts.append(f"\n## 已激活技能：{skill_id}\n\n{prompt}")
    return "\n".join(parts)


def save_skill(name, content, description=""):
    """Save a new skill or update existing one."""
    safe_id = "".join(c for c in name if c.isalnum() or c in "_- ")
    safe_id = safe_id.strip().replace(" ", "-").lower()
    if not safe_id: safe_id = "skill"
    os.makedirs(SKILLS_DIR, exist_ok=True)
    filepath = os.path.join(SKILLS_DIR, f"{safe_id}.md")
    desc_line = f"description: {description}\n" if description else ""
    full = f"---\nname: {name}\n{desc_line}---\n\n{content}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full)
    return safe_id


def delete_skill(skill_id):
    """Delete a skill file."""
    filepath = os.path.join(SKILLS_DIR, f"{skill_id}.md")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False


def get_contact_skills_prompt(contact_name):
    """Get combined prompt from skills assigned to a specific contact."""
    config = load_skills_config()
    parts = []
    contact_skills = config.get("contacts", {}).get(contact_name, [])
    for skill_id in contact_skills:
        prompt = get_skill_prompt(skill_id)
        if prompt:
            parts.append(f"\n## 对此联系人使用技能：{skill_id}\n\n{prompt}")
    return "\n".join(parts)
