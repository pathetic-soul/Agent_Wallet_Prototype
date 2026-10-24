// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract TicketShop {
    error IncorrectPrice();

    event TicketPurchased(uint256 indexed ticketId, address indexed buyer, address indexed attendee, uint256 price);

    uint256 public immutable ticketPrice;
    uint256 public nextTicketId = 1;
    mapping(uint256 ticketId => address attendee) public ticketOwner;

    constructor(uint256 ticketPrice_) {
        ticketPrice = ticketPrice_;
    }

    function buyTicket(address attendee) external payable returns (uint256 ticketId) {
        if (msg.value != ticketPrice) revert IncorrectPrice();
        ticketId = nextTicketId++;
        ticketOwner[ticketId] = attendee;
        emit TicketPurchased(ticketId, msg.sender, attendee, msg.value);
    }
}

