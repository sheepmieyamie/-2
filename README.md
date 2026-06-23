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

## 线上部署（完整功能，推荐）

本项目后端会**同时托管网页和 API**（`static/` + `/api`），**只部署一个服务即可使用全部功能**，无需 Cloudflare Pages + 后端两套。

推荐平台：[Render](https://render.com)（免费档可试用，首次打开可能较慢）。

---

### 第一步：准备 API 密钥

部署前准备好以下密钥（与本地 `backend/.env` 相同）：

| 变量名 | 说明 | 获取方式 |
|--------|------|----------|
| `TIKHUB_API_TOKEN` | 抓取小红书数据 | [tikhub.io](https://tikhub.io) 注册 |
| `OPENAI_API_KEY` | AI 生成文案 | 你的 DeepSeek / OpenAI 兼容 API 密钥 |
| `OPENAI_BASE_URL` | API 地址 | 例：`https://api.deepseek.com/v1` |

---

### 第二步：在 Render 创建服务

**方式 A — Blueprint（最简单）**

1. 打开 https://dashboard.render.com/
2. 右上角 **New +** → **Blueprint**
3. 连接 GitHub 账号，选择仓库 **`sheepmieyamie/-2`**
4. Render 会读取根目录的 `render.yaml`，点击 **Apply**
5. 在环境变量页面填入：
   - `TIKHUB_API_TOKEN`
   - `OPENAI_API_KEY`
   - `OPENAI_BASE_URL`（DeepSeek 示例：`https://api.deepseek.com/v1`）
6. 点击 **Deploy Blueprint**，等待 3～5 分钟

**方式 B — 手动创建 Web Service**

1. **New +** → **Web Service** → 选择仓库 `-2`
2. 填写：

| 配置项 | 填写内容 |
|--------|----------|
| Name | `xhs-content-library`（任意） |
| Region | Singapore（离国内较近） |
| Branch | `main` |
| Root Directory | `backend` |
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

3. 展开 **Environment**，添加环境变量（见上表）
4. 可选：Health Check Path 填 `/api/health`
5. 点击 **Create Web Service**

---

### 第三步：验证是否成功

部署完成后，Render 会给你一个地址，例如：

`https://xhs-content-library.onrender.com`

1. 浏览器打开该地址 → 应看到「小红书内容库」页面
2. 打开 `https://你的地址.onrender.com/api/health` → 应返回 `{"status":"ok"}` 之类 JSON
3. 在网页里粘贴小红书主页链接 → 点「抓取并分析」→ 能成功说明 TikHub 配置正确
4. 选对标账号后发一条消息 → 能回复说明 AI 配置正确

---

### 常见问题

**免费版第一次打开很慢？**  
Render 免费服务闲置后会休眠，首次访问需等待约 30～60 秒唤醒，属正常现象。

**抓取或 AI 报错？**  
到 Render 控制台 → 你的服务 → **Logs**，查看具体错误；多数是环境变量未填或填错。

**对标账号 / 对话记录会丢吗？**  
免费版使用 SQLite，**重新部署**时数据可能清空；日常重启一般保留。重要数据请定期在本机备份。

**还想用 Cloudflare Pages？**  
可以，但需额外配置 `static/_redirects` 把 `/api` 代理到 Render 地址，比单 Render 部署更复杂，一般不必。

---

### 本地 vs 线上

| | 本地 | Render 线上 |
|--|------|-------------|
| 启动 | `uvicorn ... --port 8000` | Render 自动启动 |
| 访问 | http://127.0.0.1:8000 | `https://xxx.onrender.com` |
| 配置 | `backend/.env` | Render 环境变量面板 |

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
