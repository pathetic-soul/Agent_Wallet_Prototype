// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IPriceOracle {
    /// @notice Quotes an asset amount in USD with 8 decimals.
    function quoteUsd(address token, uint256 amount) external view returns (uint256 usdValue);
}

