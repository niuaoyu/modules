# JD 招聘信息解析器（Web 版）

输入一个招聘链接，本地网页自动完成：**抓取 → OCR（微信图片）→ 大模型结构化解析**，同时展示 OCR 原文和 JSON 结果。

## 功能

- 单条 URL 交互式查询
- 支持：微信公众号文章（正文图片自动 OCR）、高校就业网、招聘系统等普通网页
- 多源大模型降级（OpenRouter + OpenCode），免费模型限流自动切换

## 环境要求

- Windows 10/11（复用系统 Edge 浏览器，无需单独下载）
- Python 3.10+

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --timeout 120

# 2. 配置密钥
# 复制 .env.example 为 .env，填入你的 key
cp .env.example .env

# 3. 启动服务
python app.py
```

启动后浏览器访问：**http://127.0.0.1:8000**

在输入框粘贴招聘链接 → 点「解析」→ 左侧看 OCR 原文，右侧看结构化 JSON。

## 配置说明（.env）

模型服务通过**编号 provider** 配置，支持任意服务商 + 两种接口格式（chat / responses），按编号顺序降级：

```ini
LLM_PROVIDER_1_NAME=openai
LLM_PROVIDER_1_BASE_URL=https://api.openai.com/v1
LLM_PROVIDER_1_API_KEY=sk-你的key
LLM_PROVIDER_1_FORMAT=responses          # chat 或 responses
LLM_PROVIDER_1_MODELS=gpt-5-mini,gpt-4o-mini   # 逗号分隔的降级链
```

**BASE_URL 规则**：
- 以 `/chat/completions` 结尾 → 直接作 chat 端点
- 以 `/responses` 结尾 → 直接作 responses 端点
- 否则视为 base，自动拼接：`chat → {base}/chat/completions`，`responses → {base}/responses`

**`FORMAT` 两种格式**：
- `chat`：OpenAI 兼容的 Chat Completions（`messages` 数组），OpenRouter/DeepSeek/通义/绝大多数服务商都支持
- `responses`：OpenAI 新版 Responses API（`input` 字段），仅 OpenAI 官方和少数服务商支持

> 换模型 = 在 `.env` 里加一组 `LLM_PROVIDER_N_*` 即可，无需改代码。`.env` 已加入 `.gitignore`，不会提交到 git。

**服务与调优变量**：`HOST` / `PORT` / `REQUEST_TIMEOUT` / `RETRY_COUNT` / `MAX_INPUT_CHARS` / `MAX_TECH_STACK`。

## 免费模型须知（重要）

免费模型有**每日调用配额**和**限流**：
- OpenRouter 免费模型：每天有 `free-models-per-day` 上限，用完后返回 429
- OpenCode `space-bunny-free`：目前唯一可通过 API 直连的免费模型，其余免费档返回 403
- 本项目已内置**多源降级链**，一个源限流自动切下一个

如果免费额度不够用，建议在 `.env` 换成你自己的付费 key（OpenRouter 充值后可用任意模型）。

## 结构化字段

`企业 / 职位 / 行业 / 工作地点 / 技术栈 / 硬性门槛(学历·专业·经验·英语·其他) / 薪资 / 是否开发岗 / 投递地址 / 来源链接`

## 目录结构

```
jd_webapp/
├── app.py            # FastAPI 主应用
├── fetcher.py        # 抓取 + OCR
├── llm.py            # 大模型调用 + Prompt
├── config.py         # 配置加载
├── index.html        # 前端页面
├── requirements.txt
├── .env.example      # 配置模板
└── .gitignore
```
