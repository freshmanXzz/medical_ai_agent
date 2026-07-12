"""LangChain DeepSeek Chat Model 封装模块

提供基于 langchain_openai.ChatOpenAI 调用 DeepSeek API 的功能，
利用 DeepSeek 兼容 OpenAI 协议的特性实现 LLM 调用。

使用方式:
    from martin.llm.chat_model import get_chat_model, validate_api_key

    model = get_chat_model(temperature=0.3)
    response = model.invoke("你好")
"""

from typing import Optional

from langchain_openai import ChatOpenAI

from martin.config import config

# 模块级缓存，避免重复创建 ChatOpenAI 实例
_chat_model: Optional[ChatOpenAI] = None


def get_chat_model(**kwargs) -> ChatOpenAI:
    """获取 DeepSeek ChatOpenAI 实例。

    使用模块级缓存，首次调用时创建实例并缓存，
    后续调用直接返回缓存实例。

    Args:
        **kwargs: 可覆盖的 ChatOpenAI 参数，支持:
            - temperature (float): 生成温度，默认 0.1
            - max_tokens (int): 最大生成 Token 数，默认 4096
            - timeout (int): 请求超时时间（秒），默认 60
            以及其他 ChatOpenAI 支持的所有参数。

    Returns:
        ChatOpenAI: 配置好的 ChatOpenAI 实例。

    Raises:
        ValueError: 当 DEEPSEEK_API_KEY 环境变量未设置时抛出。

    Examples:
        >>> model = get_chat_model()
        >>> model = get_chat_model(temperature=0.5, max_tokens=2048)
    """
    global _chat_model

    if _chat_model is not None:
        return _chat_model

    api_key = config.deepseek_api_key
    if not api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY 环境变量未设置，请先设置后再调用。"
        )

    # 默认参数，允许通过 kwargs 覆盖
    default_params = {
        "model": config.deepseek_model,
        "api_key": api_key,
        "base_url": config.deepseek_base_url,
        "temperature": 0.1,
        "max_tokens": 4096,
        "timeout": 60,
    }
    # 用传入的参数覆盖默认值
    default_params.update(kwargs)

    _chat_model = ChatOpenAI(**default_params)
    return _chat_model


def validate_api_key() -> bool:
    """验证 DeepSeek API 密钥是否有效。

    通过调用 API 获取可用模型列表来验证密钥的有效性。

    Returns:
        bool: 密钥有效返回 True，无效返回 False。
    """
    api_key = config.deepseek_api_key
    if not api_key:
        return False

    try:
        # 创建临时实例进行验证，不干扰缓存
        temp_model = ChatOpenAI(
            model=config.deepseek_model,
            api_key=api_key,
            base_url=config.deepseek_base_url,
            timeout=10,
        )
        # 发起一次轻量请求验证密钥
        temp_model.invoke("ping")
        return True
    except Exception:
        return False


def clear_chat_model_cache() -> None:
    """清除缓存的 ChatOpenAI 实例。

    当需要重新创建实例（如更换 API 密钥或模型配置）时调用。
    """
    global _chat_model
    _chat_model = None
