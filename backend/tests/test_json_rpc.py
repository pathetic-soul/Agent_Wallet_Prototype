import json

import httpx
import pytest

from app.services.json_rpc import JsonRpcClient, JsonRpcError


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_sends_json_rpc_request_and_returns_result():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "eth_chainId"
        assert payload["params"] == []
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": "0x14a34"},
        )

    result = await JsonRpcClient(
        "https://rpc.test", transport=httpx.MockTransport(handler)
    ).call("eth_chainId")
    assert result == "0x14a34"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_raises_typed_json_rpc_error():
    def handler(request: httpx.Request) -> httpx.Response:
        request_id = json.loads(request.content)["id"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32500, "message": "AA23 reverted", "data": "0xbeef"},
            },
        )

    with pytest.raises(JsonRpcError) as exc_info:
        await JsonRpcClient(
            "https://rpc.test", transport=httpx.MockTransport(handler)
        ).call("eth_sendUserOperation", [{}])
    assert exc_info.value.code == -32500
    assert exc_info.value.data == "0xbeef"
    assert str(exc_info.value) == "AA23 reverted"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        [],
        {"jsonrpc": "1.0", "id": 1, "result": "0x1"},
        {"jsonrpc": "2.0", "id": 999, "result": "0x1"},
        {"jsonrpc": "2.0", "id": 1},
        {"jsonrpc": "2.0", "id": 1, "error": "bad"},
    ],
)
async def test_call_rejects_malformed_responses(response):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        body = response.copy() if isinstance(response, dict) else response
        if isinstance(body, dict) and body.get("id") == 1:
            body["id"] = payload["id"]
        return httpx.Response(200, json=body)

    with pytest.raises(RuntimeError):
        await JsonRpcClient(
            "https://rpc.test", transport=httpx.MockTransport(handler)
        ).call("test_method")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_propagates_http_failure():
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await JsonRpcClient("https://rpc.test", transport=transport).call("eth_chainId")

