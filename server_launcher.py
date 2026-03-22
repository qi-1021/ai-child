#!/usr/bin/env /opt/anaconda3/bin/python
import subprocess
import sys
import os
import time

def start_server(port=8000):
    env = os.environ.copy()
    env['PYTHONPATH'] = '/Volumes/mac第二磁盘/ai-child/server'
    env['LLM_PROVIDER'] = 'dashscope'
    env['DASHSCOPE_API_KEY'] = 'sk-1435063985134058862382c9714bab35'
    env['DASHSCOPE_MODEL'] = 'qwen3.5-35b-a3b'

    cmd = [
        sys.executable, '-m', 'uvicorn', 'main:app',
        '--host', '0.0.0.0',
        '--port', str(port)
    ]

    print(f"Starting server on port {port}...")
    subprocess.run(cmd, cwd='/Volumes/mac第二磁盘/ai-child', env=env)

if __name__ == '__main__':
    start_server(8000)
