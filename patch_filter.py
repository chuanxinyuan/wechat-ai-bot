"""单路径方案：延迟注入，等 app 启动完成后再装补丁"""
import json, os, random, time, sys, threading, queue as _queue, re as _re

# ─── 加载配置（纯文件操作，不 import app 的模块） ───
import data_dir as _dd
_data_dir = _dd.get_data_dir()
whitelist_path = os.path.join(_data_dir, "whitelist.json")
personas_path = os.path.join(_data_dir, "personas.json")

def _get_whitelist():
    """每次调用都重新读取白名单（支持热更新）"""
    try:
        if os.path.exists(whitelist_path):
            with open(whitelist_path, encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return []

def _get_personas():
    """每次调用都重新读取人设（支持热更新）"""
    try:
        if os.path.exists(personas_path):
            with open(personas_path, encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return {}

_user_persona_prompt = {}

def _build_persona_prompt(contact_name, nick="", remark=""):
    pdata = _get_personas()
    shared = pdata.get("共享信息", {})
    rules = pdata.get("人设规则", {}).get("通用规则", [])
    contacts = pdata.get("联系人角色", {})
    default = pdata.get("默认", {})
    role = None; display_name = contact_name
    for cname, cdata in contacts.items():
        if cname == contact_name: role = cdata; display_name = cname; break
        if nick and cdata.get("微信昵称", "") == nick: role = cdata; display_name = cname; break
        if remark and cdata.get("备注名", "") == remark: role = cdata; display_name = cname; break
    if role is None: role = default
    parts = []
    name = shared.get("name", "你"); age = shared.get("age", ""); status = shared.get("status", "")
    show_name = role.get("alias", "") or display_name or contact_name
    parts.append(f"你是{name}，{age}岁，{status}。你现在在微信上和{show_name}聊天。")
    alias = role.get("alias", "")
    if alias: parts.append(f"你叫他/她{alias}。")
    relation = role.get("关系", "")
    if relation: parts.append(f"你们的关系：{relation}")
    info = role.get("对方信息", "")
    if info: parts.append(f"关于他/她：{info}")
    interaction = role.get("互动方式", "")
    if interaction: parts.append(f"互动方式：{interaction}")
    parts.append(""); parts.append("❗重要规则：")
    for r in rules: parts.append(f"- {r}")
    parts.append("- 回复要简短，每次不超过30个字，对方说多长你也说多长，甚至更短")
    parts.append("- 不要一次发太多信息，分多次慢慢聊，像正常人聊天一样")
    style = role.get("聊天风格", default.get("聊天风格", []))
    if style:
        parts.append(""); parts.append("聊天风格：")
        for s in style: parts.append(f"- {s}")
    # 人设进化指令
    parts.append("")
    parts.append("【人设进化系统】")
    parts.append("每当你从对话中学到关于对方的新信息，在回复末尾附加一行：")
    parts.append("【学习: {\"记忆\":[\"事实1\",\"事实2\"],\"对方信息\":\"关于对方的最新描述\",\"关系\":\"更新后的关系描述\",\"互动方式\":\"聊天方式\",\"我的信息\":\"你自己的信息\"}】")
    parts.append("规则：只记录你新发现的重要信息，不要重复已知道的。不要编造。如果没有新信息可学，就省略【学习:】标签。")
    parts.append("这条【学习:】标签我会在处理时自动去掉，对方看不到，放心使用。")
    return "\n".join(parts)

_processed_ids = set()
_session_name_map = {}  # session_id → contact_name 映射表

# ─── 长期记忆 ───
_DATA_DIR = os.path.join(_data_dir, "data")
_HISTORY_QUEUE_PATH = os.path.join(_DATA_DIR, "chat_queue.json")
_CONTACT_FACTS_PATH = os.path.join(_DATA_DIR, "contact_facts.json")

def _load_contact_facts():
    """加载所有联系人的重要信息"""
    try:
        if os.path.exists(_CONTACT_FACTS_PATH):
            with open(_CONTACT_FACTS_PATH, "r", encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return {}

def _save_contact_fact(contact_name, fact):
    """保存一条重要信息"""
    facts = _load_contact_facts()
    if contact_name not in facts:
        facts[contact_name] = []
    if fact not in facts[contact_name]:
        facts[contact_name].append(fact)
        try:
            with open(_CONTACT_FACTS_PATH, "w", encoding='utf-8') as f:
                json.dump(facts, f, ensure_ascii=False, indent=2)
        except: pass

_PERSONAS_PATH = os.path.join(_data_dir, "personas.json")  # 人设文件路径

def _save_learning(contact_name, learn_data):
    """保存AI学习到的信息到记忆和人设文件"""
    if not learn_data or not isinstance(learn_data, dict):
        return
    # 1. 保存事实到 contact_facts.json
    facts = learn_data.get("记忆", [])
    if facts:
        for fact in facts:
            _save_contact_fact(contact_name, fact.strip())
        print(f"[Patch] 🧠 已保存 {len(facts)} 条记忆: [{contact_name}]: {facts}", flush=True)
    # 2. 更新 personas.json（后台管理可见）
    try:
        if os.path.exists(_PERSONAS_PATH):
            with open(_PERSONAS_PATH, "r", encoding='utf-8') as f:
                personas = json.load(f)
        else:
            personas = {}
        display_name = _get_contact_display_name(contact_name)
        contacts = personas.get("联系人角色", {})
        target_key = None
        for cname in contacts:
            if cname == display_name or cname == contact_name:
                target_key = cname
                break
        if target_key is None:
            target_key = display_name
            if "联系人角色" not in personas:
                personas["联系人角色"] = {}
            personas["联系人角色"][target_key] = {
                "微信昵称": contact_name, "备注名": display_name,
                "alias": "", "关系": "", "对方信息": "", "互动方式": "", "聊天风格": []
            }
        changed = False
        role = personas["联系人角色"][target_key]
        for field in ["对方信息", "关系", "互动方式"]:
            val = learn_data.get(field, "")
            if val and val != role.get(field, ""):
                role[field] = val
                changed = True
                print(f"[Patch] 📝 更新 {target_key}.{field}: {val[:60]}", flush=True)
        my_info = learn_data.get("我的信息", "")
        if my_info and len(my_info) > 5:
            shared = personas.get("共享信息", {})
            existing_info = shared.get("状态", "")
            if my_info not in existing_info:
                shared["状态"] = existing_info + ("；" + my_info if existing_info else my_info)
                personas["共享信息"] = shared
                changed = True
                print(f"[Patch] 📝 更新共享信息.状态: {my_info[:60]}", flush=True)
        if changed:
            with open(_PERSONAS_PATH, "w", encoding='utf-8') as f:
                json.dump(personas, f, ensure_ascii=False, indent=2)
            print(f"[Patch] ✅ 人设进化已保存到 personas.json", flush=True)
    except Exception as e:
        print(f"[Patch] ⚠️ 更新人设失败: {e}", flush=True)
        
_MY_NAME = None  # 缓存"我"的名字

def _get_my_name():
    global _MY_NAME
    if _MY_NAME:
        return _MY_NAME
    try:
        pdata = _get_personas()
        _MY_NAME = pdata.get("共享信息", {}).get("name", "我")
    except:
        _MY_NAME = "我"
    return _MY_NAME

def _get_contact_display_name(contact_name_from_file):
    """反向解析 contact_name → 显示名"""
    try:
        pdata = _get_personas()
        contacts = pdata.get("联系人角色", {})
        for cname, cdata in contacts.items():
            if cdata.get("备注名") == contact_name_from_file or cdata.get("微信昵称") == contact_name_from_file:
                return cname
    except: pass
    return contact_name_from_file

def _load_recent_history(contact_name, max_msgs=20):
    """从队列文件加载最近 N 条与该联系人的聊天记录，返回格式化文本"""
    try:
        if not os.path.exists(_HISTORY_QUEUE_PATH):
            return ""
        with open(_HISTORY_QUEUE_PATH, "r", encoding='utf-8') as f:
            queue = json.load(f)
        # 用 display_name 来匹配
        display_name = _get_contact_display_name(contact_name)
        my_name = _get_my_name()
        matched = []
        for e in queue:
            cn = e.get("contact_name", "")
            # 匹配：contact_name 可能是备注名、昵称或 display_name
            if cn == display_name or cn == contact_name:
                matched.append(e)
        recent = matched[-max_msgs:]
        if not recent:
            return ""
        lines = []
        for e in recent:
            direction = e.get("direction", "")
            if direction == "incoming":
                # 对方发来的 → [张三]: xxx
                speaker = display_name
            else:
                # 我发出的 → [我]: xxx
                speaker = my_name
            lines.append(f"[{speaker}]: {e.get('content', '')}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Patch] ⚠️ 加载历史失败: {e}", flush=True)
        return ""

def _load_persistent_memory(contact_name):
    """加载该联系人的持久化记忆"""
    facts = _load_contact_facts()
    return facts.get(contact_name, [])

def apply_patches():
    """wait for channel to be created, then hook instance methods"""
    # Windows 兼容：/patches 是 Docker 路径，本地用 BASE_DIR
    if os.path.exists("/patches"):
        sys.path.insert(0, "/patches")
    
    import channel.wechat.wechat_channel as _ch_mod
    from lib import itchat as _itchat
    import bot.session_manager as _sm
    import db_saver
    from datetime import datetime as _dt, timedelta as _td
    
    # ─── 补丁1：Session.add_query → 时间注入（北京时间） ───
    _orig_add_query = _sm.Session.add_query
    def _patched_add_query(self, query):
        utc_now = _dt.utcnow()
        cst_now = utc_now + _td(hours=8)  # UTC+8 北京时间
        weekday = ["一","二","三","四","五","六","日"][cst_now.weekday()]
        now_fmt = cst_now.strftime(f"%Y-%m-%d %H:%M (周{weekday})")
        return _orig_add_query(self, f"[当前时间:{now_fmt}] {query}")
    _sm.Session.add_query = _patched_add_query
    
    # ─── 补丁2：SessionManager.session_query → 按联系人切换身份 + 长期记忆 ───
    # 注意：chatgpt-on-wechat 的 Session 已经自动保存历史消息（在 session.messages 里），
    # 我们不需要在 query 里再重复注入历史记录。重复注入会导致 AI 混淆：
    #   - 最新消息同时在"最近聊天记录"和"[新消息]"中出现
    #   - AI 分不清哪个才是"对方刚发来的消息"，会回复错消息
    # 原则：只注入当前需要的上下文（人设+记忆+最新消息），不重复历史。
    _orig_session_query = _sm.SessionManager.session_query
    def _patched_session_query(self, query, session_id):
        persona_prompt = _user_persona_prompt.get(session_id)
        if persona_prompt and session_id not in self.sessions:
            self.build_session(session_id, system_prompt=persona_prompt)
        # 注入上下文：只含身份 + 记忆，不重复历史（session 自带历史）
        contact_name = _session_name_map.get(session_id)
        if contact_name:
            my_name = _get_my_name()
            display_name = _get_contact_display_name(contact_name)
            # 加载通用规则（每次强化）
            try:
                _raw_personas = json.load(open(_PERSONAS_PATH, 'r', encoding='utf-8'))
                rules = _raw_personas.get("人设规则", {}).get("通用规则", [])
            except:
                rules = []
            parts = []
            # 你是谁
            parts.append(f"你是{my_name}，正在微信上和{display_name}聊天。")
            # 1. 持久化重要信息（关于对方）
            facts = _load_persistent_memory(contact_name)
            if facts:
                parts.append(f"[你知道关于{display_name}的信息]")
                for f in facts:
                    parts.append(f"- {f}")
                parts.append("")
            # 2. 每次强化回复规则（这些规则虽然在 system prompt 里，但放在 query 末尾效果更好）
            parts.append("【回复规则】")
            for r in rules:
                parts.append(f"- {r}")
            parts.append("- 回复要简短自然，每次只说一句话，最多15个字")
            parts.append("- 对方跟你说什么你就顺着聊什么，不要刻意提自己的事")
            parts.append("- 不要用表情符号，不要波浪号~，不要刻意亲切")
            context = "\n".join(parts)
            # 包装 query，突出这是"对方刚发来的消息，请立即回复"
            query = f"{context}\n\n━━━ 对方刚发来新消息 ━━━\n{display_name}说：{query}\n\n请以{my_name}的身份直接回复这段话，只说一句话："
        return _orig_session_query(self, query, session_id)
    _sm.SessionManager.session_query = _patched_session_query
    
    # ─── 补丁3：itchat.send → 保存出站消息 + 学习进化 ───
    _orig_send = _itchat.send
    def _patched_send(msg, toUserName=None):
        send_msg = str(msg) if msg else msg
        if msg:
            msg_str = str(msg)
            name = ""
            if toUserName:
                try:
                    for f in _itchat.get_friends(update=False):
                        if f.get("UserName") == toUserName:
                            name = f.get("RemarkName") or f.get("NickName") or ""; break
                except: pass
            # 用 display_name 标准化保存
            save_name = name or toUserName or "unknown"
            display = _get_contact_display_name(save_name)
            
            # 解析【学习: JSON】并剥离
            clean_msg = msg_str
            learn_match = _re.search(r'【学习:\s*(\{.*?\})】', msg_str, _re.DOTALL)
            if learn_match:
                try:
                    learn_raw = learn_match.group(1)
                    learn_data = json.loads(learn_raw)
                    _save_learning(display or save_name, learn_data)
                except Exception as e:
                    print(f"[Patch] ⚠️ 解析学习数据失败: {e}", flush=True)
                # 剥离【学习:】标签再发送
                clean_msg = _re.sub(r'\s*【学习:\s*\{.*?\}】\s*', '', msg_str, count=1).strip()
                print(f"[Patch] 🧹 已剥离学习标签, 发送: {clean_msg[:80]}...", flush=True)
            
            db_saver.save_msg(display, "outgoing", clean_msg, "text")
            send_msg = clean_msg
        return _orig_send(send_msg, toUserName)
    _itchat.send = _patched_send
    
    # ─── 补丁4：hook handle_single → 通过 get_instance() 获取实例 ───
    # 注意：WechatChannel 被 @singleton 包裹，导出的是 get_instance 函数
    # 我们直接 hook 已创建实例的方法
    instance = _ch_mod.WechatChannel()  # 通过 singleton 获取实例
    _orig_handle_single = instance.handle_single
    
    def _patched_handle_single(cmsg):
        msg_id = getattr(cmsg, 'msg_id', str(id(cmsg)))
        print(f"[Patch] 📩 收到消息 id={msg_id}, 开始处理...", flush=True)
        if msg_id in _processed_ids:
            print(f"[Patch] ⏭️ 跳过重复消息 {msg_id}", flush=True)
            return
        _processed_ids.add(msg_id)
        
        # ─── 修复：跳过自己发出去的消息（手机发消息 → itchat 收到的事件） ───
        try:
            from_user_id = getattr(cmsg, 'from_user_id', '') or getattr(cmsg, 'other_user_id', '')
            my_self = _itchat.get_friends(update=False)
            if my_self and from_user_id == my_self[0].get('UserName', ''):
                print(f"[Patch] ⏭️ 自己发出去的消息（from_user_id 等于自己）, 跳过", flush=True)
                return
        except Exception as e:
            print(f"[Patch] ⚠️ 自发送检查出错: {e}", flush=True)
        
        name = getattr(cmsg, 'other_user_nickname', '') or getattr(cmsg, 'from_user_nickname', '')
        raw = getattr(cmsg, '_rawmsg', {}) or {}
        user_info = raw.get('User', {}) or {}
        nick = user_info.get('NickName', '') or ''
        remark = user_info.get('RemarkName', '') or ''
        print(f"[Patch] name={name}, nick={nick}, remark={remark}", flush=True)
        
        wl = _get_whitelist()
        # 白名单为空则所有人都不可用
        in_whitelist = (name in wl or nick in wl or remark in wl) if wl else False
        print(f"[Patch] whitelist={wl}, in_whitelist={in_whitelist}", flush=True)
        if not in_whitelist:
            return
        
        session_id = getattr(cmsg, 'other_user_id', '') or getattr(cmsg, 'from_user_id', '')
        if name and session_id:
            _user_persona_prompt[session_id] = _build_persona_prompt(name, nick, remark)
            _session_name_map[session_id] = name  # session_id → name 映射
            print(f"[Patch] ✅ 已设置 persona prompt for session {session_id}", flush=True)
        
        text = getattr(cmsg, 'content', '')
        if text:
            # 用 display_name 标准化保存
            save_name = name or "unknown"
            display = _get_contact_display_name(save_name)
            db_saver.save_msg(display, "incoming", str(text), "text")
        
        now = time.time()
        create_time = int(getattr(cmsg, 'create_time', 0))
        is_new = create_time > now - 60
        if not is_new:
            print(f"[Patch] ⏭️ 历史消息({create_time} vs now {int(now)}), 跳过不回复", flush=True)
            return
        
        incoming_len = len(text)
        # 延迟公式：消息短也至少15秒，长的按字数递增，最大180秒
        delay = min(180, max(15, random.uniform(12, 25) + incoming_len / 3))
        print(f"[Patch] ⏳ 延迟 {delay:.0f}秒 (消息长度{incoming_len}字)...", flush=True)
        time.sleep(delay)
        print(f"[Patch] ⏳ 延迟结束, 手动 produce...", flush=True)
        
        print(f"[Patch] 🔍 手动 produce: session={session_id}, type={getattr(cmsg, 'ctype', '?')}", flush=True)
        try:
            from bridge.context import Context, ContextType
            manual_ctx = Context(getattr(cmsg, 'ctype', ContextType.TEXT), text)
            manual_ctx.kwargs = {'isgroup': False, 'msg': cmsg}
            manual_ctx['session_id'] = session_id
            manual_ctx['receiver'] = session_id
            manual_ctx['origin_ctype'] = getattr(cmsg, 'ctype', ContextType.TEXT)
            instance.produce(manual_ctx)
            print(f"[Patch] ✅ 手动 produce 完成", flush=True)
        except Exception as e:
            import traceback
            print(f"[Patch] ❌ 手动 produce 报错: {e}", flush=True)
            traceback.print_exc()
    
    instance.handle_single = _patched_handle_single
    print("[Patch] ✅ 所有补丁已应用 (直接 hook 实例方法)", flush=True)
    
    # ─── 定时导出联系人列表 ───
    _CONTACT_EXPORT_PATH = os.path.join(_DATA_DIR, "contacts.json")
    def _export_contacts_loop():
        time.sleep(10)
        while True:
            try:
                friends = _itchat.get_friends(update=True)
                result = []
                for f in friends:
                    nick = f.get('NickName', '') or ''
                    remark = f.get('RemarkName', '') or ''
                    uname = f.get('UserName', '')
                    sex = f.get('Sex', 0)
                    sig = (f.get('Signature') or '')[:50]
                    if nick or remark:
                        result.append({"nick": nick, "remark": remark, "username": uname, "sex": sex, "signature": sig})
                with open(_CONTACT_EXPORT_PATH, "w", encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False)
            except Exception as e:
                try:
                    with open(_CONTACT_EXPORT_PATH + ".err", "a", encoding='utf-8') as f:
                        f.write(f"{e}\n")
                except:
                    pass
            time.sleep(60)
    threading.Thread(target=_export_contacts_loop, daemon=True).start()
