"""Authenticated community RPCs. Never log tokens or return auth/admin payloads."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import Settings

_client = httpx.Client(timeout=12.0)
_auth_cache: dict[str, tuple[float, dict]] = {}


@dataclass
class CommunityStore:
    settings: Settings
    client: Any = None

    def __post_init__(self):
        self.client = self.client or _client
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            raise HTTPException(503, 'ระบบข้อมูลชุมชนยังไม่พร้อม กรุณาลองใหม่ภายหลัง')

    def headers(self, token: str | None = None) -> dict:
        return {
            'apikey': self.settings.supabase_anon_key or self.settings.supabase_service_role_key,
            'Authorization': 'Bearer ' + (token or self.settings.supabase_service_role_key),
        }

    def call(self, method: str, path: str, *, token: str | None = None, **kwargs):
        try:
            response = self.client.request(method, self.settings.supabase_url.rstrip('/') + path,
                                           headers={**self.headers(token), **kwargs.pop('headers', {})}, **kwargs)
        except httpx.HTTPError:
            raise HTTPException(503, 'เชื่อมต่อระบบข้อมูลชุมชนไม่ได้ ยังไม่ได้บันทึกข้อมูล') from None
        if response.status_code >= 400:
            try:
                error = response.json()
            except ValueError:
                error = {}
            code = error.get('code')
            status = {'42501': 403, '40001': 409, '23505': 409, 'P0002': 404,
                      '22023': 400, '23514': 400, '23503': 400, '22P02': 400}.get(code)
            if status:
                message = str(error.get('message') or 'ข้อมูลหรือสิทธิ์ไม่ถูกต้อง')[:240]
                raise HTTPException(status, message)
            if response.status_code in (401, 403):
                raise HTTPException(401, 'กรุณาเข้าสู่ระบบอีกครั้ง')
            raise HTTPException(503, 'ระบบข้อมูลชุมชนยังไม่พร้อม กรุณาลองใหม่ภายหลัง')
        if not response.content:
            return None
        return response.json()

    def user(self, token: str) -> dict:
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        cached = _auth_cache.get(fingerprint)
        if self.client is _client and cached and cached[0] > time.monotonic():
            return cached[1]
        data = self.call('GET', '/auth/v1/user', token=token)
        if not data.get('id') or not data.get('email_confirmed_at'):
            raise HTTPException(403, 'ยืนยันอีเมลก่อนใช้ระบบชุมชน')
        user = {key: data.get(key) for key in ('id', 'email', 'email_confirmed_at')}
        if self.client is _client:
            if len(_auth_cache) >= 256:
                _auth_cache.clear()
            _auth_cache[fingerprint] = (time.monotonic() + 20, user)
        return user

    def rpc(self, action: str, payload: dict, token: str):
        return self.call('POST', '/rest/v1/rpc/cme_action', token=token,
                         json={'p_action': action, 'p_payload': payload})

    def rows(self, table: str, **params):
        return self.call('GET', '/rest/v1/' + table, params=params)

    def insert(self, table: str, row: dict, *, dedup: bool = False):
        params = {'on_conflict': 'dedup_key'} if dedup else {}
        return self.call('POST', '/rest/v1/' + table, json=row, params=params,
                         headers={'Prefer': ('resolution=ignore-duplicates,' if dedup else '') + 'return=representation'})

    def patch(self, table: str, row_id: str, data: dict):
        return self.call('PATCH', '/rest/v1/' + table, params={'id': 'eq.' + row_id}, json=data,
                         headers={'Prefer': 'return=representation'})
