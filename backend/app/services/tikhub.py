from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings


class TikHubClient:
    def __init__(self) -> None:
        self.base_url = settings.tikhub_base_url.rstrip("/")
        self.token = settings.tikhub_api_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise ValueError("未配置 TIKHUB_API_TOKEN，请在 backend/.env 中设置")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}{path}",
                    params=params or {},
                    headers=self._headers(),
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:200]
                if status == 402:
                    raise RuntimeError("TikHub 账户余额不足，请登录 tikhub.io 充值后重试") from exc
                if status == 400:
                    raise RuntimeError(
                        "链接无效或已过期。请从小红书 App 重新复制【主页】分享链接（xhslink.com 格式）"
                    ) from exc
                    raise RuntimeError("TikHub API Token 无效，请检查 backend/.env 中的 TIKHUB_API_TOKEN") from exc
                raise RuntimeError(f"TikHub 请求失败 (HTTP {status}): {body}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"TikHub 网络请求失败: {exc}") from exc

            payload = response.json()

        if payload.get("code") not in (200, None):
            raise RuntimeError(payload.get("message_zh") or payload.get("message") or "TikHub 请求失败")

        data = payload.get("data")
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {"raw": data}
        return data or {}

    async def get_user_info(
        self, *, user_id: str = "", share_text: str = ""
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if user_id:
            params["user_id"] = user_id
        if share_text:
            params["share_text"] = share_text
        return await self._get("/api/v1/xiaohongshu/app_v2/get_user_info", params)

    async def get_user_posted_notes(
        self, *, user_id: str = "", share_text: str = "", cursor: str = ""
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if user_id:
            params["user_id"] = user_id
        if share_text:
            params["share_text"] = share_text
        if cursor:
            params["cursor"] = cursor
        return await self._get("/api/v1/xiaohongshu/app_v2/get_user_posted_notes", params)

    async def get_note_detail(
        self, *, note_id: str = "", share_text: str = "", note_type: str = "normal"
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if note_id:
            params["note_id"] = note_id
        if share_text:
            params["share_text"] = share_text

        is_video = note_type in ("video", "video_note")
        path = (
            "/api/v1/xiaohongshu/app_v2/get_video_note_detail"
            if is_video
            else "/api/v1/xiaohongshu/app_v2/get_image_note_detail"
        )
        return await self._get(path, params)

    async def search_notes(self, keyword: str, page: int = 1) -> dict[str, Any]:
        return await self._get(
            "/api/v1/xiaohongshu/app_v2/search_notes",
            {"keyword": keyword, "page": str(page)},
        )


tikhub_client = TikHubClient()
