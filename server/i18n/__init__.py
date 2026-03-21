"""
Internationalization (i18n) support for AI Child.

Supports: en-US, zh-CN (Chinese)
"""

from typing import Dict, Optional, Any
from .messages import MESSAGES, SYSTEM_PROMPTS

# Supported languages
SUPPORTED_LANGS = ["en-US", "zh-CN"]
DEFAULT_LANG = "en-US"


class I18n:
    """Localization manager for AI Child."""
    
    def __init__(self, language: str = DEFAULT_LANG):
        if language not in SUPPORTED_LANGS:
            language = DEFAULT_LANG
        self.language = language
    
    def t(self, key: str, **kwargs) -> str:
        """
        Translate a message key to the current language.
        
        Usage:
            i18n.t("greeting", name="Alice")  # Returns localized greeting
        
        Args:
            key: Message key (e.g., "greeting", "sleep.message.sleep")
            **kwargs: Variables for string interpolation
        
        Returns:
            Localized message string
        """
        # Support nested keys like "sleep.message.wake"
        keys = key.split(".")
        msg_dict = MESSAGES.get(self.language, {})
        
        # Navigate nested structure
        for k in keys:
            if isinstance(msg_dict, dict):
                msg_dict = msg_dict.get(k, None)
            else:
                return f"[Missing translation: {key}]"
        
        if msg_dict is None:
            # Fallback to English
            msg_dict = MESSAGES.get(DEFAULT_LANG, {})
            for k in keys:
                if isinstance(msg_dict, dict):
                    msg_dict = msg_dict.get(k, None)
                else:
                    return f"[Missing translation: {key}]"
        
        if msg_dict is None:
            return f"[Missing translation: {key}]"
        
        # String interpolation
        if kwargs:
            return msg_dict.format(**kwargs)
        return msg_dict
    
    def system_prompt(self, ai_name: Optional[str] = None, is_sleeping: bool = False) -> str:
        """
        Get the system prompt for the AI in the current language.
        
        Args:
            ai_name: The AI's name (if known)
            is_sleeping: Whether the AI is currently sleeping
        
        Returns:
            System prompt string
        """
        prompts = SYSTEM_PROMPTS.get(self.language, {})
        
        if is_sleeping:
            prompt = prompts.get("sleeping", prompts.get("default", ""))
        else:
            prompt = prompts.get("default", "")
        
        # Insert AI name if provided
        if ai_name and "{ai_name}" in prompt:
            prompt = prompt.replace("{ai_name}", ai_name)
        
        return prompt
    
    def set_language(self, language: str) -> None:
        """Change the current language."""
        if language in SUPPORTED_LANGS:
            self.language = language


# Global i18n instance
_i18n: Optional[I18n] = None


def get_i18n(language: str = DEFAULT_LANG) -> I18n:
    """Get or create the global i18n instance."""
    global _i18n
    if _i18n is None:
        _i18n = I18n(language)
    return _i18n


def set_language(language: str) -> None:
    """Set the global language."""
    i18n = get_i18n()
    i18n.set_language(language)


def t(key: str, language: str = DEFAULT_LANG, **kwargs) -> str:
    """
    Quick translation function.
    
    Usage:
        from i18n import t
        msg = t("greeting.hello", language="zh-CN", name="小明")
    """
    i18n = I18n(language)
    return i18n.t(key, **kwargs)
