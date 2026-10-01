# -*- coding: utf-8 -*-
"""LLM 模块：多源降级 + 双格式（chat / responses）+ JSON 解析"""
import json
import time
import requests
import urllib3
import config

# 本地开发环境可能有透明代理做 HTTPS 中间人，禁用证书校验 + 关闭告警
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SYSTEM_PROMPT = (
    "你是一名专业的招聘信息解析助手。把招聘公告文本解析成结构化 JSON。\n"
    "规则：\n"
    "1. 只输出一个合法 JSON 对象，不要任何解释或 markdown 代码块。\n"
    "2. 字段固定：企业、职位、行业、工作地点、技术栈、硬性门槛、薪资、是否开发岗、投递地址、来源链接。\n"
    "3. 【技术栈】收录 JD 中出现的所有技术/工具/框架/语言/平台/细分领域词，越多越好，不漏。\n"
    "4. 【硬性门槛】对象，含 学历、专业、经验、英语、其他。没写填 null 或 []。\n"
    "5. 【是否开发岗】程序员/开发/算法/AI/嵌入式/测试开发 等为 true；销售/财务/HR/客服/市场等为 false。\n"
    "6. 【薪资】统一为 '20k-35k' 格式，没有则 null。\n"
    "7. 值为 null 的字段也要保留。\n"
)


def _resolve_url(provider):
    """根据 base_url 和 format 解析最终端点"""
    base = provider["base_url"]
    fmt = provider.get("format", "chat")
    if base.endswith("/chat/completions") or base.endswith("/responses"):
        return base
    if fmt == "responses":
        return f"{base}/responses"
    return f"{base}/chat/completions"


def _build_payload(provider, model, messages):
    """按 provider 格式构造请求体

    chat:      {"model": ..., "messages": [...]}
    responses: {"model": ..., "input": "..."}  (OpenAI Responses API)
    """
    if provider.get("format") == "responses":
        # Responses API 的 input 支持字符串或消息数组；
        # 这里把 system+user 拼成一段字符串，最通用
        text = "\n\n".join(m["content"] for m in messages)
        return {"model": model, "input": text}
    return {"model": model, "messages": messages}


def _parse_response(provider, resp_json):
    """按 format 从响应里提取文本内容"""
    if provider.get("format") == "responses":
        # Responses API：output 是数组，取第一个 message 的 output_text
        output = resp_json.get("output", [])
        for item in output:
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        return c.get("text", "")
        # 兜底：某些兼容实现仍返回 choices
        if "choices" in resp_json:
            return resp_json["choices"][0]["message"]["content"]
        return ""
    return resp_json["choices"][0]["message"]["content"]


def _call_once(provider, model, messages):
    url = _resolve_url(provider)
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        },
        data=json.dumps(_build_payload(provider, model, messages)),
        timeout=config.REQUEST_TIMEOUT,
        verify=False,  # 兼容本地透明代理的 HTTPS 中间人证书
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    try:
        return True, _parse_response(provider, r.json())
    except Exception as e:
        return False, f"parse error: {e}"


def analyze(url, raw_text):
    """抓取文本 → LLM → 结构化 JSON，返回 (model, json_data)"""
    user = (
        f"请解析以下招聘信息。\n\n"
        f"【来源链接】{url}\n\n"
        f"【正文/OCR文本】\n{raw_text[:config.MAX_INPUT_CHARS]}\n\n"
        f"请输出结构化 JSON。注意：技术栈只收录最关键的 {config.MAX_TECH_STACK} 个以内。"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    last_err = None
    for provider in config.PROVIDERS:
        if not provider["api_key"]:
            continue
        for model in provider["models"]:
            for attempt in range(config.RETRY_COUNT):
                ok, result = _call_once(provider, model, messages)
                if ok:
                    data = extract_json(result)
                    if data:
                        data.setdefault("来源链接", url)
                        return model, data
                    last_err = "JSON 解析失败"
                else:
                    last_err = result
                time.sleep(2 * (attempt + 1))
            time.sleep(1)
    raise RuntimeError(f"所有模型调用失败: {last_err}")


def extract_json(content):
    """稳健提取 JSON 对象"""
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        import re
        fixed = re.sub(r",\s*([}\]])", r"\1", content[start:end + 1])
        try:
            return json.loads(fixed)
        except Exception:
            return None
