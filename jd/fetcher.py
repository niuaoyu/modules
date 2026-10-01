# -*- coding: utf-8 -*-
"""抓取 + OCR 模块：按域名路由，返回原始文本"""
import os
import tempfile
from urllib.parse import urlparse

_OCR_ENGINE = None


def _get_ocr():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def classify(url):
    """wechat / html / invalid"""
    if not url or not url.startswith("http"):
        return "invalid"
    if "mp.weixin.qq.com" in urlparse(url).netloc:
        return "wechat"
    return "html"


def _launch(url):
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    return p, browser, ctx, page


def _scroll(page, times=6):
    for _ in range(times):
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(500)


def fetch_html(url):
    """普通网页：提取 body 文本"""
    p, browser, ctx, page = _launch(url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        _scroll(page)
        return page.inner_text("body")
    finally:
        browser.close()
        p.stop()


def fetch_wechat(url):
    """微信文章：正文是图片则下载 + OCR"""
    p, browser, ctx, page = _launch(url)
    tmpdir = tempfile.mkdtemp()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        _scroll(page)
        title = page.title()

        try:
            content_text = page.inner_text("#js_content")
        except Exception:
            content_text = ""

        imgs = page.eval_on_selector_all(
            "#js_content img",
            "els => els.map(e => ({src: e.dataset.src || e.src, w: e.naturalWidth, h: e.naturalHeight})).filter(i => i.src)"
        )
        big_imgs = [i for i in imgs if i.get("w", 0) >= 400]

        parts = [f"标题：{title}"]
        if len(content_text.strip()) > 30:
            parts.append(content_text.strip())

        if big_imgs and len(content_text.strip()) < 100:
            ocr = _get_ocr()
            for i, im in enumerate(big_imgs):
                try:
                    resp = ctx.request.get(im["src"], timeout=20000)
                    if resp.ok:
                        fp = os.path.join(tmpdir, f"tmp_{i}.png")
                        with open(fp, "wb") as f:
                            f.write(resp.body())
                        result, _ = ocr(fp)
                        if result:
                            lines = sorted(result, key=lambda r: (r[0][0][1], r[0][0][0]))
                            parts.append("\n".join(t[1] for t in lines))
                except Exception:
                    continue
        return "\n".join(parts)
    finally:
        browser.close()
        p.stop()
        # 清理临时目录
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def fetch(url):
    """统一入口：返回 (类型, 文本) 或抛异常"""
    typ = classify(url)
    if typ == "invalid":
        raise ValueError("无效的 URL，请输入 http/https 链接")
    if typ == "wechat":
        text = fetch_wechat(url)
    else:
        text = fetch_html(url)
    return typ, text
