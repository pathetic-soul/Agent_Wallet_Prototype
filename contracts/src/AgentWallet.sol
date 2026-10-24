// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {BaseAccount} from "@account-abstraction/contracts/core/BaseAccount.sol";
import {SIG_VALIDATION_FAILED, _packValidationData} from "@account-abstraction/contracts/core/Helpers.sol";
import {UserOperationLib} from "@account-abstraction/contracts/core/UserOperationLib.sol";
import {IEntryPoint} from "@account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {PackedUserOperation} from "@account-abstraction/contracts/interfaces/PackedUserOperation.sol";
import {IERC1271} from "@openzeppelin/contracts/interfaces/IERC1271.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import {IPriceOracle} from "./interfaces/IPriceOracle.sol";

/// @notice ERC-4337 v0.7 account with explicit owner and constrained agent execution paths.
contract AgentWallet is BaseAccount, IERC1271, ReentrancyGuard {
    using UserOperationLib for PackedUserOperation;

    enum PendingStatus {
        None,
        Open,
        Approved,
        Rejected,
        Expired
    }

    enum PendingReason {
        OverPerTransactionLimit,
        OverDailyLimit,
        PricingFailed
    }

    struct Session {
        uint48 validAfter;
        uint48 validUntil;
        uint32 openPending;
        bool revoked;
    }

    struct PendingRequest {
        address agent;
        uint48 createdAt;
        uint48 expiresAt;
        PendingStatus status;
        PendingReason reason;
        uint256 usdValue;
        bytes encodedCalls;
    }

    error NotOwner();
    error NotEntryPoint();
    error NotOwnerOrEntryPoint();
    error InvalidAddress();
    error InvalidPolicy();
    error WalletPaused();
    error InvalidSession(address agent);
    error InvalidAgentCall();
    error CallNotAllowed(address target, bytes4 selector);
    error RecipientNotAllowed(address recipient);
    error InvalidTokenCall();
    error GasLimitExceeded();
    error PendingLimitReached(address agent);
    error PendingNotOpen(uint256 id);
    error PendingExpired(uint256 id);
    error ExternalCallFailed(uint256 index, bytes reason);

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event WalletPauseChanged(bool paused);
    event SessionAdded(address indexed agent, uint48 validAfter, uint48 validUntil);
    event SessionRevoked(address indexed agent);
    event CallPolicyUpdated(address indexed target, bytes4 indexed selector, bool allowed);
    event RecipientPolicyUpdated(address indexed recipient, bool allowed);
    event SpendPolicyUpdated(uint256 perTransactionUsd, uint256 dailyUsd);
    event GasPolicyUpdated(uint128 maxVerificationGas, uint128 maxCallGas, uint256 maxFeePerGas);
    event AgentCallExecuted(address indexed agent, uint256 usdValue, uint256 callCount);
    event ApprovalRequested(
        uint256 indexed id, address indexed agent, PendingReason reason, uint256 usdValue, uint48 expiresAt
    );
    event PendingApproved(uint256 indexed id);
    event PendingRejected(uint256 indexed id);
    event PendingMarkedExpired(uint256 indexed id);

    bytes4 private constant ERC1271_MAGIC_VALUE = IERC1271.isValidSignature.selector;
    bytes4 private constant TRANSFER_SELECTOR = IERC20.transfer.selector;
    bytes4 private constant TRANSFER_FROM_SELECTOR = IERC20.transferFrom.selector;
    bytes4 private constant APPROVE_SELECTOR = IERC20.approve.selector;

    IEntryPoint private immutable _entryPoint;
    IPriceOracle public immutable priceOracle;

    address public owner;
    bool public paused;

    uint256 public perTransactionLimitUsd;
    uint256 public dailyLimitUsd;
    uint48 public windowStart;
    uint48 public pendingTtl = 1 hours;
    uint256 public spentInWindowUsd;
    uint32 public maxOpenPendingPerAgent = 5;

    uint128 public maxVerificationGas = 1_000_000;
    uint128 public maxCallGas = 2_000_000;
    uint256 public maxFeePerGas = 100 gwei;

    uint256 public nextPendingId = 1;

    mapping(address agent => Session session) public sessions;
    mapping(address target => mapping(bytes4 selector => bool allowed)) public allowedCall;
    mapping(address recipient => bool allowed) public allowedRecipient;
    mapping(uint256 id => PendingRequest request) private _pending;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyEntryPoint() {
        if (msg.sender != address(_entryPoint)) revert NotEntryPoint();
        _;
    }

    constructor(
        IEntryPoint entryPoint_,
        address initialOwner,
        IPriceOracle priceOracle_,
        uint256 perTransactionLimitUsd_,
        uint256 dailyLimitUsd_
    ) {
        if (address(entryPoint_) == address(0) || initialOwner == address(0) || address(priceOracle_) == address(0)) revert InvalidAddress();
        if (perTransactionLimitUsd_ == 0 || dailyLimitUsd_ < perTransactionLimitUsd_) revert InvalidPolicy();

        _entryPoint = entryPoint_;
        owner = initialOwner;
        priceOracle = priceOracle_;
        perTransactionLimitUsd = perTransactionLimitUsd_;
        dailyLimitUsd = dailyLimitUsd_;
        windowStart = uint48(block.timestamp);

        emit OwnershipTransferred(address(0), initialOwner);
        emit SpendPolicyUpdated(perTransactionLimitUsd_, dailyLimitUsd_);
    }

    receive() external payable {}

    function entryPoint() public view override returns (IEntryPoint) {
        return _entryPoint;
    }

    function getPending(uint256 id) external view returns (PendingRequest memory) {
        return _pending[id];
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setPaused(bool newPaused) external onlyOwner {
        paused = newPaused;
        emit WalletPauseChanged(newPaused);
    }

    function addSession(address agent, uint48 validAfter, uint48 validUntil) external onlyOwner {
        if (agent == address(0) || validUntil == 0 || validUntil <= validAfter || validUntil <= block.timestamp) {
            revert InvalidPolicy();
        }
        uint32 openPending = sessions[agent].openPending;
        sessions[agent] = Session(validAfter, validUntil, openPending, false);
        emit SessionAdded(agent, validAfter, validUntil);
    }

    function revokeSession(address agent) external onlyOwner {
        sessions[agent].revoked = true;
        emit SessionRevoked(agent);
    }

    function setCallPolicy(address target, bytes4 selector, bool allowed) external onlyOwner {
        if (target == address(0) || target == address(this)) revert InvalidAddress();
        allowedCall[target][selector] = allowed;
        emit CallPolicyUpdated(target, selector, allowed);
    }

    function setRecipientPolicy(address recipient, bool allowed) external onlyOwner {
        if (recipient == address(0) || recipient == address(this)) revert InvalidAddress();
        allowedRecipient[recipient] = allowed;
        emit RecipientPolicyUpdated(recipient, allowed);
    }

    function setSpendPolicy(uint256 perTransactionLimitUsd_, uint256 dailyLimitUsd_) external onlyOwner {
        if (perTransactionLimitUsd_ == 0 || dailyLimitUsd_ < perTransactionLimitUsd_) revert InvalidPolicy();
        perTransactionLimitUsd = perTransactionLimitUsd_;
        dailyLimitUsd = dailyLimitUsd_;
        emit SpendPolicyUpdated(perTransactionLimitUsd_, dailyLimitUsd_);
    }

    function setPendingPolicy(uint48 pendingTtl_, uint32 maxOpenPendingPerAgent_) external onlyOwner {
        if (pendingTtl_ == 0 || maxOpenPendingPerAgent_ == 0) revert InvalidPolicy();
        pendingTtl = pendingTtl_;
        maxOpenPendingPerAgent = maxOpenPendingPerAgent_;
    }

    function setGasPolicy(uint128 maxVerificationGas_, uint128 maxCallGas_, uint256 maxFeePerGas_) external onlyOwner {
        if (maxVerificationGas_ == 0 || maxCallGas_ == 0 || maxFeePerGas_ == 0) revert InvalidPolicy();
        maxVerificationGas = maxVerificationGas_;
        maxCallGas = maxCallGas_;
        maxFeePerGas = maxFeePerGas_;
        emit GasPolicyUpdated(maxVerificationGas_, maxCallGas_, maxFeePerGas_);
    }

    /// @notice Owner path for direct MetaMask calls and owner-signed UserOperations.
    function execute(Call calldata call) external nonReentrant {
        if (msg.sender != owner && msg.sender != address(_entryPoint)) {
            revert NotOwnerOrEntryPoint();
        }
        _performCall(0, call);
    }

    /// @notice EntryPoint-only path for policy-constrained agent operations.
    function executeAgent(address agent, Call calldata call) external onlyEntryPoint nonReentrant {
        Call[] memory calls = new Call[](1);
        calls[0] = call;
        _executeAgent(agent, calls);
    }

    function executeAgentBatch(address agent, Call[] calldata calls) external onlyEntryPoint nonReentrant {
        Call[] memory copiedCalls = calls;
        _executeAgent(agent, copiedCalls);
    }

    function approvePending(uint256 id) external onlyOwner nonReentrant {
        PendingRequest storage request = _pending[id];
        if (request.status != PendingStatus.Open) revert PendingNotOpen(id);
        if (block.timestamp > request.expiresAt) revert PendingExpired(id);

        request.status = PendingStatus.Approved;
        sessions[request.agent].openPending -= 1;
        Call[] memory calls = abi.decode(request.encodedCalls, (Call[]));
        _performCalls(calls);
        emit PendingApproved(id);
    }

    function rejectPending(uint256 id) external onlyOwner {
        PendingRequest storage request = _pending[id];
        if (request.status != PendingStatus.Open) revert PendingNotOpen(id);
        request.status = PendingStatus.Rejected;
        sessions[request.agent].openPending -= 1;
        emit PendingRejected(id);
    }

    function expirePending(uint256 id) external {
        PendingRequest storage request = _pending[id];
        if (request.status != PendingStatus.Open) revert PendingNotOpen(id);
        if (block.timestamp <= request.expiresAt) revert InvalidPolicy();
        request.status = PendingStatus.Expired;
        sessions[request.agent].openPending -= 1;
        emit PendingMarkedExpired(id);
    }

    function addDeposit() external payable {
        _entryPoint.depositTo{value: msg.value}(address(this));
    }

    function withdrawDepositTo(address payable recipient, uint256 amount) external onlyOwner {
        _entryPoint.withdrawTo(recipient, amount);
    }

    function isValidSignature(bytes32 hash, bytes calldata signature) external view override returns (bytes4) {
        (address recovered, ECDSA.RecoverError error,) =
            ECDSA.tryRecover(MessageHashUtils.toEthSignedMessageHash(hash), signature);
        return error == ECDSA.RecoverError.NoError && recovered == owner ? ERC1271_MAGIC_VALUE : bytes4(0xffffffff);
    }

    function _validateSignature(PackedUserOperation calldata userOp, bytes32 userOpHash)
        internal
        view
        override
        returns (uint256 validationData)
    {
        (address signer, ECDSA.RecoverError error,) =
            ECDSA.tryRecover(MessageHashUtils.toEthSignedMessageHash(userOpHash), userOp.signature);
        if (error != ECDSA.RecoverError.NoError) return SIG_VALIDATION_FAILED;

        if (signer == owner) {
            return 0;
        }

        Session memory session = sessions[signer];
        if (paused || session.revoked || session.validUntil == 0) {
            return SIG_VALIDATION_FAILED;
        }
        _validateGas(userOp);
        _validateAgentCallData(signer, userOp.callData);
        return _packValidationData(false, session.validUntil, session.validAfter);
    }

    function _validateGas(PackedUserOperation calldata userOp) internal view {
        if (
            userOp.unpackVerificationGasLimit() > maxVerificationGas || userOp.unpackCallGasLimit() > maxCallGas
                || userOp.unpackMaxFeePerGas() > maxFeePerGas
        ) revert GasLimitExceeded();
    }

    function _validateAgentCallData(address signer, bytes calldata callData) internal view {
        if (callData.length < 4) revert InvalidAgentCall();
        bytes4 selector = bytes4(callData[:4]);
        if (selector == this.executeAgent.selector) {
            (address agent, Call memory call) = abi.decode(callData[4:], (address, Call));
            if (agent != signer) revert InvalidAgentCall();
            _validateCall(call);
            return;
        }
        if (selector == this.executeAgentBatch.selector) {
            (address agent, Call[] memory calls) = abi.decode(callData[4:], (address, Call[]));
            if (agent != signer || calls.length == 0) revert InvalidAgentCall();
            for (uint256 i = 0; i < calls.length; ++i) {
                _validateCall(calls[i]);
            }
            return;
        }
        revert InvalidAgentCall();
    }

    function _validateCall(Call memory call) internal view {
        if (call.target == address(this) || call.target == address(0)) {
            revert InvalidAgentCall();
        }
        bytes4 selector = _selector(call.data);
        if (!allowedCall[call.target][selector]) {
            revert CallNotAllowed(call.target, selector);
        }
        _validateTokenRecipient(call.target, selector, call.data);
    }

    function _validateTokenRecipient(address, bytes4 selector, bytes memory data) internal view {
        if (selector == TRANSFER_SELECTOR) {
            (address recipient,) = abi.decode(_arguments(data), (address, uint256));
            if (!allowedRecipient[recipient]) revert RecipientNotAllowed(recipient);
        } else if (selector == TRANSFER_FROM_SELECTOR) {
            (address from, address recipient,) = abi.decode(_arguments(data), (address, address, uint256));
            if (from != address(this)) revert InvalidTokenCall();
            if (!allowedRecipient[recipient]) revert RecipientNotAllowed(recipient);
        } else if (selector == APPROVE_SELECTOR) {
            (address spender,) = abi.decode(_arguments(data), (address, uint256));
            if (!allowedRecipient[spender]) revert RecipientNotAllowed(spender);
        }
    }

    function _executeAgent(address agent, Call[] memory calls) internal {
        Session memory session = sessions[agent];
        if (
            paused || session.revoked || session.validUntil == 0 || block.timestamp < session.validAfter
                || block.timestamp > session.validUntil
        ) revert InvalidSession(agent);
        if (calls.length == 0) revert InvalidAgentCall();

        uint256 totalUsd;
        for (uint256 i = 0; i < calls.length; ++i) {
            _validateCall(calls[i]);
            (bool priced, uint256 usdValue) = _quoteCall(calls[i]);
            if (!priced) {
                _createPending(agent, calls, PendingReason.PricingFailed, 0);
                return;
            }
            totalUsd += usdValue;
        }

        _resetWindowIfNeeded();
        if (totalUsd > perTransactionLimitUsd) {
            _createPending(agent, calls, PendingReason.OverPerTransactionLimit, totalUsd);
            return;
        }
        if (spentInWindowUsd + totalUsd > dailyLimitUsd) {
            _createPending(agent, calls, PendingReason.OverDailyLimit, totalUsd);
            return;
        }

        spentInWindowUsd += totalUsd;
        _performCalls(calls);
        emit AgentCallExecuted(agent, totalUsd, calls.length);
    }

    function _quoteCall(Call memory call) internal view returns (bool priced, uint256 usdValue) {
        if (call.value > 0) {
            try priceOracle.quoteUsd(address(0), call.value) returns (uint256 valueUsd) {
                usdValue += valueUsd;
            } catch {
                return (false, 0);
            }
        }

        bytes4 selector = _selector(call.data);
        uint256 tokenAmount;
        if (selector == TRANSFER_SELECTOR || selector == APPROVE_SELECTOR) {
            (, tokenAmount) = abi.decode(_arguments(call.data), (address, uint256));
        } else if (selector == TRANSFER_FROM_SELECTOR) {
            (,, tokenAmount) = abi.decode(_arguments(call.data), (address, address, uint256));
        }

        if (tokenAmount > 0) {
            try priceOracle.quoteUsd(call.target, tokenAmount) returns (uint256 valueUsd) {
                usdValue += valueUsd;
            } catch {
                return (false, 0);
            }
        }
        return (true, usdValue);
    }

    function _createPending(address agent, Call[] memory calls, PendingReason reason, uint256 usdValue) internal {
        Session storage session = sessions[agent];
        if (session.openPending >= maxOpenPendingPerAgent) {
            revert PendingLimitReached(agent);
        }

        uint256 id = nextPendingId++;
        uint48 expiresAt = uint48(block.timestamp) + pendingTtl;
        _pending[id] = PendingRequest({
            agent: agent,
            createdAt: uint48(block.timestamp),
            expiresAt: expiresAt,
            status: PendingStatus.Open,
            reason: reason,
            usdValue: usdValue,
            encodedCalls: abi.encode(calls)
        });
        session.openPending += 1;
        emit ApprovalRequested(id, agent, reason, usdValue, expiresAt);
    }

    function _resetWindowIfNeeded() internal {
        if (block.timestamp >= uint256(windowStart) + 24 hours) {
            windowStart = uint48(block.timestamp);
            spentInWindowUsd = 0;
        }
    }

    function _performCalls(Call[] memory calls) internal {
        for (uint256 i = 0; i < calls.length; ++i) {
            _performCall(i, calls[i]);
        }
    }

    function _performCall(uint256 index, Call memory call) internal {
        (bool success, bytes memory result) = call.target.call{value: call.value}(call.data);
        if (!success) revert ExternalCallFailed(index, result);
    }

    function _selector(bytes memory data) internal pure returns (bytes4 selector) {
        if (data.length < 4) return bytes4(0);
        assembly ("memory-safe") {
            selector := mload(add(data, 0x20))
        }
    }

    function _arguments(bytes memory data) internal pure returns (bytes memory result) {
        if (data.length < 4) revert InvalidTokenCall();
        result = new bytes(data.length - 4);
        for (uint256 i = 4; i < data.length; ++i) {
            result[i - 4] = data[i];
        }
    }
}
