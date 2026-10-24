// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Local-demo token with six decimals and an open mint. Never deploy outside a throwaway chain.
contract DevMockUSDC is ERC20 {
    constructor() ERC20("Dev USD Coin", "dUSDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
