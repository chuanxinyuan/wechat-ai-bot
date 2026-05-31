import sys, os, threading, time

sys.path.insert(0, "/app")
sys.path.insert(0, "/patches")
os.chdir("/app")

# 第一步：导入 app，触发所有模块初始化
import app as _app

# 第二步：app.run() 阻塞，另起线程等登录完成后打补丁
def _delayed_patch():
    time.sleep(15)  # 等 itchat 登录 + channel startup 完成
    from patch_filter import apply_patches
    apply_patches()

threading.Thread(target=_delayed_patch, daemon=True).start()

# 第三步：启动 app（会阻塞等待扫码登录）
_app.run()
