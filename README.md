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
