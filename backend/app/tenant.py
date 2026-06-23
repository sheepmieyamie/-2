from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from app.models import BenchmarkAccount, ChatMessage, ChatSession, ContentPreset, ReferencePost


def require_client_id(client_id: str) -> str:
    cid = (client_id or "").strip()
    if not cid or cid == "anonymous":
        raise HTTPException(401, "客户端标识无效，请刷新页面后重试")
    return cid


def owned_accounts(db: Session, client_id: str) -> Query:
    return db.query(BenchmarkAccount).filter(BenchmarkAccount.client_id == client_id)


def owned_presets(db: Session, client_id: str) -> Query:
    return db.query(ContentPreset).filter(ContentPreset.client_id == client_id)


def owned_reference_posts(db: Session, client_id: str) -> Query:
    return db.query(ReferencePost).filter(ReferencePost.client_id == client_id)


def get_owned_account(db: Session, client_id: str, account_id: int) -> BenchmarkAccount:
    account = owned_accounts(db, client_id).filter(BenchmarkAccount.id == account_id).first()
    if not account:
        raise HTTPException(404, "账号不存在")
    return account


def get_owned_preset(db: Session, client_id: str, preset_id: int) -> ContentPreset:
    preset = owned_presets(db, client_id).filter(ContentPreset.id == preset_id).first()
    if not preset:
        raise HTTPException(404, "档案不存在")
    return preset


def get_owned_reference_post(db: Session, client_id: str, post_id: int) -> ReferencePost:
    post = owned_reference_posts(db, client_id).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(404, "参考帖子不存在")
    return post


def verify_chat_selection(
    db: Session,
    client_id: str,
    account_ids: list[int],
    reference_post_ids: list[int],
) -> None:
    for aid in account_ids:
        get_owned_account(db, client_id, aid)
    for pid in reference_post_ids:
        get_owned_reference_post(db, client_id, pid)


def verify_chat_session(db: Session, client_id: str, session_id: str) -> None:
    owned = (
        db.query(ChatMessage.id)
        .filter(ChatMessage.session_id == session_id, ChatMessage.client_id == client_id)
        .first()
    )
    if owned:
        return
    meta = (
        db.query(ChatSession)
        .filter(ChatSession.session_id == session_id, ChatSession.client_id == client_id)
        .first()
    )
    if not meta:
        raise HTTPException(404, "对话不存在")
