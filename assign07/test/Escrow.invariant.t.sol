// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {Escrow} from "../src/Escrow.sol";

/// Calls random actions from random actors and checks the accounting after every call.
contract Handler is Test {
    Escrow public e;
    address[4] public actors;
    uint256 public withdrawnTotal;

    constructor(Escrow e_, address[4] memory a) {
        e = e_;
        actors = a;
    }

    function _a(uint256 i) internal view returns (address) { return actors[i % 4]; }

    function fund(uint256 who) external {
        address a = _a(who);
        uint256 amt = e.amount();      // read first: a prank applies only to the very next external call
        vm.deal(a, amt);
        vm.prank(a);
        try e.fund{value: amt}() {} catch {}
    }
    function release(uint256 who) external { vm.prank(_a(who)); try e.release() {} catch {} }
    function dispute(uint256 who) external { vm.prank(_a(who)); try e.dispute() {} catch {} }
    function resolve(uint256 who, bool b) external { vm.prank(_a(who)); try e.resolve(b) {} catch {} }
    function approveCancel(uint256 who) external { vm.prank(_a(who)); try e.approveCancel() {} catch {} }
    function withdraw(uint256 who) external {
        address a = _a(who);
        uint256 before = a.balance;
        vm.prank(a);
        try e.withdraw() { withdrawnTotal += a.balance - before; } catch {}
    }
}

contract EscrowInvariantTest is StdInvariant, Test {
    Escrow e;
    Handler h;

    function setUp() public {
        address buyer = makeAddr("buyer");
        address seller = makeAddr("seller");
        address arbiter = makeAddr("arbiter");
        address stranger = makeAddr("stranger");
        vm.prank(buyer);
        e = new Escrow(seller, arbiter, 1 ether);
        h = new Handler(e, [buyer, seller, arbiter, stranger]);
        targetContract(address(h));
    }

    /// contract balance and recorded liabilities agree (no forced ether in this test, so equal)
    function invariant_balance_equals_liabilities() public view {
        assertEq(address(e).balance, e.liabilities());
    }

    function invariant_never_pays_out_more_than_amount() public view {
        assertLe(h.withdrawnTotal(), e.amount());
    }

    function invariant_terminal_states_hold_no_escrowed_funds_beyond_credits() public view {
        Escrow.State s = e.state();
        if (s == Escrow.State.Cancelled) assertEq(address(e).balance, 0);
        if (s == Escrow.State.Created) assertEq(address(e).balance, 0);
    }
}
