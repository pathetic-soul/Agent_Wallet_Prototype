// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EntryPoint} from "@account-abstraction/contracts/core/EntryPoint.sol";

/// @dev Re-exports the reference EntryPoint so Forge builds its artifact for local demos.
contract DevEntryPoint is EntryPoint {}
