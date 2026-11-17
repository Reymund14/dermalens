"""Object storage: local disk in development, Supabase Storage when configured.
The three functions keep the same contract for callers in both modes.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

import httpx

from .config import settings

_USE_SUPABASE = bool(settings.supabase_url and settings.supabase_service_key)


def _check_key(key: str) -> None:
    if not key or key.startswith("/") or "\\" in key or ".." in key.split("/"):
        raise ValueError("invalid object key")


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.supabase_url,
        headers={
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "apikey": settings.supabase_service_key,
        },
        timeout=30.0,
    )


def _object_path(key: str) -> str:
    return f"/storage/v1/object/{settings.supabase_bucket}/{quote(key, safe='/')}"


def _list_paths(client: httpx.Client, prefix: str) -> list[str]:
    paths: list[str] = []
    offset = 0
    while True:
        r = client.post(
            f"/storage/v1/object/list/{settings.supabase_bucket}",
            json={"prefix": prefix, "limit": 1000, "offset": offset},
        )
        r.raise_for_status()
        items = r.json()
        for item in items:
            path = f"{prefix.rstrip('/')}/{item['name']}"
            if item.get("id") is None:  # a folder prefix, not an object
                paths.extend(_list_paths(client, path))
            else:
                paths.append(path)
        if len(items) < 1000:
            return paths
        offset += 1000


def _path(key: str) -> Path:
    _check_key(key)
    p = (settings.storage_dir / key).resolve()
    root = settings.storage_dir.resolve()
    if root not in p.parents:
        raise ValueError("invalid object key")
    return p


def put(key: str, data: bytes) -> None:
    _check_key(key)
    if _USE_SUPABASE:
        with _client() as client:
            r = client.put(_object_path(key), content=data, headers={"Content-Type": "application/octet-stream"})
            r.raise_for_status()
        return
    p = _path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def get(key: str) -> bytes:
    _check_key(key)
    if _USE_SUPABASE:
        with _client() as client:
            r = client.get(_object_path(key))
            r.raise_for_status()
            return r.content
    return _path(key).read_bytes()


def delete_prefix(prefix: str) -> None:
    _check_key(prefix)
    if _USE_SUPABASE:
        with _client() as client:
            paths = _list_paths(client, prefix)
            if "." in prefix.rsplit("/", 1)[-1]:  # exact file key, not a folder
                paths.append(prefix)
            paths = list(dict.fromkeys(paths))
            for i in range(0, len(paths), 100):
                r = client.request(
                    "DELETE",
                    f"/storage/v1/object/{settings.supabase_bucket}",
                    json={"prefixes": paths[i:i + 100]},
                )
                r.raise_for_status()
        return
    p = _path(prefix)
    if p.exists():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
