"""Minimal itchat login test - server-style approach."""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["WECHAT_TYPE"] = "uos"

from lib import itchat
import types
from qrcode import QRCode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
qr_path = os.path.join(BASE_DIR, "qr_cache", "QR.png")
pkl_path = os.path.join(BASE_DIR, "qr_cache", "itchat.pkl")
os.makedirs(os.path.dirname(qr_path), exist_ok=True)

# Step 1: Pre-get UUID (like server launcher does)
print("Step 1: Getting UUID...")
uuid = itchat.get_QRuuid()
if not uuid:
    print("FAILED: could not get UUID")
    sys.exit(1)
print(f"UUID: {uuid}")

# Step 2: Generate QR code from UUID
print("Step 2: Generating QR code...")
url = 'https://login.weixin.qq.com/l/' + uuid
qr = QRCode()
qr.add_data(url)
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
img.save(qr_path)
print(f"QR saved to: {qr_path}")

# Step 3: Replace itchat's internal get_QR method
print("Step 3: Replacing get_QR method...")
def _replacement_get_QR(self, uuid=None, enableCmdQR=False, picDir=None, qrCallback=None):
    uuid = uuid or self.uuid
    picDir = picDir or 'QR.png'
    qrStorage = io.BytesIO()
    url = 'https://login.weixin.qq.com/l/' + uuid
    qr = QRCode()
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qrStorage, format='PNG')
    if hasattr(qrCallback, '__call__'):
        qrCallback(uuid=uuid, status='0', qrcode=qrStorage.getvalue())
    else:
        with open(picDir, 'wb') as f:
            f.write(qrStorage.getvalue())
    return io.BytesIO(qrStorage.getvalue())

itchat.instance.get_QR = types.MethodType(_replacement_get_QR, itchat.instance)

# Step 4: QR callback
def qr_callback(uuid, status, qrcode):
    print(f"[QR] status={status}")
    if status == "0":
        # Save the QR image
        with open(qr_path, 'wb') as f:
            f.write(qrcode)
        print(f"[QR] Updated QR saved")

def login_callback():
    print("[LOGIN] callback fired!")

# Step 5: Login
print("Step 5: Starting auto_login...")
print(f"pkl exists: {os.path.exists(pkl_path)}")
print("Open this file and scan: " + qr_path)

try:
    itchat.auto_login(
        hotReload=os.path.exists(pkl_path),
        qrCallback=qr_callback,
        loginCallback=login_callback,
        statusStorageDir=pkl_path,
    )
    print("SUCCESS! Logged in.")
    friends = itchat.get_friends()
    print(f"Friends count: {len(friends)}")
    itchat.run()
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FAILED: {e}")
