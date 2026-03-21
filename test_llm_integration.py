"""快速测试 LLM 集成是否正常工作"""
import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, '/Volumes/mac第二磁盘/ai-child/server')

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置测试用的环境变量
os.environ.setdefault('LLM_PROVIDER', 'dashscope')
os.environ.setdefault('DASHSCOPE_API_KEY', 'sk-1435063985134058862382c9714bab35')
os.environ.setdefault('DASHSCOPE_MODEL', 'qwen3.5-35b-a3b')

from ai.llm_provider import get_llm_client, initialize_llm_provider
from config import settings

async def test_llm():
    """测试 LLM 连接"""
    print(f"🔧 LLM 提供商: {settings.llm_provider}")
    print(f"🔑 使用的模型: {settings.dashscope_model if settings.llm_provider == 'dashscope' else settings.openai_model}")
    
    # 初始化
    initialize_llm_provider()
    
    # 获取客户端
    client = get_llm_client()
    print("✅ 客户端初始化成功")
    
    # 测试 API 调用
    try:
        response = await client.chat.completions.create(
            model=settings.dashscope_model if settings.llm_provider == 'dashscope' else settings.openai_model,
            messages=[
                {"role": "system", "content": "你是一个有用的助手。"},
                {"role": "user", "content": "你好，请自我介绍一下"}
            ],
            max_tokens=200,
            temperature=0.7,
        )
        
        print("🎯 API 调用成功！")
        print(f"📝 回复: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ API 调用失败: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_llm())
    exit(0 if success else 1)
