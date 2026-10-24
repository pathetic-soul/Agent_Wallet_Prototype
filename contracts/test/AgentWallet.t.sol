// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {PackedUserOperation} from "@account-abstraction/contracts/interfaces/PackedUserOperation.sol";
import {IEntryPoint} from "@account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {BaseAccount} from "@account-abstraction/contracts/core/BaseAccount.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

import {AgentWallet} from "../src/AgentWallet.sol";
import {IPriceOracle} from "../src/interfaces/IPriceOracle.sol";

interface Vm {
    function addr(uint256 privateKey) external returns (address);
    function deal(address account, uint256 newBalance) external;
    function sign(uint256 privateKey, bytes32 digest) external returns (uint8, bytes32, bytes32);
    function expectRevert(bytes4 selector) external;
    function expectRevert(bytes calldata revertData) external;
    function warp(uint256 timestamp) external;
}

contract MockEntryPoint {
    function validate(AgentWallet wallet, PackedUserOperation calldata userOp, bytes32 userOpHash)
        external
        returns (uint256)
    {
        return wallet.validateUserOp(userOp, userOpHash, 0);
    }

    function executeAgent(AgentWallet wallet, address agent, BaseAccount.Call calldata call) external {
        wallet.executeAgent(agent, call);
    }

    function executeAgentBatch(AgentWallet wallet, address agent, BaseAccount.Call[] calldata calls) external {
        wallet.executeAgentBatch(agent, calls);
    }

    function depositTo(address) external payable {}
    function withdrawTo(address payable, uint256) external {}

    function getNonce(address, uint192) external pure returns (uint256) {
        return 0;
    }
}

contract FixedOracle is IPriceOracle {
    mapping(address => uint256) public price;

    function setPrice(address token, uint256 priceUsd) external {
        price[token] = priceUsd;
    }

    function quoteUsd(address token, uint256 amount) external view returns (uint256) {
        require(price[token] != 0, "missing price");
        return amount * price[token] / 1e18;
    }
}

contract Target {
    uint256 public calls;

    function purchase() external payable {
        calls += 1;
    }
}

contract MockToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address recipient, uint256 amount) external {
        balanceOf[recipient] += amount;
    }

    function transfer(address recipient, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[recipient] += amount;
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transferFrom(address from, address recipient, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "allowance");
        require(balanceOf[from] >= amount, "balance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[recipient] += amount;
        return true;
    }
}

