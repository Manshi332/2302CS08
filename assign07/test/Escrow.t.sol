// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Escrow} from "../src/Escrow.sol";

contract EscrowTest is Test {
    address buyer = makeAddr("buyer");
    address seller = makeAddr("seller");
    address arbiter = makeAddr("arbiter");
    uint256 constant AMT = 1 ether;
    Escrow e;

    event Funded(address indexed buyer, uint256 amount);
    event Released(address indexed seller, uint256 amount);
    event DisputeRaised(address indexed by);
    event Resolved(address indexed arbiter, address indexed beneficiary, uint256 amount);
    event CancelApproved(address indexed by);
    event Cancelled();
    event Withdrawn(address indexed to, uint256 amount);

    function setUp() public {
        vm.deal(buyer, 100 ether);
        e = _deploy(AMT);
    }

    function _deploy(uint256 amt) internal returns (Escrow) {
        vm.prank(buyer);
        return new Escrow(seller, arbiter, amt);
    }

    function _assertSolvent() internal view {
        assertGe(address(e).balance, e.liabilities());
    }

    // ------------------------------------------------ valid transitions
    function test_Created_to_Funded() public {
        vm.expectEmit(true, false, false, true);
        emit Funded(buyer, AMT);
        vm.prank(buyer);
        e.fund{value: AMT}();
        assertEq(uint8(e.state()), uint8(Escrow.State.Funded));
        assertEq(address(e).balance, AMT);
        _assertSolvent();
    }

    function test_Created_to_Cancelled_needs_both() public {
        vm.prank(buyer);
        e.approveCancel();
        assertEq(uint8(e.state()), uint8(Escrow.State.Created));
        vm.expectEmit(true, false, false, false);
        emit CancelApproved(seller);
        vm.expectEmit(false, false, false, false);
        emit Cancelled();
        vm.prank(seller);
        e.approveCancel();
        assertEq(uint8(e.state()), uint8(Escrow.State.Cancelled));
    }

    function test_Funded_to_Released_and_withdraw() public {
        _toFunded();
        vm.expectEmit(true, false, false, true);
        emit Released(seller, AMT);
        vm.prank(buyer);
        e.release();
        assertEq(uint8(e.state()), uint8(Escrow.State.Released));
        assertEq(seller.balance, 0, "pull payment: nothing sent yet");
        _assertSolvent();
        vm.expectEmit(true, false, false, true);
        emit Withdrawn(seller, AMT);
        vm.prank(seller);
        e.withdraw();
        assertEq(seller.balance, AMT);
        assertEq(address(e).balance, 0);
        _assertSolvent();
    }

    function test_Funded_to_Disputed_by_buyer_or_seller() public {
        _toFunded();
        vm.expectEmit(true, false, false, false);
        emit DisputeRaised(seller);
        vm.prank(seller);
        e.dispute();
        assertEq(uint8(e.state()), uint8(Escrow.State.Disputed));
        Escrow e2 = _deployFunded();
        vm.prank(buyer);
        e2.dispute();
        assertEq(uint8(e2.state()), uint8(Escrow.State.Disputed));
    }

    function test_Disputed_to_ResolvedToBuyer() public {
        _toDisputed();
        vm.expectEmit(true, true, false, true);
        emit Resolved(arbiter, buyer, AMT);
        vm.prank(arbiter);
        e.resolve(true);
        assertEq(uint8(e.state()), uint8(Escrow.State.ResolvedToBuyer));
        uint256 before = buyer.balance;
        vm.prank(buyer);
        e.withdraw();
        assertEq(buyer.balance, before + AMT);
        _assertSolvent();
    }

    function test_Disputed_to_ResolvedToSeller() public {
        _toDisputed();
        vm.prank(arbiter);
        e.resolve(false);
        assertEq(uint8(e.state()), uint8(Escrow.State.ResolvedToSeller));
        vm.prank(seller);
        e.withdraw();
        assertEq(seller.balance, AMT);
        assertEq(address(e).balance, 0);
    }

    // ------------------------------------------------ rejected transitions (full matrix)
    // functions: 0 fund, 1 release, 2 dispute, 3 resolve(true), 4 resolve(false), 5 approveCancel
    function _reach(Escrow x, uint8 s) internal {
        if (s == 0) return;
        if (s == 6) {
            vm.prank(buyer); x.approveCancel();
            vm.prank(seller); x.approveCancel();
            return;
        }
        vm.prank(buyer); x.fund{value: AMT}();
        if (s == 1) return;
        if (s == 2) { vm.prank(buyer); x.release(); return; }
        vm.prank(buyer); x.dispute();
        if (s == 3) return;
        vm.prank(arbiter); x.resolve(s == 4);
    }

    function _try(Escrow x, uint8 f) internal returns (bool ok, bytes memory ret) {
        if (f == 0) { vm.prank(buyer); (ok, ret) = address(x).call{value: AMT}(abi.encodeCall(Escrow.fund, ())); }
        else if (f == 1) { vm.prank(buyer); (ok, ret) = address(x).call(abi.encodeCall(Escrow.release, ())); }
        else if (f == 2) { vm.prank(buyer); (ok, ret) = address(x).call(abi.encodeCall(Escrow.dispute, ())); }
        else if (f == 3) { vm.prank(arbiter); (ok, ret) = address(x).call(abi.encodeCall(Escrow.resolve, (true))); }
        else if (f == 4) { vm.prank(arbiter); (ok, ret) = address(x).call(abi.encodeCall(Escrow.resolve, (false))); }
        else { vm.prank(seller); (ok, ret) = address(x).call(abi.encodeCall(Escrow.approveCancel, ())); }
    }

    function _allowed(uint8 s, uint8 f) internal pure returns (bool) {
        if (f == 0 || f == 5) return s == 0;            // fund / approveCancel only in Created
        if (f == 1 || f == 2) return s == 1;            // release / dispute only in Funded
        return s == 3;                                  // resolve only in Disputed
    }

    function test_transition_matrix() public {
        for (uint8 s = 0; s <= 6; s++) {
            for (uint8 f = 0; f <= 5; f++) {
                Escrow x = _deploy(AMT);
                _reach(x, s);
                (bool ok, bytes memory ret) = _try(x, f);
                assertEq(ok, _allowed(s, f), "matrix mismatch");
                if (!ok) {
                    assertEq(bytes4(ret), Escrow.InvalidState.selector, "wrong revert");
                }
            }
        }
    }

    function test_terminal_states_pay_only_once() public {
        _toFunded();
        vm.prank(buyer);
        e.release();
        vm.startPrank(seller);
        e.withdraw();
        vm.expectRevert(Escrow.NothingToWithdraw.selector);
        e.withdraw();
        vm.stopPrank();
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(Escrow.InvalidState.selector, Escrow.State.Released));
        e.release();
        vm.prank(arbiter);
        vm.expectRevert(abi.encodeWithSelector(Escrow.InvalidState.selector, Escrow.State.Released));
        e.resolve(true);
    }

    function test_cannot_fund_twice() public {
        _toFunded();
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(Escrow.InvalidState.selector, Escrow.State.Funded));
        e.fund{value: AMT}();
    }

    function test_withdraw_by_stranger_reverts() public {
        _toFunded();
        vm.prank(buyer);
        e.release();
        vm.prank(makeAddr("stranger"));
        vm.expectRevert(Escrow.NothingToWithdraw.selector);
        e.withdraw();
    }

    function test_double_cancel_approval_reverts() public {
        vm.startPrank(buyer);
        e.approveCancel();
        vm.expectRevert(Escrow.AlreadyApproved.selector);
        e.approveCancel();
        vm.stopPrank();
    }

    function test_direct_eth_rejected() public {
        (bool ok,) = address(e).call{value: 1}("");
        assertFalse(ok);
    }

    // ------------------------------------------------ constructor checks
    function test_constructor_rejects_zero_and_overlap() public {
        vm.startPrank(buyer);
        vm.expectRevert(Escrow.ZeroAddress.selector);
        new Escrow(address(0), arbiter, 1);
        vm.expectRevert(Escrow.ZeroAddress.selector);
        new Escrow(seller, address(0), 1);
        vm.expectRevert(Escrow.ZeroAmount.selector);
        new Escrow(seller, arbiter, 0);
        vm.expectRevert(Escrow.RoleOverlap.selector);
        new Escrow(buyer, arbiter, 1);
        vm.expectRevert(Escrow.RoleOverlap.selector);
        new Escrow(seller, buyer, 1);
        vm.expectRevert(Escrow.RoleOverlap.selector);
        new Escrow(seller, seller, 1);
        vm.stopPrank();
    }

    // ------------------------------------------------ reentrancy
    function test_reentrancy_on_withdraw() public {
        Attacker atk = new Attacker();
        vm.prank(buyer);
        Escrow x = new Escrow(address(atk), arbiter, AMT);
        atk.setTarget(x);
        vm.prank(buyer);
        x.fund{value: AMT}();
        vm.prank(buyer);
        x.release();
        // fund another victim escrow balance so a successful re-entry would be profitable
        vm.deal(address(x), address(x).balance + 5 ether); // forced extra ether
        atk.attack();
        assertEq(address(atk).balance, AMT, "attacker got exactly its credit");
        assertTrue(atk.reentered());
        assertFalse(atk.reentrySucceeded());
        assertEq(address(x).balance, 5 ether);
    }

    // ------------------------------------------------ fuzz: amounts
    function testFuzz_full_release_flow(uint96 amt) public {
        amt = uint96(bound(amt, 1, 50 ether));
        Escrow x = _deploy(amt);
        vm.deal(buyer, amt);
        vm.prank(buyer);
        x.fund{value: amt}();
        assertEq(address(x).balance, amt);
        vm.prank(buyer);
        x.release();
        assertEq(x.liabilities(), amt);
        vm.prank(seller);
        x.withdraw();
        assertEq(seller.balance, amt);
        assertEq(address(x).balance, 0);
        assertEq(x.liabilities(), 0);
    }

    function testFuzz_dispute_flow(uint96 amt, bool toBuyer, bool sellerDisputes) public {
        amt = uint96(bound(amt, 1, 50 ether));
        Escrow x = _deploy(amt);
        vm.deal(buyer, amt);
        vm.prank(buyer);
        x.fund{value: amt}();
        vm.prank(sellerDisputes ? seller : buyer);
        x.dispute();
        vm.prank(arbiter);
        x.resolve(toBuyer);
        address winner = toBuyer ? buyer : seller;
        uint256 before = winner.balance;
        vm.prank(winner);
        x.withdraw();
        assertEq(winner.balance, before + amt);
        assertEq(address(x).balance, 0);
        assertEq(x.owed(toBuyer ? seller : buyer), 0);
    }

    function testFuzz_wrong_amount_reverts(uint96 amt, uint96 sent) public {
        amt = uint96(bound(amt, 1, 50 ether));
        vm.assume(sent != amt);
        Escrow x = _deploy(amt);
        vm.deal(buyer, uint256(sent));
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(Escrow.WrongAmount.selector, uint256(sent), uint256(amt)));
        x.fund{value: sent}();
        assertEq(uint8(x.state()), uint8(Escrow.State.Created));
    }

    // ------------------------------------------------ fuzz: caller roles
    function testFuzz_only_buyer_can_fund_or_release(address caller) public {
        vm.assume(caller != buyer);
        vm.deal(caller, AMT);
        vm.prank(caller);
        vm.expectRevert(Escrow.Unauthorized.selector);
        e.fund{value: AMT}();
        _toFunded();
        vm.prank(caller);
        vm.expectRevert(Escrow.Unauthorized.selector);
        e.release();
    }

    function testFuzz_only_parties_can_dispute(address caller) public {
        vm.assume(caller != buyer && caller != seller);
        _toFunded();
        vm.prank(caller);
        vm.expectRevert(Escrow.Unauthorized.selector);
        e.dispute();
    }

    function testFuzz_only_arbiter_can_resolve(address caller, bool toBuyer) public {
        vm.assume(caller != arbiter);
        _toDisputed();
        vm.prank(caller);
        vm.expectRevert(Escrow.Unauthorized.selector);
        e.resolve(toBuyer);
    }

    function testFuzz_only_parties_can_approve_cancel(address caller) public {
        vm.assume(caller != buyer && caller != seller);
        vm.prank(caller);
        vm.expectRevert(Escrow.Unauthorized.selector);
        e.approveCancel();
    }

    function testFuzz_constructor_roles(address s, address a, uint256 amt) public {
        vm.assume(s != address(0) && a != address(0) && amt > 0);
        vm.prank(buyer);
        if (s == buyer || a == buyer || s == a) {
            vm.expectRevert(Escrow.RoleOverlap.selector);
        }
        new Escrow(s, a, amt);
    }

    // ------------------------------------------------ helpers
    function _toFunded() internal {
        vm.prank(buyer);
        e.fund{value: AMT}();
    }

    function _toDisputed() internal {
        _toFunded();
        vm.prank(buyer);
        e.dispute();
    }

    function _deployFunded() internal returns (Escrow x) {
        x = _deploy(AMT);
        vm.prank(buyer);
        x.fund{value: AMT}();
    }
}

contract Attacker {
    Escrow public target;
    bool public reentered;
    bool public reentrySucceeded;

    function setTarget(Escrow t) external { target = t; }

    function attack() external { target.withdraw(); }

    receive() external payable {
        if (!reentered) {
            reentered = true;
            try target.withdraw() { reentrySucceeded = true; } catch {}
        }
    }
}
