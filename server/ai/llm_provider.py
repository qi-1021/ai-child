"""LLM 提供商配置管理 — OpenAI 兼容接口（支持 OpenAI 和百炼）。

百炼 (DashScope) 完全兼容 OpenAI API，只需切换 base_url 和 api_key。
不需要复杂适配层，直接使用 AsyncOpenAI 客户端即可。
"""

import logging
from typing import Optional
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 全局 LLM 客户端
# ============================================================================

class LLMProvider:
    """LLM 提供商管理器"""
    
    _instance: Optional[AsyncOpenAI] = None
    
    @classmethod
    def get_client(cls) -> AsyncOpenAI:
        """获取或初始化 LLM 客户端（单例）"""
        if cls._instance is None:
            cls._instance = cls._create_client()
        return cls._instance
    
    @classmethod
    def _create_client(cls) -> AsyncOpenAI:
        """根据配置创建 OpenAI 兼容客户端"""
        provider = settings.llm_provider.lower()
        
        if provider == "dashscope":
            # 百炼：OpenAI 兼容接口
            logger.info("🌐 初始化百炼 (DashScope) 客户端")
            return AsyncOpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        else:
            # OpenAI（默认）
            logger.info("🔑 初始化 OpenAI 客户端")
            return AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url or "https://api.openai.com/v1"
            )
    
    @classmethod
    def reset(cls) -> None:
        """重置客户端（用于测试或切换提供商）"""
        cls._instance = None
        logger.info("✅ LLM 客户端已重置")


def initialize_llm_provider() -> None:
    """在应用启动时初始化 LLM 提供商"""
    client = LLMProvider.get_client()
    logger.info(f"✅ LLM 提供商已初始化: {settings.llm_provider}")


def get_llm_client() -> AsyncOpenAI:
    """便捷函数：获取 LLM 客户端"""
    return LLMProvider.get_client()
