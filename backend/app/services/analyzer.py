from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any


def _dig(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def extract_user_profile(raw: dict[str, Any]) -> dict[str, Any]:
    user = _dig(raw, "data", "data") or _dig(raw, "data") or _dig(raw, "user") or raw
    if isinstance(user, dict) and "user" in user and isinstance(user["user"], dict):
        user = user["user"]

    user_id = str(
        user.get("user_id")
        or user.get("userid")
        or user.get("id")
        or ""
    )

    note_num_stat = user.get("note_num_stat") or {}
    posted_stat = 0
    if isinstance(note_num_stat, dict):
        posted_stat = int(note_num_stat.get("posted") or 0)

    return {
        "user_id": user_id,
        "nickname": user.get("nickname") or user.get("name") or "",
        "avatar": user.get("avatar") or user.get("images") or user.get("imageb") or "",
        "bio": user.get("desc") or user.get("description") or "",
        "follower_count": int(
            user.get("fans") or user.get("follower_count") or user.get("followers") or 0
        ),
        "following_count": int(user.get("follows") or user.get("following_count") or 0),
        "note_count": int(
            user.get("notes")
            or user.get("note_count")
            or user.get("ndiscovery")
            or posted_stat
            or 0
        ),
        "liked_count": int(user.get("liked") or user.get("liked_count") or 0),
        "red_id": user.get("red_id") or "",
    }


def extract_notes_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    notes = (
        _dig(raw, "data", "notes")
        or _dig(raw, "data", "data", "notes")
        or _dig(raw, "notes")
        or []
    )
    if not isinstance(notes, list):
        return []

    result = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        note_card = note.get("note_card") or note
        interact = note_card.get("interact_info") or note.get("interact_info") or {}
        tag_list = note_card.get("tag_list") or note.get("tag_list") or []
        tags = [
            t.get("name") if isinstance(t, dict) else str(t)
            for t in tag_list
            if t
        ]

        result.append(
            {
                "note_id": str(
                    note_card.get("note_id") or note_card.get("id") or note.get("id") or ""
                ),
                "title": note_card.get("display_title") or note_card.get("title") or "",
                "content": note_card.get("desc") or note_card.get("content") or "",
                "note_type": note_card.get("type") or note.get("type") or "normal",
                "liked_count": int(
                    interact.get("liked_count")
                    or note_card.get("likes")
                    or note.get("likes")
                    or 0
                ),
                "collected_count": int(
                    interact.get("collected_count")
                    or note_card.get("collected_count")
                    or note.get("collected_count")
                    or 0
                ),
                "comment_count": int(
                    interact.get("comment_count")
                    or note_card.get("comments_count")
                    or note.get("comments_count")
                    or 0
                ),
                "tags": tags,
                "cursor": note.get("cursor") or note_card.get("cursor") or "",
                "raw": note,
            }
        )
    return result


def extract_note_detail(raw: dict[str, Any]) -> dict[str, Any]:
    """从 TikHub 笔记详情接口解析单篇帖子。"""
    data = raw.get("data") if isinstance(raw, dict) else raw
    note_list: list | None = None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            note_list = first.get("note_list")
    elif isinstance(data, dict):
        note_list = data.get("note_list")

    if not note_list or not isinstance(note_list, list):
        return {}

    note = note_list[0]
    if not isinstance(note, dict):
        return {}

    user = note.get("user") or {}
    tags = [
        h.get("name")
        for h in (note.get("hash_tag") or [])
        if isinstance(h, dict) and h.get("name")
    ]

    return {
        "note_id": str(note.get("id") or note.get("note_id") or ""),
        "title": note.get("title") or "",
        "content": note.get("desc") or note.get("content") or "",
        "note_type": note.get("type") or "normal",
        "liked_count": int(note.get("liked_count") or 0),
        "collected_count": int(note.get("collected_count") or 0),
        "comment_count": int(
            note.get("comments_count") or note.get("comment_count") or 0
        ),
        "tags": tags,
        "author_nickname": user.get("nickname") or user.get("name") or "",
    }


def note_dict_to_benchmark_shape(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "note_id": note.get("note_id", ""),
        "title": note.get("title", ""),
        "content": note.get("content", ""),
        "note_type": note.get("note_type", "normal"),
        "liked_count": note.get("liked_count", 0),
        "collected_count": note.get("collected_count", 0),
        "comment_count": note.get("comment_count", 0),
        "tags": note.get("tags") or [],
    }


def analyze_reference_post(note: dict[str, Any]) -> dict[str, Any]:
    author = note.get("author_nickname") or "参考作者"
    shaped = note_dict_to_benchmark_shape(note)
    style = analyze_account_style([shaped], {"nickname": author})
    style["reference_title"] = note.get("title", "")
    return style


def reference_post_to_context(
    title: str,
    content: str,
    author: str,
    tags: list[str],
    style_analysis: dict[str, Any],
    *,
    liked_count: int = 0,
    collected_count: int = 0,
    comment_count: int = 0,
) -> str:
    tag_text = "、".join(f"#{t}" for t in tags[:8]) if tags else "（无）"
    lines = [
        "## 参考帖子（单篇仿写对标）",
        f"标题：{title}",
        f"作者：{author or '未知'}",
        f"互动：点赞 {liked_count} · 收藏 {collected_count} · 评论 {comment_count}",
        f"话题：{tag_text}",
        "",
        "正文：",
        content or "（无正文）",
        "",
        "风格要点：",
        style_analysis.get("summary", ""),
    ]
    for hint in style_analysis.get("writing_style_hints") or []:
        lines.append(f"- {hint}")
    top = (style_analysis.get("top_performing_notes") or [{}])[0]
    if top.get("title"):
        lines.append(f"- 标题结构参考：《{top.get('title')}》")
    return "\n".join(lines)


def _count_emojis(text: str) -> int:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return len(emoji_pattern.findall(text))


def _extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#([^#\s\[\]]+)", text)


def analyze_account_style(notes: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    if not notes:
        return {
            "summary": "暂无足够笔记样本进行分析",
            "profile": profile,
        }

    titles = [n.get("title", "") for n in notes if n.get("title")]
    contents = [n.get("content", "") for n in notes if n.get("content")]
    all_text = "\n".join(titles + contents)

    title_lens = [len(t) for t in titles]
    content_lens = [len(c) for c in contents]
    emoji_counts = [_count_emojis(t) for t in titles + contents]
    all_tags: list[str] = []
    for note in notes:
        all_tags.extend(note.get("tags") or [])

    hashtag_counter = Counter(_extract_hashtags(all_text))
    tag_counter = Counter(all_tags)

    avg_likes = sum(n.get("liked_count", 0) for n in notes) / len(notes)
    top_notes = sorted(notes, key=lambda n: n.get("liked_count", 0), reverse=True)[:5]

    title_patterns = []
    for title in titles[:10]:
        if "？" in title or "?" in title:
            title_patterns.append("疑问式标题")
        if any(w in title for w in ("绝了", "必看", "干货", "教程", "分享")):
            title_patterns.append("种草/干货型")
        if re.search(r"\d+", title):
            title_patterns.append("数字清单型")

    pattern_counter = Counter(title_patterns)

    return {
        "summary": (
            f"参考「{profile.get('nickname', '')}」单篇帖子分析。"
            f"点赞 {avg_likes:.0f}，标题 {sum(title_lens) / max(len(title_lens), 1):.0f} 字，"
            f"正文 {sum(content_lens) / max(len(content_lens), 1):.0f} 字。"
            if len(notes) == 1
            else (
                f"账号「{profile.get('nickname', '')}」共分析 {len(notes)} 篇笔记。"
                f"平均点赞 {avg_likes:.0f}，标题均长 {sum(title_lens) / max(len(title_lens), 1):.0f} 字，"
                f"正文均长 {sum(content_lens) / max(len(content_lens), 1):.0f} 字。"
            )
        ),
        "profile": profile,
        "metrics": {
            "note_sample_count": len(notes),
            "avg_title_length": round(sum(title_lens) / max(len(title_lens), 1), 1),
            "avg_content_length": round(sum(content_lens) / max(len(content_lens), 1), 1),
            "avg_emoji_per_post": round(sum(emoji_counts) / max(len(emoji_counts), 1), 1),
            "avg_likes": round(avg_likes, 1),
        },
        "title_patterns": dict(pattern_counter.most_common(5)),
        "top_hashtags": [
            h for h, _ in (hashtag_counter + tag_counter).most_common(10)
        ],
        "top_tags": [t for t, _ in tag_counter.most_common(10)],
        "top_performing_notes": [
            {
                "title": n.get("title"),
                "liked_count": n.get("liked_count"),
                "content_preview": (n.get("content") or "")[:120],
            }
            for n in top_notes
        ],
        "writing_style_hints": _infer_writing_style(all_text, titles, contents),
    }


def _infer_writing_style(all_text: str, titles: list[str], contents: list[str]) -> list[str]:
    hints: list[str] = []
    if _count_emojis(all_text) > len(titles) * 2:
        hints.append("高频使用 emoji，语气活泼亲切")
    if any("姐妹" in t or "宝子" in t for t in titles + contents):
        hints.append("使用亲密称呼（姐妹/宝子），拉近读者距离")
    if any("｜" in t or "|" in t for t in titles):
        hints.append("标题常用竖线分隔主题与卖点")
    if sum(1 for c in contents if "\n" in c) > len(contents) * 0.5:
        hints.append("正文分段清晰，善用换行提升可读性")
    if _extract_hashtags(all_text):
        hints.append("文末或文中嵌入话题标签 #xxx")
    if not hints:
        hints.append("文风简洁直接，以实用信息为主")
    return hints


def style_profile_to_prompt(style_profile: dict[str, Any]) -> str:
    return json.dumps(style_profile, ensure_ascii=False, indent=2)
