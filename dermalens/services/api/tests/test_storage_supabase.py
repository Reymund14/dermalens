import json

import httpx

from app import storage
from app.config import settings


def test_supabase_storage_uses_rest_api(monkeypatch):
    real_client = httpx.Client
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "PUT":
            return httpx.Response(200, json={"Key": "ok"})
        if request.method == "GET":
            return httpx.Response(200, content=b"jpeg")
        if request.method == "POST" and "/list/" in request.url.path:
            prefix = json.loads(request.content)["prefix"]
            items = [] if prefix.endswith(".pdf") else [{"name": "front.jpg", "id": "obj-1"}]
            return httpx.Response(200, json=items)
        if request.method == "DELETE":
            return httpx.Response(200, json=[])
        return httpx.Response(405)

    monkeypatch.setattr(
        storage.httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(storage, "_USE_SUPABASE", True)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key")
    monkeypatch.setattr(settings, "supabase_bucket", "dermalens")

    storage.put("sessions/s1/front.jpg", b"jpeg")
    assert storage.get("sessions/s1/front.jpg") == b"jpeg"
    storage.delete_prefix("sessions/s1")
    storage.delete_prefix("summaries/u/s1.pdf")

    put = next(r for r in requests if r.method == "PUT")
    assert put.url.path == "/storage/v1/object/dermalens/sessions/s1/front.jpg"
    assert put.headers["authorization"] == "Bearer service-key"
    assert put.content == b"jpeg"

    deletes = [json.loads(r.content)["prefixes"] for r in requests if r.method == "DELETE"]
    assert deletes == [["sessions/s1/front.jpg"], ["summaries/u/s1.pdf"]]
