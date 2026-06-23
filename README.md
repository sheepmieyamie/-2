# 小红书内容库 · AI 文案助手

对标账号抓取分析 + AI 仿写文案 + 违禁词合规检测。

## 功能

- 通过 TikHub API 抓取小红书对标账号信息与近期笔记
- 自动分析账号风格特征（标题模式、emoji、话题标签、高赞样本等）
- 前端对话界面，选择对标账号后 AI 仿写文案
- 违禁词库检测 + AI 自动修正

## 快速开始

### 1. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

## AI 配置说明

当前使用 Claude API（`ANTHROPIC_*` 环境变量）。

> **注意**：若你使用的代理（如 photoliv）提示 `only allows Claude Code clients`，说明该密钥**仅限 Claude Code 终端工具使用**，无法用于本项目后端。需要向服务商申请**通用 API 密钥**，或换用 OpenAI / DeepSeek 等兼容接口。

`backend/.env` 示例：

```env
ANTHROPIC_BASE_URL=https://api2.photoliv.com
ANTHROPIC_AUTH_TOKEN=你的密钥
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```


### 2. 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173

## 线上部署

本项目 = **Python 后端（FastAPI）** + **静态前端（`static/`）**。  
Cloudflare Pages **只能托管静态页**，不能直接跑 Python；需前后端分开部署。

### 方案 A：Cloudflare Pages（前端）+ Render（后端 API）

**1. Cloudflare Pages 设置**

| 项 | 值 |
|----|-----|
| 构建命令 | `npm run build` |
| 构建输出目录 | `dist` |
| Node 版本 | 18 或以上 |

仓库根目录已包含 `package.json`，构建会把 `static/` 复制到 `dist/`。

**2. Render 部署后端**

在 [Render](https://render.com) 新建 Web Service，连接本仓库，使用根目录的 `render.yaml`，或在面板中设置：

- Root Directory：`backend`
- Build Command：`pip install -r requirements.txt`
- Start Command：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- 环境变量：参考 `backend/.env.example` 配置 `TIKHUB_API_TOKEN`、`OPENAI_API_KEY` 等

**3. 把前端的 `/api` 指到后端**

部署 Render 后得到地址（如 `https://xxx.onrender.com`），编辑 `static/_redirects`：

```
/api/*  https://你的-render-域名.onrender.com/api/:splat  200
```

重新推送并触发 Pages 构建后，前端页面的 `/api` 请求会转发到 Render。

### 方案 B：仅本机 / 自有服务器

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 `http://服务器IP:8000` 即可（前后端一体）。

## 使用流程

1. 左侧粘贴小红书主页分享链接 → 点击「抓取并分析」
2. 选择对标账号，查看右侧账号特征
3. 在对话框描述想写的主题 → 生成仿写文案
4. 系统自动检测违禁词并标注合规状态

## 违禁词维护

三层检测规则来自 `xhs-content-check` skill：

| 文件 | 层级 | 说明 |
|------|------|------|
| `data/forbidden_words.txt` | Layer 1 违禁词 | 发帖即删/封号 |
| `data/limit_words.json` | Layer 2 限流词 | 降权词 + 替换建议 |

修改后热加载：

```bash
curl -X POST http://localhost:8000/api/forbidden-words/reload
```

检测接口：

```bash
curl -X POST http://localhost:8000/api/check-forbidden \
  -H "Content-Type: application/json" \
  -d '{"text": "你的帖子内容"}'
```

## Cursor Skills

- `.cursor/skills/xhs-content-check` — 三层违禁词/限流词检测（来自你提供的 skill）
- `.cursor/skills/xhs-copywriting` — 对标仿写文案
