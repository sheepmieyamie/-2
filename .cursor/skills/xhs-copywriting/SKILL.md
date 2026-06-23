---
name: xhs-copywriting
description: 基于对标账号风格档案生成小红书文案。在用户要求仿写对标账号、生成小红书笔记、创作种草/干货/探店文案时使用。
---

# 小红书对标仿写文案

## 内容库 API

后端运行在 `http://127.0.0.1:8000`

| 操作 | 方法 | 路径 |
|------|------|------|
| 添加对标账号 | POST | `/api/accounts` |
| 账号列表 | GET | `/api/accounts` |
| 账号详情+风格档案 | GET | `/api/accounts/{id}` |
| AI 对话生成 | POST | `/api/chat` |

## 添加对标账号

```json
POST /api/accounts
{
  "share_text": "小红书主页分享链接或 @用户名 分享文本",
  "note_limit": 20
}
```

系统通过 TikHub API 抓取用户信息及近期笔记，自动分析账号特征并存入内容库。

## 账号风格档案字段

- `summary`：整体风格摘要
- `metrics`：标题均长、正文均长、emoji 频率、平均点赞
- `title_patterns`：标题模式（疑问式、数字清单型等）
- `top_hashtags` / `top_tags`：高频话题标签
- `writing_style_hints`：文风提示（如「高频 emoji」「姐妹称呼」）
- `top_performing_notes`：高赞笔记样本

## 文案生成

```json
POST /api/chat
{
  "message": "帮我写一篇夏季防晒好物推荐",
  "account_id": 1,
  "session_id": ""
}
```

`account_id` 指定对标账号；不传则使用通用小红书风格。

## 输出格式

```
【标题】15-25字，吸引眼球
【正文】分段清晰，口语化，适当 emoji
【话题标签】3-5 个 #话题
```

## 仿写原则

1. 模仿对标账号的标题结构、语气、emoji 习惯和分段方式
2. 参考 `top_performing_notes` 中的高赞样本
3. 复用 `top_hashtags` 中的话题标签策略
4. 配合 `xhs-content-check` skill 做三层合规检测（违禁词/限流词/素人专项）
