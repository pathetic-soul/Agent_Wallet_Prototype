from typing import Any

from app.models import PackedUserOperation, UserOperationGasEstimate
from app.services.json_rpc import JsonRpcClient


class BundlerClient:
    def __init__(
        self,
        url: str,
        entry_point: str,
        rpc: JsonRpcClient | None = None,
    ) -> None:
        self.rpc = rpc or JsonRpcClient(url)
        self.entry_point = entry_point

    async def supported_entry_points(self) -> list[str]:
        result = await self.rpc.call("eth_supportedEntryPoints")
        if not isinstance(result, list):
            raise RuntimeError("Bundler returned an invalid entry-point list")
        return [str(address).lower() for address in result]

    async def send_user_operation(self, user_operation: PackedUserOperation) -> str:
        payload = user_operation.model_dump(by_alias=True)
        result = await self.rpc.call(
            "eth_sendUserOperation",
            [payload, self.entry_point],
        )
        if not isinstance(result, str) or not result.startswith("0x") or len(result) != 66:
            raise RuntimeError("Bundler returned an invalid UserOperation hash")
        return result.lower()

    async def estimate_user_operation_gas(
        self, user_operation: PackedUserOperation
    ) -> UserOperationGasEstimate:
        result = await self.rpc.call(
            "eth_estimateUserOperationGas",
            [user_operation.model_dump(by_alias=True), self.entry_point],
        )
        if not isinstance(result, dict):
            raise RuntimeError("Bundler returned an invalid gas estimate")
        return UserOperationGasEstimate.model_validate(result)

    async def get_user_operation_receipt(
        self, user_operation_hash: str
    ) -> dict[str, Any] | None:
        result = await self.rpc.call(
            "eth_getUserOperationReceipt", [user_operation_hash]
        )
        if result is not None and not isinstance(result, dict):
            raise RuntimeError("Bundler returned an invalid UserOperation receipt")
        return result