contract AgentWalletTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 private constant AGENT_KEY = 0xA11CE;
    uint256 private constant PER_TX_USD = 20e8;
    uint256 private constant DAILY_USD = 50e8;

    MockEntryPoint private entryPoint;
    FixedOracle private oracle;
    AgentWallet private wallet;
    Target private target;
    MockToken private token;
    address private agent;
    address private recipient = address(0xBEEF);
    address private attacker = address(0xBAD);

    function setUp() public {
        agent = vm.addr(AGENT_KEY);
        entryPoint = new MockEntryPoint();
        oracle = new FixedOracle();
        wallet = new AgentWallet(IEntryPoint(address(entryPoint)), address(this), oracle, PER_TX_USD, DAILY_USD);
        target = new Target();
        token = new MockToken();

        wallet.addSession(agent, 0, uint48(block.timestamp + 1 days));
        wallet.setCallPolicy(address(target), Target.purchase.selector, true);
        wallet.setCallPolicy(address(token), MockToken.transfer.selector, true);
        wallet.setCallPolicy(address(token), MockToken.approve.selector, true);
        wallet.setCallPolicy(address(token), MockToken.transferFrom.selector, true);
        wallet.setRecipientPolicy(recipient, true);
        oracle.setPrice(address(0), 2_000e8);
        oracle.setPrice(address(token), 1e8);
        vm.deal(address(this), 2 ether);
        payable(address(wallet)).transfer(1 ether);
        token.mint(address(wallet), 100e18);
    }

    function testAgentCallWithinLimitExecutes() public {
        BaseAccount.Call memory call =
            BaseAccount.Call({target: address(target), value: 0.005 ether, data: abi.encodeCall(Target.purchase, ())});
        PackedUserOperation memory userOp =
            _signedUserOp(abi.encodeCall(AgentWallet.executeAgent, (agent, call)), keccak256("within-limit"));

        uint256 validationData = entryPoint.validate(wallet, userOp, keccak256("within-limit"));
        require(uint160(validationData) == 0, "signature should validate");
        entryPoint.executeAgent(wallet, agent, call);

        require(target.calls() == 1, "target not called");
        require(wallet.spentInWindowUsd() == 10e8, "wrong USD accounting");
    }

    function testOverLimitCallBecomesPending() public {
        BaseAccount.Call memory call =
            BaseAccount.Call({target: address(target), value: 0.015 ether, data: abi.encodeCall(Target.purchase, ())});

        entryPoint.executeAgent(wallet, agent, call);

        AgentWallet.PendingRequest memory request = wallet.getPending(1);
        require(request.status == AgentWallet.PendingStatus.Open, "pending not open");
        require(request.usdValue == 30e8, "wrong pending value");
        require(target.calls() == 0, "over-limit call executed");
    }

    function testExpiredPendingCanBeReleased() public {
        BaseAccount.Call memory call =
            BaseAccount.Call({target: address(target), value: 0.015 ether, data: abi.encodeCall(Target.purchase, ())});
        entryPoint.executeAgent(wallet, agent, call);
        vm.warp(block.timestamp + 1 hours + 1);

        wallet.expirePending(1);

        AgentWallet.PendingRequest memory request = wallet.getPending(1);
        require(request.status == AgentWallet.PendingStatus.Expired, "not expired");
        (,, uint32 openPending,) = wallet.sessions(agent);
        require(openPending == 0, "pending slot not released");
    }

    function testAgentCannotCallUnapprovedSelector() public {
        BaseAccount.Call memory call =
            BaseAccount.Call({target: address(target), value: 0, data: abi.encodeWithSignature("unknown()")});
        bytes32 userOpHash = keccak256("blocked-selector");
        PackedUserOperation memory userOp =
            _signedUserOp(abi.encodeCall(AgentWallet.executeAgent, (agent, call)), userOpHash);

        vm.expectRevert(
            abi.encodeWithSelector(AgentWallet.CallNotAllowed.selector, address(target), bytes4(keccak256("unknown()")))
        );
        entryPoint.validate(wallet, userOp, userOpHash);
    }

    function testAllowedTokenTransferExecutesAndCountsUsd() public {
        BaseAccount.Call memory call = BaseAccount.Call({
            target: address(token), value: 0, data: abi.encodeCall(MockToken.transfer, (recipient, 5e18))
        });

        entryPoint.executeAgent(wallet, agent, call);

        require(token.balanceOf(recipient) == 5e18, "recipient not paid");
        require(wallet.spentInWindowUsd() == 5e8, "token spend not counted");
    }

    function testApproveToUnapprovedSpenderIsRejected() public {
        BaseAccount.Call memory call = BaseAccount.Call({
            target: address(token), value: 0, data: abi.encodeCall(MockToken.approve, (attacker, type(uint256).max))
        });
        bytes32 userOpHash = keccak256("blocked-approval");
        PackedUserOperation memory userOp =
            _signedUserOp(abi.encodeCall(AgentWallet.executeAgent, (agent, call)), userOpHash);

        vm.expectRevert(abi.encodeWithSelector(AgentWallet.RecipientNotAllowed.selector, attacker));
        entryPoint.validate(wallet, userOp, userOpHash);
    }

    function testBatchValueIsAggregatedBeforeAnyCallExecutes() public {
        BaseAccount.Call[] memory calls = new BaseAccount.Call[](2);
        calls[0] = _nativePurchase(0.0075 ether);
        calls[1] = _nativePurchase(0.0075 ether);

        entryPoint.executeAgentBatch(wallet, agent, calls);

        require(target.calls() == 0, "partial batch execution");
        AgentWallet.PendingRequest memory request = wallet.getPending(1);
        require(request.status == AgentWallet.PendingStatus.Open, "batch not pending");
        require(request.usdValue == 30e8, "batch total incorrect");
    }

    function testDailyLimitAccumulatesAcrossOperations() public {
        BaseAccount.Call memory call = _nativePurchase(0.0075 ether);

        entryPoint.executeAgent(wallet, agent, call);
        entryPoint.executeAgent(wallet, agent, call);
        entryPoint.executeAgent(wallet, agent, call);
        entryPoint.executeAgent(wallet, agent, call);

        require(target.calls() == 3, "wrong successful call count");
        require(wallet.spentInWindowUsd() == 45e8, "wrong daily total");
        require(wallet.getPending(1).reason == AgentWallet.PendingReason.OverDailyLimit, "wrong pending reason");
    }

    function testPauseAndRevokeReturnSignatureFailure() public {
        BaseAccount.Call memory call = _nativePurchase(0.001 ether);
        bytes32 userOpHash = keccak256("session-state");
        PackedUserOperation memory userOp =
            _signedUserOp(abi.encodeCall(AgentWallet.executeAgent, (agent, call)), userOpHash);

        wallet.setPaused(true);
        require(entryPoint.validate(wallet, userOp, userOpHash) == 1, "pause did not fail signature");
        wallet.setPaused(false);
        wallet.revokeSession(agent);
        require(entryPoint.validate(wallet, userOp, userOpHash) == 1, "revoke did not fail signature");
    }

    function testOversizedGasFieldsAreRejected() public {
        BaseAccount.Call memory call = _nativePurchase(0.001 ether);
        bytes32 userOpHash = keccak256("gas-grief");
        PackedUserOperation memory userOp =
            _signedUserOp(abi.encodeCall(AgentWallet.executeAgent, (agent, call)), userOpHash);
        userOp.accountGasLimits =
            bytes32((uint256(uint128(wallet.maxVerificationGas() + 1)) << 128) | uint256(uint128(100_000)));

        vm.expectRevert(AgentWallet.GasLimitExceeded.selector);
        entryPoint.validate(wallet, userOp, userOpHash);
    }

    function testOwnerCanApprovePendingWithoutConsumingAgentBudget() public {
        entryPoint.executeAgent(wallet, agent, _nativePurchase(0.015 ether));

        wallet.approvePending(1);

        require(target.calls() == 1, "approved call not executed");
        require(wallet.spentInWindowUsd() == 0, "owner approval consumed budget");
        require(wallet.getPending(1).status == AgentWallet.PendingStatus.Approved, "not approved");
    }

    function testOwnerCanRejectPendingAndReleaseSlot() public {
        entryPoint.executeAgent(wallet, agent, _nativePurchase(0.015 ether));

        wallet.rejectPending(1);

        require(wallet.getPending(1).status == AgentWallet.PendingStatus.Rejected, "not rejected");
        (,, uint32 openPending,) = wallet.sessions(agent);
        require(openPending == 0, "pending slot not released");
    }

    function testMissingOraclePriceCreatesPendingInsteadOfExecuting() public {
        MockToken unknownToken = new MockToken();
        unknownToken.mint(address(wallet), 10e18);
        wallet.setCallPolicy(address(unknownToken), MockToken.transfer.selector, true);
        BaseAccount.Call memory call = BaseAccount.Call({
            target: address(unknownToken), value: 0, data: abi.encodeCall(MockToken.transfer, (recipient, 1e18))
        });

        entryPoint.executeAgent(wallet, agent, call);

        require(unknownToken.balanceOf(recipient) == 0, "unpriced transfer executed");
        require(wallet.getPending(1).reason == AgentWallet.PendingReason.PricingFailed, "wrong reason");
    }

    function testFuzzSpendAtOrBelowLimit(uint96 seed) public {
        uint256 value = uint256(seed) % (0.01 ether + 1);
        entryPoint.executeAgent(wallet, agent, _nativePurchase(value));
        require(target.calls() == 1, "fuzzed call did not execute");
        require(wallet.spentInWindowUsd() == value * 2_000e8 / 1e18, "fuzzed accounting mismatch");
        require(wallet.spentInWindowUsd() <= PER_TX_USD, "per-tx invariant violated");
    }

    function testAgentExecutionCanOnlyComeFromEntryPoint() public {
        vm.expectRevert(AgentWallet.NotEntryPoint.selector);
        wallet.executeAgent(agent, _nativePurchase(0));
    }

    function testOwnerCanExecuteDirectly() public {
        wallet.execute(_nativePurchase(0));
        require(target.calls() == 1, "owner call failed");
    }

    function testPendingQueueCapPreventsFlooding() public {
        wallet.setPendingPolicy(1 hours, 1);
        BaseAccount.Call memory call = _nativePurchase(0.015 ether);
        entryPoint.executeAgent(wallet, agent, call);

        vm.expectRevert(abi.encodeWithSelector(AgentWallet.PendingLimitReached.selector, agent));
        entryPoint.executeAgent(wallet, agent, call);
    }

    function testFixedWindowResetsAfterTwentyFourHours() public {
        BaseAccount.Call memory call = _nativePurchase(0.0075 ether);
        entryPoint.executeAgent(wallet, agent, call);
        entryPoint.executeAgent(wallet, agent, call);
        entryPoint.executeAgent(wallet, agent, call);
        vm.warp(block.timestamp + 24 hours);

        entryPoint.executeAgent(wallet, agent, call);

        require(target.calls() == 4, "post-reset call failed");
        require(wallet.spentInWindowUsd() == 15e8, "window did not reset");
    }

    function testExpiredPendingCannotBeApproved() public {
        entryPoint.executeAgent(wallet, agent, _nativePurchase(0.015 ether));
        vm.warp(block.timestamp + 1 hours + 1);

        vm.expectRevert(abi.encodeWithSelector(AgentWallet.PendingExpired.selector, 1));
        wallet.approvePending(1);
    }

    function testTransferFromMustDebitTheWallet() public {
        BaseAccount.Call memory call = BaseAccount.Call({
            target: address(token), value: 0, data: abi.encodeCall(MockToken.transferFrom, (attacker, recipient, 1e18))
        });
        bytes32 userOpHash = keccak256("invalid-transfer-from");
        PackedUserOperation memory userOp =
            _signedUserOp(abi.encodeCall(AgentWallet.executeAgent, (agent, call)), userOpHash);

        vm.expectRevert(AgentWallet.InvalidTokenCall.selector);
        entryPoint.validate(wallet, userOp, userOpHash);
    }

    function testEip1271AcceptsOnlyOwnerSignature() public {
        uint256 ownerKey = 0xB0B;
        address signingOwner = vm.addr(ownerKey);
        AgentWallet signingWallet =
            new AgentWallet(IEntryPoint(address(entryPoint)), signingOwner, oracle, PER_TX_USD, DAILY_USD);
        bytes32 hash = keccak256("permit-attempt");
        (uint8 ownerV, bytes32 ownerR, bytes32 ownerS) =
            vm.sign(ownerKey, MessageHashUtils.toEthSignedMessageHash(hash));
        (uint8 agentV, bytes32 agentR, bytes32 agentS) =
            vm.sign(AGENT_KEY, MessageHashUtils.toEthSignedMessageHash(hash));

        require(
            signingWallet.isValidSignature(hash, abi.encodePacked(ownerR, ownerS, ownerV)) == 0x1626ba7e,
            "owner signature rejected"
        );
        require(
            signingWallet.isValidSignature(hash, abi.encodePacked(agentR, agentS, agentV)) == 0xffffffff,
            "agent signature accepted"
        );
    }

    function _nativePurchase(uint256 value) private view returns (BaseAccount.Call memory) {
        return BaseAccount.Call({target: address(target), value: value, data: abi.encodeCall(Target.purchase, ())});
    }

    function _signedUserOp(bytes memory callData, bytes32 userOpHash)
        private
        returns (PackedUserOperation memory userOp)
    {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(AGENT_KEY, MessageHashUtils.toEthSignedMessageHash(userOpHash));
        userOp.sender = address(wallet);
        userOp.callData = callData;
        userOp.accountGasLimits = bytes32((uint256(uint128(500_000)) << 128) | uint256(uint128(500_000)));
        userOp.gasFees = bytes32(uint256(10 gwei));
        userOp.signature = abi.encodePacked(r, s, v);
    }

    receive() external payable {}
}
