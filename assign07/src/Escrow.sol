// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title Escrow between a buyer, a seller and an arbiter (see docs/SPEC.md)
/// @notice Buyer funds an exact price. Buyer may release to the seller; buyer or seller may
///         dispute; the arbiter then resolves to one side. Before funding, buyer and seller
///         can mutually cancel. Payouts are pull payments: state transitions only record
///         credits, `withdraw()` moves ETH.
contract Escrow is ReentrancyGuard {
    enum State { Created, Funded, Released, Disputed, ResolvedToBuyer, ResolvedToSeller, Cancelled }

    // ---- errors
    error ZeroAddress();
    error RoleOverlap();
    error ZeroAmount();
    error Unauthorized();
    error InvalidState(State current);
    error WrongAmount(uint256 sent, uint256 expected);
    error AlreadyApproved();
    error NothingToWithdraw();
    error TransferFailed();
    error DirectPaymentNotAllowed();

    // ---- events
    event Funded(address indexed buyer, uint256 amount);
    event Released(address indexed seller, uint256 amount);
    event DisputeRaised(address indexed by);
    event Resolved(address indexed arbiter, address indexed beneficiary, uint256 amount);
    event CancelApproved(address indexed by);
    event Cancelled();
    event Withdrawn(address indexed to, uint256 amount);

    // ---- storage
    address public immutable buyer;
    address public immutable seller;
    address public immutable arbiter;
    uint256 public immutable amount;

    State public state;
    bool public buyerApprovedCancel;
    bool public sellerApprovedCancel;
    mapping(address => uint256) public owed; // pull-payment credits
    uint256 public totalOwed;                // sum of all credits not yet withdrawn

    constructor(address seller_, address arbiter_, uint256 amount_) {
        if (seller_ == address(0) || arbiter_ == address(0)) revert ZeroAddress();
        if (amount_ == 0) revert ZeroAmount();
        if (msg.sender == seller_ || msg.sender == arbiter_ || seller_ == arbiter_) revert RoleOverlap();
        buyer = msg.sender;
        seller = seller_;
        arbiter = arbiter_;
        amount = amount_;
    }

    // ---- modifiers
    modifier inState(State s) {
        if (state != s) revert InvalidState(state);
        _;
    }

    modifier onlyBuyer() {
        if (msg.sender != buyer) revert Unauthorized();
        _;
    }

    // ---- transitions
    /// Created -> Funded
    function fund() external payable onlyBuyer inState(State.Created) {
        if (msg.value != amount) revert WrongAmount(msg.value, amount);
        state = State.Funded;
        emit Funded(msg.sender, msg.value);
    }

    /// Funded -> Released (seller is credited)
    function release() external onlyBuyer inState(State.Funded) {
        state = State.Released;
        _credit(seller, amount);
        emit Released(seller, amount);
    }

    /// Funded -> Disputed (buyer or seller)
    function dispute() external inState(State.Funded) {
        if (msg.sender != buyer && msg.sender != seller) revert Unauthorized();
        state = State.Disputed;
        emit DisputeRaised(msg.sender);
    }

    /// Disputed -> ResolvedToBuyer | ResolvedToSeller (arbiter only)
    function resolve(bool toBuyer) external inState(State.Disputed) {
        if (msg.sender != arbiter) revert Unauthorized();
        address to = toBuyer ? buyer : seller;
        state = toBuyer ? State.ResolvedToBuyer : State.ResolvedToSeller;
        _credit(to, amount);
        emit Resolved(msg.sender, to, amount);
    }

    /// Created -> Cancelled once BOTH buyer and seller have approved.
    function approveCancel() external inState(State.Created) {
        if (msg.sender == buyer) {
            if (buyerApprovedCancel) revert AlreadyApproved();
            buyerApprovedCancel = true;
        } else if (msg.sender == seller) {
            if (sellerApprovedCancel) revert AlreadyApproved();
            sellerApprovedCancel = true;
        } else {
            revert Unauthorized();
        }
        emit CancelApproved(msg.sender);
        if (buyerApprovedCancel && sellerApprovedCancel) {
            state = State.Cancelled;
            emit Cancelled();
        }
    }

    // ---- pull payment
    /// Checks-effects-interactions + nonReentrant. Does not change `state`.
    function withdraw() external nonReentrant {
        uint256 value = owed[msg.sender];
        if (value == 0) revert NothingToWithdraw();
        owed[msg.sender] = 0;
        totalOwed -= value;
        emit Withdrawn(msg.sender, value);
        (bool ok,) = msg.sender.call{value: value}("");
        if (!ok) revert TransferFailed();
    }

    // ---- views
    /// ETH the contract must be able to pay: credits plus the escrowed amount while it is still in play.
    function liabilities() public view returns (uint256) {
        bool held = state == State.Funded || state == State.Disputed;
        return totalOwed + (held ? amount : 0);
    }

    function _credit(address to, uint256 value) private {
        owed[to] += value;
        totalOwed += value;
    }

    receive() external payable {
        revert DirectPaymentNotAllowed();
    }
}
