"""
Wrapper around MAX Bot API.
Base URL: https://platform-api.max.ru
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

import httpx

from app.config import config

logger = logging.getLogger(__name__)

BASE_URL = config.max_api_base
TOKEN = config.max_token


def _headers() -> dict[str, str]:
    return {
        "Authorization": TOKEN,
        "Content-Type": "application/json",
    }


class MaxApiError(Exception):
    """Raised when MAX API returns a non-success status."""

    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        super().__init__(f"MAX API error {status}: {body}")


async def get_me() -> dict[str, Any]:
    """GET /me — get bot info."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/me", headers=_headers())
        if resp.status_code != 200:
            raise MaxApiError(resp.status_code, resp.text)
        return resp.json()


async def send_message(
    text: str,
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    attachments: list[dict[str, Any]] | None = None,
    disable_link_preview: bool = False,
    format_: str | None = None,
) -> dict[str, Any]:
    """
    POST /messages — send a message to a user or chat.
    Either user_id or chat_id must be provided (not both).
    """
    if user_id is None and chat_id is None:
        raise ValueError("Either user_id or chat_id must be specified")

    params: dict[str, Any] = {}
    if user_id is not None:
        params["user_id"] = user_id
    if chat_id is not None:
        params["chat_id"] = chat_id
    if disable_link_preview:
        params["disable_link_preview"] = True

    body: dict[str, Any] = {"text": text}
    if attachments:
        body["attachments"] = attachments
    if format_ is not None:
        body["format"] = format_

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/messages",
            params=params,
            headers=_headers(),
            json=body,
        )
        if resp.status_code != 200:
            raise MaxApiError(resp.status_code, resp.text)
        return resp.json()


async def get_updates(last_event_id: int | None = None) -> list[dict[str, Any]]:
    """GET /updates — long polling. For dev/testing only."""
    params: dict[str, str] = {}
    if last_event_id is not None:
        params["last_event_id"] = str(last_event_id)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/updates", headers=_headers(), params=params
        )
        if resp.status_code != 200:
            raise MaxApiError(resp.status_code, resp.text)
        return resp.json()


async def set_webhook_subscription(
    url: str, update_types: list[str], *, secret: str = ""
) -> dict[str, Any]:
    """
    POST /subscriptions — subscribe to events via webhook.
    """
    body: dict[str, Any] = {
        "url": url,
        "update_types": update_types,
    }
    if secret:
        body["secret"] = secret

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/subscriptions",
            headers=_headers(),
            json=body,
        )
        if resp.status_code not in (200, 201):
            raise MaxApiError(resp.status_code, resp.text)
        return resp.json()


async def delete_webhook_subscription() -> dict[str, Any]:
    """DELETE /subscriptions — unsubscribe from webhook events."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{BASE_URL}/subscriptions", headers=_headers()
        )
        if resp.status_code not in (200, 204):
            raise MaxApiError(resp.status_code, resp.text)
        return {"success": True}


async def answer_callback(
    callback_id: str, text: str | None = None
) -> dict[str, Any]:
    """
    POST /answers — respond to a message_callback event.
    """
    body: dict[str, Any] = {"callback_id": callback_id}
    if text is not None:
        body["text"] = text

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/answers",
            headers=_headers(),
            json=body,
        )
        if resp.status_code != 200:
            raise MaxApiError(resp.status_code, resp.text)
        return resp.json()


def verify_webhook_secret(secret_header: str | None) -> bool:
    """
    Verify the X-Max-Bot-Api-Secret header against our configured secret.
    """
    if not config.webhook_secret:
        return True  # no secret configured → skip check
    if secret_header is None:
        return False
    return hmac.compare_digest(secret_header, config.webhook_secret)


def verify_contact_hash(vcf_info: str, hash_value: str) -> bool:
    """
    Verify that a contact hash matches HMAC-SHA256(access_token, vcf_info).
    Used with request_contact button.
    """
    computed = hmac.digest(
        key=TOKEN.encode(),
        msg=vcf_info.encode(),
        digest="sha256",
    )
    return hmac.compare_digest(computed.hex(), hash_value)
