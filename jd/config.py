# -*- coding: utf-8 -*-
"""配置加载：从 .env 读取

支持任意大模型服务商 + 两种接口格式（chat / responses），通过编号的
环境变量声明一个「provider 降级链」。每加一个新模型只需在 .env 里
写一组 LLM_PROVIDER_N_* 变量，无需改代码。
"""
import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "1"))

# 最大输入字符数（免费小模型生成长 JSON 慢，截断以防超时）
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "4000"))
# 技术栈最多收录数量
MAX_TECH_STACK = int(os.getenv("MAX_TECH_STACK", "30"))


def _load_providers():
    """从 .env 读取编号 provider，构建降级链。

    .env 里可声明任意多个 provider，按编号顺序降级：

        LLM_PROVIDER_1_NAME=openai
        LLM_PROVIDER_1_BASE_URL=https://api.openai.com/v1
        LLM_PROVIDER_1_API_KEY=sk-xxx
        LLM_PROVIDER_1_FORMAT=responses          # chat 或 responses
        LLM_PROVIDER_1_MODELS=gpt-5-mini,gpt-4o-mini

        LLM_PROVIDER_2_NAME=openrouter
        LLM_PROVIDER_2_BASE_URL=https://openrouter.ai/api/v1
        LLM_PROVIDER_2_API_KEY=sk-or-xxx
        LLM_PROVIDER_2_FORMAT=chat
        LLM_PROVIDER_2_MODELS=deepseek/deepseek-chat,google/gemma-4-31b-it:free

    BASE_URL 规则：
      - 若以 /chat/completions 结尾，直接用作 chat 端点
      - 若以 /responses 结尾，直接用作 responses 端点
      - 否则视为 base_url，按 format 自动拼接：
          chat      -> {base}/chat/completions
          responses -> {base}/responses
    """
    providers = []
    i = 1
    while True:
        name = os.getenv(f"LLM_PROVIDER_{i}_NAME")
        if not name:
            break
        base_url = os.getenv(f"LLM_PROVIDER_{i}_BASE_URL", "").rstrip("/")
        api_key = os.getenv(f"LLM_PROVIDER_{i}_API_KEY", "")
        fmt = os.getenv(f"LLM_PROVIDER_{i}_FORMAT", "chat").lower()
        models = [
            m.strip()
            for m in os.getenv(f"LLM_PROVIDER_{i}_MODELS", "").split(",")
            if m.strip()
        ]

        if not base_url or not models:
            # 配置不完整的 provider 跳过
            i += 1
            continue

        providers.append({
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "format": fmt,
            "models": models,
        })
        i += 1
    return providers


# 兼容旧版：若没有编号 provider，则回退到旧的 OPENROUTER_API_KEY / OPENCODE_API_KEY
def _legacy_providers():
    providers = []
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append({
            "name": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "format": "chat",
            "models": [
                "inclusionai/ling-3.0-flash-sante:free",
                "nvidia/nemotron-3-super-120b-a12b:free",
                "cohere/north-mini-code:free",
                "google/gemma-4-31b-it:free",
            ],
        })
    if os.getenv("OPENCODE_API_KEY"):
        providers.append({
            "name": "opencode",
            "base_url": "https://opencode.ai/zen/v1",
            "api_key": os.getenv("OPENCODE_API_KEY"),
            "format": "chat",
            "models": ["space-bunny-free"],
        })
    return providers


PROVIDERS = _load_providers() or _legacy_providers()
