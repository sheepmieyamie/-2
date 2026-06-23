from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BenchmarkAccount, BenchmarkNote, ChatMessage, ChatSession, ContentPreset, ReferencePost
from app.services.ai_writer import ai_writer, sanitize_output
from app.services.analyzer import (
    analyze_account_style,
    analyze_reference_post,
    extract_note_detail,
    extract_notes_list,
    extract_user_profile,
    reference_post_to_context,
    style_profile_to_prompt,
)
from app.services.forbidden_words import forbidden_checker
from app.services.strategy import (
    build_strategy_context,
    detect_finalize_intent,
    extract_post_number,
    extract_post_number_from_messages,
    get_post_phase,
    is_full_plan_reply,
    summarize_benchmark_notes,
)
from app.services.tikhub import tikhub_client
from app.tenant import (
    get_owned_account,
    get_owned_preset,
    get_owned_reference_post,
    owned_accounts,
    owned_presets,
    owned_reference_posts,
    require_client_id,
    verify_chat_selection,
    verify_chat_session,
)

router = APIRouter(prefix="/api", tags=["api"])


def get_client_id(x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id")) -> str:
    cid = (x_client_id or "anonymous").strip()[:64]
    return cid or "anonymous"


def _ensure_chat_session(db: Session, session_id: str, client_id: str) -> None:
    meta = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if meta:
        if meta.client_id and meta.client_id != client_id:
            raise HTTPException(404, "对话不存在")
        meta.client_id = client_id
        meta.updated_at = datetime.utcnow()
    else:
        db.add(ChatSession(session_id=session_id, client_id=client_id))


def _assert_session_writable(db: Session, session_id: str, client_id: str) -> None:
    foreign_msg = (
        db.query(ChatMessage.id)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.client_id != "",
            ChatMessage.client_id != client_id,
        )
        .first()
    )
    if foreign_msg:
        raise HTTPException(404, "对话不存在")
    meta = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if meta and meta.client_id and meta.client_id != client_id:
        raise HTTPException(404, "对话不存在")


