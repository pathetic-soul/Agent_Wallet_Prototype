// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

import {IPriceOracle} from "./interfaces/IPriceOracle.sol";

interface IAggregatorV3 {
    function decimals() external view returns (uint8);

    function latestRoundData()
        external
        view
        returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}

/// @notice Testnet oracle wrapper that normalizes supported assets to 8-decimal USD values.
contract PriceOracle is IPriceOracle {
    struct TokenConfig {
        address feed;
        uint48 maxAge;
        uint8 tokenDecimals;
        bool enabled;
        bool usesFixedPrice;
        uint256 fixedPriceUsd;
    }

    error NotOwner();
    error InvalidAddress();
    error InvalidConfiguration();
    error TokenNotConfigured(address token);
    error InvalidOracleAnswer(address token);
    error StaleOracleAnswer(address token, uint256 updatedAt);

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event FeedConfigured(address indexed token, address indexed feed, uint8 tokenDecimals, uint48 maxAge);
    event FixedPriceConfigured(address indexed token, uint8 tokenDecimals, uint256 fixedPriceUsd);
    event TokenDisabled(address indexed token);

    address public owner;
    mapping(address token => TokenConfig config) public tokenConfig;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address initialOwner) {
        if (initialOwner == address(0)) revert InvalidAddress();
        owner = initialOwner;
        emit OwnershipTransferred(address(0), initialOwner);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setFeed(address token, address feed, uint8 tokenDecimals, uint48 maxAge) external onlyOwner {
        if (feed == address(0) || maxAge == 0 || tokenDecimals > 36) {
            revert InvalidConfiguration();
        }
        tokenConfig[token] = TokenConfig({
            feed: feed,
            maxAge: maxAge,
            tokenDecimals: tokenDecimals,
            enabled: true,
            usesFixedPrice: false,
            fixedPriceUsd: 0
        });
        emit FeedConfigured(token, feed, tokenDecimals, maxAge);
    }

    /// @dev Testnet escape hatch for assets without a supported feed. Surface this clearly in the UI.
    function setFixedPrice(address token, uint8 tokenDecimals, uint256 fixedPriceUsd) external onlyOwner {
        if (fixedPriceUsd == 0 || tokenDecimals > 36) revert InvalidConfiguration();
        tokenConfig[token] = TokenConfig({
            feed: address(0),
            maxAge: 0,
            tokenDecimals: tokenDecimals,
            enabled: true,
            usesFixedPrice: true,
            fixedPriceUsd: fixedPriceUsd
        });
        emit FixedPriceConfigured(token, tokenDecimals, fixedPriceUsd);
    }

    function disableToken(address token) external onlyOwner {
        tokenConfig[token].enabled = false;
        emit TokenDisabled(token);
    }

    function quoteUsd(address token, uint256 amount) external view returns (uint256 usdValue) {
        TokenConfig memory config = tokenConfig[token];
        if (!config.enabled) revert TokenNotConfigured(token);

        uint256 priceUsd = config.fixedPriceUsd;
        if (!config.usesFixedPrice) {
            IAggregatorV3 feed = IAggregatorV3(config.feed);
            (, int256 answer,, uint256 updatedAt,) = feed.latestRoundData();
            if (answer <= 0 || updatedAt == 0 || updatedAt > block.timestamp) {
                revert InvalidOracleAnswer(token);
            }
            if (block.timestamp - updatedAt > config.maxAge) {
                revert StaleOracleAnswer(token, updatedAt);
            }

            uint8 feedDecimals = feed.decimals();
            if (feedDecimals > 36) revert InvalidConfiguration();
            priceUsd = uint256(answer);
            if (feedDecimals < 8) {
                priceUsd *= 10 ** (8 - feedDecimals);
            } else if (feedDecimals > 8) {
                priceUsd /= 10 ** (feedDecimals - 8);
            }
        }

        return Math.mulDiv(amount, priceUsd, 10 ** config.tokenDecimals);
    }
}

