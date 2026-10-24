// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IEntryPoint} from "@account-abstraction/contracts/interfaces/IEntryPoint.sol";

import {AgentWallet} from "../src/AgentWallet.sol";
import {AgentWalletFactory} from "../src/AgentWalletFactory.sol";
import {PriceOracle} from "../src/PriceOracle.sol";
import {TicketShop} from "../src/TicketShop.sol";
import {IPriceOracle} from "../src/interfaces/IPriceOracle.sol";

interface VmFactoryOracle {
    function expectRevert(bytes4 selector) external;
    function expectRevert(bytes calldata revertData) external;
    function warp(uint256 timestamp) external;
    function deal(address account, uint256 newBalance) external;
}

contract EntryPointStub {}

contract FeedStub {
    uint8 public immutable decimals;
    int256 public answer;
    uint256 public updatedAt;

    constructor(uint8 decimals_) {
        decimals = decimals_;
    }

    function setAnswer(int256 answer_, uint256 updatedAt_) external {
        answer = answer_;
        updatedAt = updatedAt_;
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        return (1, answer, updatedAt, updatedAt, 1);
    }
}

contract FactoryAndOracleTest {
    VmFactoryOracle private constant vm = VmFactoryOracle(address(uint160(uint256(keccak256("hevm cheat code")))));

    PriceOracle private oracle;

    function setUp() public {
        oracle = new PriceOracle(address(this));
    }

    function testFixedPriceNormalizesTokenDecimals() public {
        address token = address(0xCAFE);
        oracle.setFixedPrice(token, 6, 1e8);
        require(oracle.quoteUsd(token, 12_500_000) == 12_50000000, "fixed price quote incorrect");
    }

    function testFeedPriceNormalizesToEightDecimals() public {
        address token = address(0xCAFE);
        FeedStub feed = new FeedStub(18);
        feed.setAnswer(2_000e18, block.timestamp);
        oracle.setFeed(token, address(feed), 18, 1 hours);
        require(oracle.quoteUsd(token, 2e18) == 4_000e8, "feed quote incorrect");
    }

    function testStaleFeedFailsClosed() public {
        vm.warp(2 hours);
        address token = address(0xCAFE);
        FeedStub feed = new FeedStub(8);
        feed.setAnswer(1e8, 1);
        oracle.setFeed(token, address(feed), 18, 1 hours);

        vm.expectRevert(abi.encodeWithSelector(PriceOracle.StaleOracleAnswer.selector, token, 1));
        oracle.quoteUsd(token, 1e18);
    }

    function testDisabledTokenCannotBeQuoted() public {
        address token = address(0xCAFE);
        oracle.setFixedPrice(token, 18, 1e8);
        oracle.disableToken(token);

        vm.expectRevert(abi.encodeWithSelector(PriceOracle.TokenNotConfigured.selector, token));
        oracle.quoteUsd(token, 1e18);
    }

    function testFactoryAddressIsDeterministicAndCreationIsIdempotent() public {
        EntryPointStub entryPoint = new EntryPointStub();
        AgentWalletFactory factory =
            new AgentWalletFactory(IEntryPoint(address(entryPoint)), IPriceOracle(address(oracle)));
        bytes32 salt = keccak256("owner-one");
        address predicted = factory.getAddress(address(this), salt, 20e8, 50e8);

        AgentWallet first = factory.createWallet(address(this), salt, 20e8, 50e8);
        AgentWallet second = factory.createWallet(address(this), salt, 20e8, 50e8);

        require(address(first) == predicted, "prediction mismatch");
        require(address(second) == predicted, "creation not idempotent");
        require(first.owner() == address(this), "owner mismatch");
    }

    function testTicketShopRecordsPurchase() public {
        vm.deal(address(this), 1 ether);
        TicketShop shop = new TicketShop(0.01 ether);

        uint256 ticketId = shop.buyTicket{value: 0.01 ether}(address(0xBEEF));

        require(ticketId == 1, "wrong ticket id");
        require(shop.ticketOwner(ticketId) == address(0xBEEF), "wrong attendee");
    }

    function testTicketShopRejectsWrongPrice() public {
        TicketShop shop = new TicketShop(0.01 ether);
        vm.expectRevert(TicketShop.IncorrectPrice.selector);
        shop.buyTicket(address(0xBEEF));
    }

    receive() external payable {}
}
