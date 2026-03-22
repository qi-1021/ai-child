#!/usr/bin/env /opt/anaconda3/bin/python
"""
最简单的测试服务器
"""
import sys
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import threading

# 设置环境
sys.path.insert(0, '/Volumes/mac第二磁盘/ai-child/server')
os.environ['LLM_PROVIDER'] = 'dashscope'
os.environ['DASHSCOPE_API_KEY'] = 'sk-1435063985134058862382c9714bab35'
os.environ['DASHSCOPE_MODEL'] = 'qwen3.5-35b-a3b'

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/chat/text':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            # 简单的测试响应
            response = {
                'reply': '你好! 我是一个测试AI。',
                'proactive_question': '你叫什么名字?'
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(format % args)

def run_server(port=8000):
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"✅ 测试服务器运行在 http://localhost:{port}")
    print(f"   /health - 健康检查")
    print(f"   /chat/text - 发送消息")
    server.serve_forever()

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
