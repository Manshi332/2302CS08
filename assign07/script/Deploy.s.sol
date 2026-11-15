// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {Escrow} from "../src/Escrow.sol";

/// forge script script/Deploy.s.sol --rpc-url $RPC --private-key $BUYER_PK --broadcast
/// env: SELLER, ARBITER, AMOUNT (wei)
contract Deploy is Script {
    function run() external returns (Escrow e) {
        address seller = vm.envAddress("SELLER");
        address arbiter = vm.envAddress("ARBITER");
        uint256 amount = vm.envUint("AMOUNT");
        vm.startBroadcast();
        e = new Escrow(seller, arbiter, amount);
        vm.stopBroadcast();
        console.log("Escrow deployed at", address(e));
    }
}
