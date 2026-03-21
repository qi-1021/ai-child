#!/bin/bash
cd /Volumes/mac第二磁盘/ai-child
export PYTHONPATH=/Volumes/mac第二磁盘/ai-child/server
export LLM_PROVIDER=dashscope
export DASHSCOPE_API_KEY=sk-1435063985134058862382c9714bab35
export DASHSCOPE_MODEL=qwen3.5-35b-a3b
/opt/anaconda3/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
