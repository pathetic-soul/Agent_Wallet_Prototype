// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IEntryPoint} from "@account-abstraction/contracts/interfaces/IEntryPoint.sol";

import {AgentWallet} from "./AgentWallet.sol";
import {IPriceOracle} from "./interfaces/IPriceOracle.sol";

contract AgentWalletFactory {
    error InvalidAddress();

    event WalletCreated(address indexed wallet, address indexed owner, bytes32 indexed salt);

    IEntryPoint public immutable entryPoint;
    IPriceOracle public immutable priceOracle;

    constructor(IEntryPoint entryPoint_, IPriceOracle priceOracle_) {
        if (address(entryPoint_) == address(0) || address(priceOracle_) == address(0)) {
            revert InvalidAddress();
        }
        entryPoint = entryPoint_;
        priceOracle = priceOracle_;
    }

    function createWallet(address owner, bytes32 salt, uint256 perTransactionLimitUsd, uint256 dailyLimitUsd)
        external
        returns (AgentWallet wallet)
    {
        address predicted = getAddress(owner, salt, perTransactionLimitUsd, dailyLimitUsd);
        if (predicted.code.length != 0) return AgentWallet(payable(predicted));

        wallet = new AgentWallet{salt: salt}(entryPoint, owner, priceOracle, perTransactionLimitUsd, dailyLimitUsd);
        emit WalletCreated(address(wallet), owner, salt);
    }

    function getAddress(address owner, bytes32 salt, uint256 perTransactionLimitUsd, uint256 dailyLimitUsd)
        public
        view
        returns (address)
    {
        bytes memory creationCode = abi.encodePacked(
            type(AgentWallet).creationCode,
            abi.encode(entryPoint, owner, priceOracle, perTransactionLimitUsd, dailyLimitUsd)
        );
        bytes32 hash = keccak256(abi.encodePacked(bytes1(0xff), address(this), salt, keccak256(creationCode)));
        return address(uint160(uint256(hash)));
    }
}