def normalize_share_text(text: str) -> str:
    text = text.strip()
    for pattern in (
        r"https?://xhslink\.com/[^\s\u4e00-\u9fff]+",
        r"https?://www\.xiaohongshu\.com/[^\s\u4e00-\u9fff]+",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(0).rstrip("，。,.;；)")
    return text


async def _enrich_notes_with_details(notes: list[dict]) -> list[dict]:
    """列表接口正文常被截断，补拉详情以获取完整文案与话题标签。"""
    sem = asyncio.Semaphore(5)

    async def enrich_one(note: dict) -> dict:
        merged = dict(note)
        content = merged.get("content") or ""
        tags = merged.get("tags") or []
        if len(content) >= 150 and tags:
            return merged
        note_id = merged.get("note_id")
        if not note_id:
            return merged
        async with sem:
            try:
                raw = await tikhub_client.get_note_detail(
                    note_id=note_id,
                    note_type=merged.get("note_type", "normal"),
                )
                detail = extract_note_detail(raw)
                if detail.get("content"):
                    merged["content"] = detail["content"]
                if detail.get("tags"):
                    merged["tags"] = detail["tags"]
            except (ValueError, RuntimeError):
                pass
        return merged

    return list(await asyncio.gather(*[enrich_one(n) for n in notes]))


def preset_to_context(preset: ContentPreset) -> str:
    lines = [f"档案名称：{preset.name}"]
    if preset.product_desc:
        lines.append(f"产品/服务：{preset.product_desc}")
    if preset.audience_desc:
        lines.append(f"目标人群：{preset.audience_desc}")
    if preset.extra_notes:
        lines.append(f"补充说明：{preset.extra_notes}")
    return "\n".join(lines)


def _preset_dict(p: ContentPreset) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "product_desc": p.product_desc,
        "audience_desc": p.audience_desc,
        "extra_notes": p.extra_notes,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


class AddAccountRequest(BaseModel):
    user_id: str = ""
    share_text: str = ""
    note_limit: int = Field(default=50, ge=5, le=100)


def _load_strategy_context(
    db: Session, client_id: str, account_id: int, post_number: Optional[int] = None
) -> tuple[str, dict, dict]:
    account = get_owned_account(db, client_id, account_id)

    style = json.loads(account.style_profile or "{}")
    db_notes = db.query(BenchmarkNote).filter(BenchmarkNote.account_id == account_id).all()
    notes = [
        {
            "title": n.title,
            "note_type": n.note_type,
            "liked_count": n.liked_count,
            "collected_count": n.collected_count,
            "comment_count": n.comment_count,
        }
        for n in db_notes
    ]
    notes_summary = summarize_benchmark_notes(notes)
    strategy_text = build_strategy_context(style, notes_summary, post_number)
    return strategy_text, style, notes_summary


def _require_analysis_source(
    account_ids: list[int], reference_post_ids: list[int]
) -> None:
    if not account_ids and not reference_post_ids:
        raise HTTPException(400, "请至少选择对标账号或参考帖子之一")


def _resolve_chat_selection(req: "ChatRequest") -> tuple[list[int], list[int]]:
    account_ids = list(
        dict.fromkeys(
            (req.account_ids or [])
            + ([req.account_id] if req.account_id else [])
        )
    )
    reference_post_ids = list(
        dict.fromkeys(
            (req.reference_post_ids or [])
            + ([req.reference_post_id] if req.reference_post_id else [])
        )
    )
    return account_ids, reference_post_ids


def _load_reference_context(db: Session, client_id: str, reference_post_id: int) -> tuple[str, dict]:
    post = get_owned_reference_post(db, client_id, reference_post_id)
    style = json.loads(post.style_analysis or "{}")
    tags = json.loads(post.tags or "[]")
    context = reference_post_to_context(
        post.title,
        post.content,
        post.author_nickname,
        tags,
        style,
        liked_count=post.liked_count,
        collected_count=post.collected_count,
        comment_count=post.comment_count,
    )
    return context, style


def _reference_post_dict(post: ReferencePost) -> dict:
    return {
        "id": post.id,
        "note_id": post.note_id,
        "title": post.title,
        "content_preview": (post.content or "")[:120],
        "note_type": post.note_type,
        "liked_count": post.liked_count,
        "collected_count": post.collected_count,
        "comment_count": post.comment_count,
        "tags": json.loads(post.tags or "[]"),
        "author_nickname": post.author_nickname,
        "style_summary": json.loads(post.style_analysis or "{}").get("summary", ""),
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }


def _assemble_generation_context(
    db: Session,
    *,
    client_id: str,
    account_ids: list[int],
    reference_post_ids: list[int],
    post_number: Optional[int],
) -> dict:
    style_entries: list[dict] = []
    strategy_parts: list[str] = []
    reference_parts: list[str] = []
    notes_summaries: list[dict] = []

    for aid in account_ids:
        account = get_owned_account(db, client_id, aid)
        strategy_text, style, notes_summary = _load_strategy_context(
            db, client_id, aid, post_number
        )
        nickname = account.nickname or account.user_id
        strategy_parts.append(f"### 对标账号：{nickname}\n{strategy_text}")
        style_entries.append({"nickname": nickname, "style_profile": style})
        notes_summaries.append(
            {"account_id": aid, "nickname": nickname, **notes_summary}
        )

    for rid in reference_post_ids:
        post = get_owned_reference_post(db, client_id, rid)
        ref_ctx, ref_style = _load_reference_context(db, client_id, rid)
        reference_parts.append(ref_ctx)
        style_entries.append(
            {
                "title": post.title,
                "type": "reference_post",
                "style_profile": ref_style,
            }
        )

    if account_ids:
        strategy_context = "\n\n".join(strategy_parts)
    elif reference_post_ids:
        strategy_context = (
            "当前仅选择参考帖子，无对标账号级数据；请综合多篇参考帖的"
            "标题结构、语气、分段与话题标签制定策略。"
        )
    else:
        strategy_context = ""

    if account_ids:
        style_profile = json.dumps(
            {"selected_accounts": style_entries[: len(account_ids)]},
            ensure_ascii=False,
            indent=2,
        )
    elif reference_post_ids:
        ref_styles = [e for e in style_entries if e.get("type") == "reference_post"]
        style_profile = json.dumps(
            {"selected_reference_posts": ref_styles},
            ensure_ascii=False,
            indent=2,
        )
    else:
        style_profile = ""

    reference_context = "\n\n---\n\n".join(reference_parts) if reference_parts else ""

    if len(notes_summaries) == 1:
        notes_summary = notes_summaries[0]
    elif notes_summaries:
        notes_summary = {"accounts": notes_summaries}
    else:
        notes_summary = {}

    return {
        "style_profile": style_profile,
        "strategy_context": strategy_context,
        "reference_context": reference_context,
        "notes_summary": notes_summary,
    }


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    account_id: Optional[int] = None
    reference_post_id: Optional[int] = None
    account_ids: list[int] = Field(default_factory=list)
    reference_post_ids: list[int] = Field(default_factory=list)
    preset_id: Optional[int] = None
    post_number: Optional[int] = Field(default=None, ge=1, le=9999)
    mode: str = Field(default="plan", pattern="^(plan|copy)$")


class AdviceRequest(BaseModel):
    post_number: int = Field(..., ge=1, le=9999)
    account_id: int
    preset_id: Optional[int] = None
    extra_requirement: str = ""


class PresetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    product_desc: str = ""
    audience_desc: str = ""
    extra_notes: str = ""


class AddReferencePostRequest(BaseModel):
    share_text: str = Field(..., min_length=1)


class CheckTextRequest(BaseModel):
    text: str


@router.get("/health")
async def health():
    return {"status": "ok"}


def _effective_note_count(profile_count: int, imported: int) -> int:
    """主页笔记数优先用接口字段，缺失时用已抓取数量兜底。"""
    return max(profile_count, imported)


@router.get("/accounts")
def list_accounts(
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    accounts = owned_accounts(db, cid).order_by(BenchmarkAccount.updated_at.desc()).all()
    imported_map = dict(
        db.query(BenchmarkNote.account_id, func.count(BenchmarkNote.id))
        .group_by(BenchmarkNote.account_id)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "nickname": a.nickname,
            "avatar": a.avatar,
            "bio": a.bio,
            "follower_count": a.follower_count,
            "note_count": _effective_note_count(a.note_count, imported_map.get(a.id, 0)),
            "style_summary": json.loads(a.style_profile or "{}").get("summary", ""),
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        }
        for a in accounts
    ]


@router.get("/accounts/{account_id}")
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    account = get_owned_account(db, require_client_id(client_id), account_id)

    notes = (
        db.query(BenchmarkNote)
        .filter(BenchmarkNote.account_id == account_id)
        .order_by(BenchmarkNote.liked_count.desc())
        .limit(20)
        .all()
    )
    imported_total = (
        db.query(func.count(BenchmarkNote.id))
        .filter(BenchmarkNote.account_id == account_id)
        .scalar()
        or 0
    )

    return {
        "id": account.id,
        "user_id": account.user_id,
        "nickname": account.nickname,
        "avatar": account.avatar,
        "bio": account.bio,
        "follower_count": account.follower_count,
        "note_count": _effective_note_count(account.note_count, imported_total),
        "style_profile": json.loads(account.style_profile or "{}"),
        "notes": [
            {
                "note_id": n.note_id,
                "title": n.title,
                "content": n.content,
                "liked_count": n.liked_count,
                "collected_count": n.collected_count,
                "tags": json.loads(n.tags or "[]"),
            }
            for n in notes
        ],
    }


@router.post("/accounts/{account_id}/refresh-style")
async def refresh_account_style(
    account_id: int,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    account = get_owned_account(db, require_client_id(client_id), account_id)

    db_notes = (
        db.query(BenchmarkNote)
        .filter(BenchmarkNote.account_id == account_id)
        .all()
    )
    if not db_notes:
        raise HTTPException(400, "该账号暂无笔记，请重新抓取")

    note_dicts = [
        {
            "note_id": n.note_id,
            "title": n.title,
            "content": n.content,
            "note_type": n.note_type,
            "liked_count": n.liked_count,
            "collected_count": n.collected_count,
            "comment_count": n.comment_count,
            "tags": json.loads(n.tags or "[]"),
        }
        for n in db_notes
    ]
    enriched = await _enrich_notes_with_details(note_dicts)
    by_id = {n.note_id: n for n in db_notes}

    for item in enriched:
        row = by_id.get(item["note_id"])
        if not row:
            continue
        row.content = item.get("content") or row.content
        row.tags = json.dumps(item.get("tags") or [], ensure_ascii=False)

    profile = {
        "user_id": account.user_id,
        "nickname": account.nickname,
    }
    style = analyze_account_style(enriched, profile)
    account.style_profile = json.dumps(style, ensure_ascii=False)
    account.updated_at = datetime.utcnow()
    db.commit()

    return {
        "id": account.id,
        "nickname": account.nickname,
        "style_profile": style,
        "notes_refreshed": len(enriched),
    }


@router.post("/accounts")
async def add_account(
    req: AddAccountRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    if not req.user_id and not req.share_text:
        raise HTTPException(400, "请提供 user_id 或 share_text（小红书分享链接）")

    share_text = normalize_share_text(req.share_text) if req.share_text else ""

    try:
        user_raw = await tikhub_client.get_user_info(
            user_id=req.user_id, share_text=share_text
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc

    profile = extract_user_profile(user_raw)
    if not profile["user_id"]:
        raise HTTPException(
            400,
            "无法解析用户信息。请粘贴小红书【主页】分享链接（xhslink.com），不要贴单条笔记链接",
        )

    all_notes: list[dict] = []
    cursor = ""
    has_more = True
    try:
        while len(all_notes) < req.note_limit and has_more:
            notes_raw = await tikhub_client.get_user_posted_notes(
                user_id=profile["user_id"], cursor=cursor
            )
            batch = extract_notes_list(notes_raw)
            if not batch:
                break
            all_notes.extend(batch)
            page_data = notes_raw.get("data", notes_raw) if isinstance(notes_raw, dict) else {}
            has_more = bool(page_data.get("has_more")) if isinstance(page_data, dict) else False
            cursor = batch[-1].get("cursor") or batch[-1].get("note_id") or ""
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc

    all_notes = all_notes[: req.note_limit]
    all_notes = await _enrich_notes_with_details(all_notes)
    profile["note_count"] = _effective_note_count(profile["note_count"], len(all_notes))
    style = analyze_account_style(all_notes, profile)

    account = (
        owned_accounts(db, cid)
        .filter(BenchmarkAccount.user_id == profile["user_id"])
        .first()
    )

    if account:
        account.nickname = profile["nickname"]
        account.avatar = profile["avatar"]
        account.bio = profile["bio"]
        account.follower_count = profile["follower_count"]
        account.note_count = profile["note_count"]
        account.style_profile = json.dumps(style, ensure_ascii=False)
        account.client_id = cid
        account.updated_at = datetime.utcnow()
        db.query(BenchmarkNote).filter(BenchmarkNote.account_id == account.id).delete()
    else:
        account = BenchmarkAccount(
            user_id=profile["user_id"],
            nickname=profile["nickname"],
            avatar=profile["avatar"],
            bio=profile["bio"],
            follower_count=profile["follower_count"],
            note_count=profile["note_count"],
            share_text=share_text or req.share_text,
            style_profile=json.dumps(style, ensure_ascii=False),
            client_id=cid,
        )
        db.add(account)
        db.flush()

    for note in all_notes:
        db.add(
            BenchmarkNote(
                account_id=account.id,
                note_id=note["note_id"],
                title=note["title"],
                content=note["content"],
                note_type=note.get("note_type", "normal"),
                liked_count=note.get("liked_count", 0),
                collected_count=note.get("collected_count", 0),
                comment_count=note.get("comment_count", 0),
                tags=json.dumps(note.get("tags", []), ensure_ascii=False),
                raw_data=json.dumps(note.get("raw", {}), ensure_ascii=False),
            )
        )

    db.commit()
    db.refresh(account)

    return {
        "id": account.id,
        "nickname": account.nickname,
        "style_profile": style,
        "notes_imported": len(all_notes),
    }


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    account = get_owned_account(db, require_client_id(client_id), account_id)
    db.delete(account)
    db.commit()
    return {"ok": True}


@router.get("/presets")
def list_presets(
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    presets = owned_presets(db, require_client_id(client_id)).order_by(ContentPreset.updated_at.desc()).all()
    return [_preset_dict(p) for p in presets]


@router.post("/presets")
def create_preset(
    req: PresetRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    preset = ContentPreset(
        name=req.name.strip(),
        product_desc=req.product_desc.strip(),
        audience_desc=req.audience_desc.strip(),
        extra_notes=req.extra_notes.strip(),
        client_id=require_client_id(client_id),
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return _preset_dict(preset)


@router.put("/presets/{preset_id}")
def update_preset(
    preset_id: int,
    req: PresetRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    preset = get_owned_preset(db, require_client_id(client_id), preset_id)
    preset.name = req.name.strip()
    preset.product_desc = req.product_desc.strip()
    preset.audience_desc = req.audience_desc.strip()
    preset.extra_notes = req.extra_notes.strip()
    preset.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(preset)
    return _preset_dict(preset)


@router.delete("/presets/{preset_id}")
def delete_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    preset = get_owned_preset(db, require_client_id(client_id), preset_id)
    db.delete(preset)
    db.commit()
    return {"ok": True}


@router.get("/reference-posts")
def list_reference_posts(
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    posts = (
        owned_reference_posts(db, require_client_id(client_id))
        .order_by(ReferencePost.updated_at.desc())
        .all()
    )
    return [_reference_post_dict(p) for p in posts]


@router.get("/reference-posts/{post_id}")
def get_reference_post(
    post_id: int,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    post = get_owned_reference_post(db, require_client_id(client_id), post_id)
    data = _reference_post_dict(post)
    data["content"] = post.content
    data["style_analysis"] = json.loads(post.style_analysis or "{}")
    return data


@router.post("/reference-posts")
async def add_reference_post(
    req: AddReferencePostRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    share_text = normalize_share_text(req.share_text)
    if not share_text:
        raise HTTPException(400, "请粘贴小红书笔记分享链接")

    try:
        raw = await tikhub_client.get_note_detail(share_text=share_text)
        note = extract_note_detail(raw)
        if not note.get("note_id"):
            raw = await tikhub_client.get_note_detail(
                share_text=share_text, note_type="video"
            )
            note = extract_note_detail(raw)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc

    if not note.get("note_id"):
        raise HTTPException(
            400,
            "无法解析笔记信息。请粘贴小红书【单条笔记】分享链接，不要贴主页链接",
        )

    style = analyze_reference_post(note)
    existing = (
        owned_reference_posts(db, cid)
        .filter(ReferencePost.note_id == note["note_id"])
        .first()
    )

    if existing:
        existing.share_text = share_text
        existing.title = note["title"]
        existing.content = note["content"]
        existing.note_type = note.get("note_type", "normal")
        existing.liked_count = note.get("liked_count", 0)
        existing.collected_count = note.get("collected_count", 0)
        existing.comment_count = note.get("comment_count", 0)
        existing.tags = json.dumps(note.get("tags", []), ensure_ascii=False)
        existing.author_nickname = note.get("author_nickname", "")
        existing.style_analysis = json.dumps(style, ensure_ascii=False)
        existing.client_id = cid
        existing.updated_at = datetime.utcnow()
        post = existing
    else:
        post = ReferencePost(
            note_id=note["note_id"],
            share_text=share_text,
            title=note["title"],
            content=note["content"],
            note_type=note.get("note_type", "normal"),
            liked_count=note.get("liked_count", 0),
            collected_count=note.get("collected_count", 0),
            comment_count=note.get("comment_count", 0),
            tags=json.dumps(note.get("tags", []), ensure_ascii=False),
            author_nickname=note.get("author_nickname", ""),
            style_analysis=json.dumps(style, ensure_ascii=False),
            client_id=cid,
        )
        db.add(post)

    db.commit()
    db.refresh(post)
    return _reference_post_dict(post)


@router.delete("/reference-posts/{post_id}")
def delete_reference_post(
    post_id: int,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    post = get_owned_reference_post(db, require_client_id(client_id), post_id)
    db.delete(post)
    db.commit()
    return {"ok": True}


@router.post("/advice")
async def get_advice(
    req: AdviceRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    strategy_context, style, notes_summary = _load_strategy_context(
        db, cid, req.account_id, req.post_number
    )
    product_context = ""
    if req.preset_id:
        preset = get_owned_preset(db, cid, req.preset_id)
        product_context = preset_to_context(preset)

    reply = await ai_writer.generate_advice(
        strategy_context=strategy_context,
        product_context=product_context,
        extra_requirement=req.extra_requirement,
    )

    phase = get_post_phase(req.post_number)
    return {
        "post_number": req.post_number,
        "phase": phase,
        "notes_summary": notes_summary,
        "advice": reply,
    }


@router.post("/chat")
async def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    try:
        return await _handle_chat(req, db, client_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "生成失败，请稍后重试") from exc


async def _handle_chat(
    req: ChatRequest,
    db: Session,
    client_id: str,
):
    cid = require_client_id(client_id)
    account_ids, reference_post_ids = _resolve_chat_selection(req)
    _require_analysis_source(account_ids, reference_post_ids)
    verify_chat_selection(db, cid, account_ids, reference_post_ids)
    primary_account_id = account_ids[0] if account_ids else None

    session_id = req.session_id or str(uuid.uuid4())
    _assert_session_writable(db, session_id, cid)
    _ensure_chat_session(db, session_id, cid)
    product_context = ""

    if req.preset_id:
        preset = get_owned_preset(db, cid, req.preset_id)
        product_context = preset_to_context(preset)

    post_number = req.post_number or extract_post_number(req.message)
    parsed_from_message = post_number is not None

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.client_id == cid)
        .order_by(ChatMessage.created_at.asc())
        .limit(20)
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": req.message})

    if req.mode == "plan":
        post_number = req.post_number or extract_post_number_from_messages(messages)
        parsed_from_message = post_number is not None

        ctx = _assemble_generation_context(
            db,
            client_id=cid,
            account_ids=account_ids,
            reference_post_ids=reference_post_ids,
            post_number=post_number,
        )
        finalize = detect_finalize_intent(req.message)

        reply = sanitize_output(
            await ai_writer.generate_plan_consult(
                messages,
                style_profile=ctx["style_profile"],
                strategy_context=ctx["strategy_context"],
                product_context=product_context,
                reference_context=ctx["reference_context"],
                finalize=finalize,
            )
        )
        phase = get_post_phase(post_number) if post_number else None
        stage = "final" if finalize or is_full_plan_reply(reply) else "consult"

        db.add(ChatMessage(session_id=session_id, role="user", content=req.message, account_id=primary_account_id, client_id=cid))
        db.add(ChatMessage(session_id=session_id, role="assistant", content=reply, account_id=primary_account_id, client_id=cid))
        db.commit()

        report = forbidden_checker.check_report(reply)
        if stage == "final":
            if post_number and phase:
                risk_level = f"运营方案 · 第{post_number}篇 · {phase['phase']}"
            else:
                risk_level = "运营方案"
        else:
            risk_level = "策略咨询"

        return {
            "session_id": session_id,
            "reply": reply,
            "mode": "plan",
            "stage": stage,
            "post_number": post_number,
            "phase": phase,
            "notes_summary": ctx["notes_summary"],
            "compliance_report": report,
            "compliance": report["compliance"],
            "risk_level": risk_level,
        }

    ctx = _assemble_generation_context(
        db,
        client_id=cid,
        account_ids=account_ids,
        reference_post_ids=reference_post_ids,
        post_number=post_number if parsed_from_message else None,
    )

    reply = sanitize_output(
        await ai_writer.generate(
            messages,
            style_profile=ctx["style_profile"],
            product_context=product_context,
            strategy_context=ctx["strategy_context"],
            reference_context=ctx["reference_context"],
        )
    )

    db.add(ChatMessage(session_id=session_id, role="user", content=req.message, account_id=primary_account_id, client_id=cid))
    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply, account_id=primary_account_id, client_id=cid))
    db.commit()

    report = forbidden_checker.check_report(reply)

    return {
        "session_id": session_id,
        "reply": reply,
        "mode": "copy",
        "post_number": post_number if parsed_from_message else None,
        "compliance_report": report,
        "compliance": report["compliance"],
        "risk_level": report["risk_level"],
    }


def _session_title(text: str, max_len: int = 36) -> str:
    text = " ".join(text.split())
    if not text:
        return "空对话"
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _resolve_session_title(
    db: Session, session_id: str, fallback_text: str = ""
) -> str:
    meta = (
        db.query(ChatSession)
        .filter(ChatSession.session_id == session_id)
        .first()
    )
    if meta and meta.title.strip():
        return meta.title.strip()
    return _session_title(fallback_text)


class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)


@router.get("/chat/sessions")
def list_chat_sessions(
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
    limit: int = 50,
):
    cid = require_client_id(client_id)
    rows = (
        db.query(
            ChatMessage.session_id,
            func.max(ChatMessage.created_at).label("updated_at"),
            func.count(ChatMessage.id).label("message_count"),
        )
        .filter(ChatMessage.client_id == cid)
        .group_by(ChatMessage.session_id)
        .order_by(func.max(ChatMessage.created_at).desc())
        .limit(min(limit, 100))
        .all()
    )

    sessions = []
    for row in rows:
        first_user = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == row.session_id,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at.asc())
            .first()
        )
        account_id = first_user.account_id if first_user else None
        account_name = ""
        if account_id:
            account = (
                owned_accounts(db, cid)
                .filter(BenchmarkAccount.id == account_id)
                .first()
            )
            account_name = account.nickname if account else ""

        sessions.append(
            {
                "session_id": row.session_id,
                "title": _resolve_session_title(
                    db, row.session_id, first_user.content if first_user else ""
                ),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "message_count": row.message_count,
                "account_id": account_id,
                "account_name": account_name,
            }
        )
    return sessions


@router.get("/chat/sessions/{session_id}")
def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    verify_chat_session(db, cid, session_id)
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.client_id == cid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    if not messages:
        raise HTTPException(404, "对话不存在")

    account_id = next((m.account_id for m in messages if m.account_id), None)
    first_user = next((m for m in messages if m.role == "user"), None)
    return {
        "session_id": session_id,
        "title": _resolve_session_title(
            db, session_id, first_user.content if first_user else ""
        ),
        "account_id": account_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.patch("/chat/sessions/{session_id}")
def rename_chat_session(
    session_id: str,
    req: RenameSessionRequest,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    verify_chat_session(db, cid, session_id)
    exists = (
        db.query(ChatMessage.id)
        .filter(ChatMessage.session_id == session_id, ChatMessage.client_id == cid)
        .first()
    )
    if not exists:
        raise HTTPException(404, "对话不存在")

    title = req.title.strip()
    if not title:
        raise HTTPException(400, "标题不能为空")

    meta = (
        db.query(ChatSession)
        .filter(ChatSession.session_id == session_id)
        .first()
    )
    if meta:
        if meta.client_id and meta.client_id != cid:
            raise HTTPException(404, "对话不存在")
        meta.title = title
        meta.client_id = cid
        meta.updated_at = datetime.utcnow()
    else:
        db.add(ChatSession(session_id=session_id, title=title, client_id=cid))
    db.commit()

    return {"session_id": session_id, "title": title}


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    client_id: str = Depends(get_client_id),
):
    cid = require_client_id(client_id)
    verify_chat_session(db, cid, session_id)
    deleted = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.client_id == cid)
        .delete(synchronize_session=False)
    )
    if not deleted:
        raise HTTPException(404, "对话不存在")
    db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.client_id == cid,
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.post("/check-forbidden")
def check_forbidden(req: CheckTextRequest):
    report = forbidden_checker.check_report(req.text)
    return {
        **report,
        "report_text": forbidden_checker.format_report_text(report),
    }


@router.get("/forbidden-words")
def list_forbidden_words():
    forbidden_checker.reload()
    return {
        "forbidden": forbidden_checker.forbidden_words,
        "limit": forbidden_checker.limit_words,
        "count": len(forbidden_checker.forbidden_words) + len(forbidden_checker.limit_words),
    }


@router.post("/forbidden-words/reload")
def reload_forbidden_words():
    forbidden_checker.reload()
    return {
        "forbidden_count": len(forbidden_checker.forbidden_words),
        "limit_count": len(forbidden_checker.limit_words),
    }
