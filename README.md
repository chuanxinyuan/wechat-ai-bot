# 微信AI助手 (WeChat AI Bot)

Windows 桌面版微信 AI 自动回复机器人。用户扫码登录微信后，AI 自动回复好友消息。

## 功能

- 微信扫码登录（UOS 协议，不显示 AI 标签）
- 每人独立人设（身份、关系、回复风格、称呼）
- 20 轮短期对话记忆 + 长期重要信息记忆
- 真人化回复（延迟回复、简短自然、偶尔错别字）
- Token 管理系统（新用户赠送 100 万 Token）
- Web 管理后台（localhost:5001）
- 一键打包 EXE，普通用户双击运行

## 快速开始

### 开发运行

```bash
pip install flask Pillow qrcode[pil] openai==0.28.1
python launcher.py
```

### 打包 EXE

```bash
build.bat
```

输出 `dist/WeChatAIBot.exe`，发给用户双击运行即可。

## 管理后台

启动后浏览器打开 http://localhost:5001

- 联系人管理（开启/关闭 AI 回复）
- 每人独立人设配置
- Token 余额查看
- 购买联系方式

## 数据存储

所有用户数据存储在 `%APPDATA%/WeChatAIBot/`，EXE 同目录保持干净。

## 技术栈

- Python 3.10+ / Tkinter GUI
- itchat-uos（微信 UOS 协议）
- DeepSeek API（OpenAI 兼容）
- Flask Web 管理后台
- SQLite Token 管理
- PyInstaller 打包

## 许可

私有项目，仅供授权用户使用。
