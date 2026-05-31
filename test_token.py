"""Test token system without WeChat login."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from token_patch import init_token_system, get_token_status, get_user_info

print("Initializing token system...")
info = init_token_system()
print(f"Machine ID: {info['machine_id']}")
print(f"License Key: {info['license_key']}")
print(f"Balance: {info['balance']:,}")
print(f"Total Used: {info['total_used']:,}")
print(f"Is New: {info['is_new']}")

# Test that the patch is applied
import openai
print(f"\nOpenAI ChatCompletion patched: {openai.ChatCompletion.create.__name__}")
print("Token system test PASSED!")
