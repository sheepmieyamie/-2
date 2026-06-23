from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Optional


def extract_post_number(text: str) -> Optional[int]:
    """从用户描述中解析发帖序号，如「这是我发的第3篇帖子」。"""
    patterns = (
        r"这是我发的第\s*(\d+)\s*篇",
        r"第\s*(\d+)\s*篇帖",
        r"第\s*(\d+)\s*篇",
        r"发帖序号[：:\s]*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            num = int(match.group(1))
            if 1 <= num <= 9999:
                return num
    return None


def extract_post_number_from_messages(messages: list[dict[str, str]]) -> Optional[int]:
    """从对话历史中解析最近一次明确的发帖序号。"""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        num = extract_post_number(msg.get("content", ""))
        if num is not None:
            return num
    return None


FINALIZE_KEYWORDS = (
    "完整方案",
    "出方案",
    "生成方案",
    "最终方案",
    "定稿",
    "就按这个",
    "直接出",
    "可以出了",
    "出完整",
)


def detect_finalize_intent(text: str) -> bool:
    return any(kw in text for kw in FINALIZE_KEYWORDS)


def is_full_plan_reply(text: str) -> bool:
    return "## 📊 对标数据解读" in text and "## 📝 主帖文案" in text


def get_post_phase(post_number: int) -> dict[str, str]:
    if post_number == 1:
        return {
            "phase": "首发破冰",
            "goal": "建立账号第一印象，让读者知道你是谁、做什么",
            "content_focus": "轻自我介绍 + 领域价值预告，避免硬广",
            "risk": "首篇不宜堆砌产品卖点，重在建立信任感",
        }
    if post_number <= 3:
        return {
            "phase": "冷启动期",
            "goal": "巩固人设，测试哪类内容更受欢迎",
            "content_focus": "1-2 篇干货/共鸣向 + 适度种草，观察互动反馈",
            "risk": "避免连续多篇同质内容，类型可交替（干货/种草/日常）",
        }
    if post_number <= 10:
        return {
            "phase": "涨粉爬坡期",
            "goal": "放大已验证的内容方向，提升曝光与收藏",
            "content_focus": "复用高赞选题结构，强化标题钩子与实用价值",
            "risk": "注意发帖节奏，避免一天多篇被判定营销号",
        }
    if post_number <= 30:
        return {
            "phase": "稳定运营期",
            "goal": "维持更新频率，深化垂直领域权威感",
            "content_focus": "系列化选题（合集/连载），绑定粉丝期待",
            "risk": "需定期回顾数据，淘汰低效选题类型",
        }
    return {
        "phase": "成熟运营期",
        "goal": "品牌心智巩固与转化",
        "content_focus": "高信任内容 + 软性转化，可穿插用户故事",
        "risk": "避免内容疲劳，尝试新形式（视频/图文切换）",
    }


def summarize_benchmark_notes(notes: list[dict[str, Any]]) -> dict[str, Any]:
    if not notes:
        return {"sample_count": 0}

    types = Counter(n.get("note_type") or "normal" for n in notes)
    video_count = sum(v for k, v in types.items() if "video" in str(k).lower())
    image_count = len(notes) - video_count

    sorted_by_likes = sorted(notes, key=lambda n: n.get("liked_count", 0), reverse=True)
    top3 = sorted_by_likes[:3]
    bottom3 = sorted_by_likes[-3:] if len(notes) >= 3 else []

    avg_likes = sum(n.get("liked_count", 0) for n in notes) / len(notes)
    video_notes = [n for n in notes if "video" in str(n.get("note_type", "")).lower()]
    image_notes = [n for n in notes if n not in video_notes]
    avg_video_likes = (
        sum(n.get("liked_count", 0) for n in video_notes) / len(video_notes) if video_notes else 0
    )
    avg_image_likes = (
        sum(n.get("liked_count", 0) for n in image_notes) / len(image_notes) if image_notes else 0
    )

    better_format = "视频" if avg_video_likes > avg_image_likes else "图文"

    return {
        "sample_count": len(notes),
        "video_ratio": round(video_count / len(notes) * 100, 1),
        "image_ratio": round(image_count / len(notes) * 100, 1),
        "avg_likes": round(avg_likes, 1),
        "avg_video_likes": round(avg_video_likes, 1),
        "avg_image_likes": round(avg_image_likes, 1),
        "better_format": better_format,
        "top_notes": [
            {
                "title": n.get("title"),
                "likes": n.get("liked_count"),
                "type": n.get("note_type"),
            }
            for n in top3
        ],
        "low_notes": [
            {"title": n.get("title"), "likes": n.get("liked_count")}
            for n in bottom3
        ],
    }


def build_strategy_context(
    style_profile: dict[str, Any],
    notes_summary: dict[str, Any],
    post_number: Optional[int] = None,
) -> str:
    lines: list[str] = []
    if post_number is not None:
        phase = get_post_phase(post_number)
        lines.extend([
            f"用户即将发布：第 {post_number} 篇帖子",
            f"运营阶段：{phase['phase']}",
            f"阶段目标：{phase['goal']}",
            f"内容侧重：{phase['content_focus']}",
            f"阶段风险：{phase['risk']}",
            "",
        ])
    else:
        lines.extend([
            "用户未说明发帖序号（可选项，无需主动追问）。",
            "策略重点结合对标数据与用户描述的主题、角度、卖点来制定。",
            "",
        ])

    lines.extend([
        "对标账号风格摘要：",
        style_profile.get("summary", ""),
        "",
        "对标账号笔记数据洞察：",
        json.dumps(notes_summary, ensure_ascii=False, indent=2),
    ])
    if style_profile.get("top_performing_notes"):
        lines.append("\n对标高赞笔记样本：")
        for n in style_profile["top_performing_notes"][:5]:
            lines.append(f"- 《{n.get('title')}》点赞 {n.get('liked_count', 0)}")

    return "\n".join(lines)
