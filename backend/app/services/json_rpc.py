from dataclasses import dataclass
from itertools import count
from typing import Any

import httpx


class JsonRpcError(RuntimeError):
    def __init__(self, code: int, message: str, data: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


@dataclass(slots=True)
class JsonRpcClient:
    url: str
    timeout_seconds: float = 10.0
    transport: httpx.AsyncBaseTransport | None = None

    _ids = count(1)

    async def call(self, method: str, params: list[object] | None = None) -> Any:
        request_id = next(self._ids)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or [],
        }
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("JSON-RPC response must be an object")
        if body.get("jsonrpc") != "2.0":
            raise RuntimeError("JSON-RPC response used an unsupported version")
        if body.get("id") != request_id:
            raise RuntimeError("JSON-RPC response id did not match the request")
        if "error" in body:
            error = body["error"]
            if not isinstance(error, dict):
                raise RuntimeError("JSON-RPC error payload must be an object")
            raise JsonRpcError(
                int(error.get("code", -32000)),
                str(error.get("message", "Unknown JSON-RPC error")),
                error.get("data"),
            )
        if "result" not in body:
            raise RuntimeError("JSON-RPC response did not contain a result")
        return body["result"]
