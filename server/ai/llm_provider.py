"""LLM 提供商配置管理 — OpenAI 兼容接口（支持 OpenAI、百炼和 Ollama 本地部署）。

百炼 (DashScope) 和 Ollama 均兼容 OpenAI API，只需切换 base_url 和 api_key。
不需要复杂适配层，直接使用 AsyncOpenAI 客户端即可。

全本地部署（无需任何 API Key）：
  1. 安装 Ollama: https://ollama.com
  2. ollama pull llama3.2          # 主对话模型
  3. ollama pull nomic-embed-text  # 嵌入向量模型
  4. 设置环境变量: LLM_PROVIDER=ollama
  5. 正常启动服务端 — 完全离线运行。
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

    # Runtime model override — set by the dream module after creating a new
    # Ollama model generation.  None means "use the config default".
    _active_model: Optional[str] = None

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
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        elif provider == "ollama":
            # Ollama 本地部署：OpenAI 兼容接口，无需 API Key
            logger.info("🖥️  初始化 Ollama 本地客户端 (%s)", settings.ollama_base_url)
            return AsyncOpenAI(
                api_key="ollama",  # Ollama 不需要真实 key，但客户端要求非空
                base_url=settings.ollama_base_url,
            )
        else:
            # OpenAI（默认）
            logger.info("🔑 初始化 OpenAI 客户端")
            return AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url or "https://api.openai.com/v1",
            )

    @classmethod
    def reset(cls) -> None:
        """重置客户端（用于测试或切换提供商）"""
        cls._instance = None
        cls._active_model = None
        logger.info("✅ LLM 客户端已重置")

    @classmethod
    def get_model(cls) -> str:
        """
        Return the currently active model name.

        Priority order:
          1. Runtime override set by ``set_active_model()`` (dream phase).
          2. Provider-specific config default.
        """
        if cls._active_model:
            return cls._active_model
        provider = settings.llm_provider.lower()
        if provider == "ollama":
            return settings.ollama_model
        if provider == "dashscope":
            return settings.dashscope_model
        return settings.openai_model

    @classmethod
    def set_model(cls, model_name: str) -> None:
        """
        Override the active model at runtime.

        Called by the dream module after creating a new Ollama model generation
        so that all subsequent LLM calls use the strengthened model without
        requiring a server restart.
        """
        cls._active_model = model_name
        logger.info("🔄 Active model updated to: %s", model_name)

    @classmethod
    def get_embedding_model(cls) -> str:
        """Return the embedding model name appropriate for the current provider."""
        provider = settings.llm_provider.lower()
        if provider == "ollama":
            return settings.ollama_embedding_model
        return settings.embedding_model


def initialize_llm_provider() -> None:
    """在应用启动时初始化 LLM 提供商"""
    LLMProvider.get_client()
    logger.info("✅ LLM 提供商已初始化: %s  模型: %s", settings.llm_provider, LLMProvider.get_model())


def get_llm_client() -> AsyncOpenAI:
    """便捷函数：获取 LLM 客户端"""
    return LLMProvider.get_client()


def get_active_model() -> str:
    """便捷函数：获取当前活跃模型名称（支持运行时切换）"""
    return LLMProvider.get_model()


def set_active_model(model_name: str) -> None:
    """便捷函数：运行时切换模型（梦境阶段创建新 Ollama 代次后调用）"""
    LLMProvider.set_model(model_name)


def get_embedding_model() -> str:
    """便捷函数：获取当前提供商的嵌入向量模型名称"""
    return LLMProvider.get_embedding_model()
