# -*- coding: utf-8 -*-
"""FastAPI 主应用：输入 URL → 返回 OCR 文本 + LLM 结构化 JSON"""
import os

# 修复：让本地回环地址不走系统代理（否则 127.0.0.1 请求会被透明代理拦截导致 502/超时）
_no_proxy = "127.0.0.1,localhost,::1"
if os.environ.get("NO_PROXY"):
    os.environ["NO_PROXY"] = os.environ["NO_PROXY"] + "," + _no_proxy
else:
    os.environ["NO_PROXY"] = _no_proxy
# 小写版本（requests 会读这两个）
os.environ["no_proxy"] = os.environ["NO_PROXY"]

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

import config
import fetcher
import llm

app = FastAPI(title="JD 招聘信息解析器")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class AnalyzeRequest(BaseModel):
    url: str


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    # 注意：用同步 def（非 async），FastAPI 会丢线程池执行，
    # 避免 Playwright 同步 API 阻塞 async 事件循环导致卡死
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL 不能为空")

    # 1. 抓取 + OCR
    try:
        typ, raw_text = fetcher.fetch(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抓取失败：{e}")

    # 2. LLM 结构化
    try:
        model, data = llm.analyze(url, raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 解析失败：{e}")

    return {
        "url": url,
        "type": typ,
        "ocr_text": raw_text,
        "model": model,
        "json": data,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
