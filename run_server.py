import subprocess
import time
import os

# 启动新的服务器在8001端口
env = os.environ.copy()
env['PYTHONPATH'] = '/Volumes/mac第二磁盘/ai-child/server'
env['LLM_PROVIDER'] = 'dashscope'
env['DASHSCOPE_API_KEY'] = 'sk-1435063985134058862382c9714bab35'
env['DASHSCOPE_MODEL'] = 'qwen3.5-35b-a3b'

proc = subprocess.Popen(
    ['/opt/anaconda3/bin/python', '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8001'],
    cwd='/Volumes/mac第二磁盘/ai-child',
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

print("Server starting...")
time.sleep(4)

# 测试服务器
import urllib.request
try:
    response = urllib.request.urlopen("http://localhost:8001/health", timeout=5)
    print("✅ 服务器已启动在 8001!")
    print(response.read().decode())
except Exception as e:
    print(f"❌ 服务器启动失败: {e}")

# Keep process alive
proc.wait()
