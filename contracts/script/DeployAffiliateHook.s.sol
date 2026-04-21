// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

// ─────────────────────────────────────────────────────────────────────────────
// Usage:
//
//   export POOL_MANAGER_ADDRESS=0x...   # deployed ICLPoolManager
//   export DISTRIBUTOR_ADDRESS=0x...   # platform fee distributor contract
//   export TOKEN0=0x...                # currency0 (lower address, sorted)
//   export TOKEN1=0x...                # currency1 (higher address, sorted)
//   export INITIAL_SQRT_PRICE=79228162514264337593543950336  # 1:1 price
//   export PRIVATE_KEY=0x...
//
//   forge script contracts/script/DeployAffiliateHook.s.sol \
//     --rpc-url $RPC_URL \
//     --private-key $PRIVATE_KEY \
//     --broadcast \
//     --verify \
//     -vvvv
// ─────────────────────────────────────────────────────────────────────────────

import {Script, console} from "forge-std/Script.sol";

import {ICLPoolManager} from "infinity-core/src/pool-cl/interfaces/ICLPoolManager.sol";
import {PoolKey} from "infinity-core/src/types/PoolKey.sol";
import {Currency} from "infinity-core/src/types/Currency.sol";
import {LPFeeLibrary} from "infinity-core/src/libraries/LPFeeLibrary.sol";
import {CLPoolParametersHelper} from "infinity-core/src/pool-cl/libraries/CLPoolParametersHelper.sol";
import {IHooks} from "infinity-core/src/interfaces/IHooks.sol";

import {AffiliateHook} from "../AffiliateHook.sol";

/**
 * @title  DeployAffiliateHook
 * @notice Foundry script that:
 *           1. Deploys AffiliateHook.
 *           2. Reads the permissions bitmap from the hook itself.
 *           3. Encodes that bitmap into PoolKey.parameters alongside tick spacing.
 *           4. Initialises a new dynamic-fee CL pool with the hook attached.
 *
 * ──────────────────────────────────────────────────────────────────────────
 * PancakeSwap Infinity vs Uniswap V4 — key difference
 * ──────────────────────────────────────────────────────────────────────────
 *   In Uniswap V4 the hook permissions are encoded in specific ADDRESS BITS.
 *   In PancakeSwap Infinity the hook permissions are encoded in the first
 *   16 bits of PoolKey.parameters (the address has no special requirements).
 *
 *   Permissions used by AffiliateHook:
 *     afterInitialize       → bit  1  (0x0002)
 *     beforeSwap            → bit  6  (0x0040)
 *     beforeSwapReturnDelta → bit 10  (0x0400)
 *     ─────────────────────────────────────────
 *     Total bitmap:                    0x0442
 *
 *   Bits 16-39 of PoolKey.parameters encode the tick spacing for CL pools
 *   (set via CLPoolParametersHelper.setTickSpacing).
 * ──────────────────────────────────────────────────────────────────────────
 */
contract DeployAffiliateHook is Script {
    using CLPoolParametersHelper for bytes32;

    // ─── Pool configuration ───────────────────────────────────────────────────

    /// @dev Tick spacing for the concentrated-liquidity pool.
    ///      Common values: 1 (stable pairs), 10 (0.05%), 60 (0.30%), 200 (1%)
    int24 constant TICK_SPACING = 60;

    // ─── Script entry point ───────────────────────────────────────────────────

    function run() external {
        // ── 1. Load environment ───────────────────────────────────────────────
        address poolManagerAddr = vm.envAddress("POOL_MANAGER_ADDRESS");
        address distributorAddr = vm.envAddress("DISTRIBUTOR_ADDRESS");
        address token0Addr      = vm.envAddress("TOKEN0");
        address token1Addr      = vm.envAddress("TOKEN1");
        uint160 sqrtPriceX96   = uint160(vm.envUint("INITIAL_SQRT_PRICE"));

        // Sanity check: currency0 must have a lower address than currency1.
        require(
            token0Addr < token1Addr,
            "DeployAffiliateHook: TOKEN0 address must be < TOKEN1 address"
        );

        ICLPoolManager poolManager = ICLPoolManager(poolManagerAddr);

        // ── 2. Deploy AffiliateHook ───────────────────────────────────────────
        vm.startBroadcast();

        AffiliateHook hook = new AffiliateHook(poolManager, distributorAddr);
        console.log("AffiliateHook deployed at :", address(hook));

        // ── 3. Read permissions bitmap from the hook ──────────────────────────
        //
        // We read the bitmap directly from the deployed contract to avoid
        // hardcoding it here — the hook is the single source of truth.
        //
        uint16 permissionsBitmap = hook.getHooksRegistrationBitmap();
        console.log("Permissions bitmap (uint16):", permissionsBitmap);
        // Expected: 0x0442 = 1090
        //   bit  1 → afterInitialize
        //   bit  6 → beforeSwap
        //   bit 10 → beforeSwapReturnDelta

        // ── 4. Build PoolKey.parameters ───────────────────────────────────────
        //
        // Layout of bytes32 parameters (PancakeSwap Infinity CL pools):
        //   [bits 0-15 ] → hook permissions bitmap  (uint16)
        //   [bits 16-39] → tick spacing             (int24 via CLPoolParametersHelper)
        //   [bits 40+  ] → reserved / unused
        //
        bytes32 parameters = bytes32(uint256(permissionsBitmap))
            .setTickSpacing(TICK_SPACING);

        // ── 5. Assemble PoolKey ───────────────────────────────────────────────
        //
        // fee = DYNAMIC_FEE_FLAG (0x800000) is REQUIRED for:
        //   • lpFeeOverride in beforeSwap to take effect
        //   • poolManager.updateDynamicLPFee() calls from the hook
        //
        PoolKey memory poolKey = PoolKey({
            currency0:   Currency.wrap(token0Addr),
            currency1:   Currency.wrap(token1Addr),
            hooks:        IHooks(address(hook)),
            poolManager:  poolManager,
            fee:          LPFeeLibrary.DYNAMIC_FEE_FLAG, // 0x800000
            parameters:   parameters
        });

        // ── 6. Initialize pool ────────────────────────────────────────────────
        //
        // This triggers _afterInitialize on the hook, which calls
        // poolManager.updateDynamicLPFee(key, STANDARD_LP_FEE = 3000).
        //
        poolManager.initialize(poolKey, sqrtPriceX96);
        console.log("Pool initialised. sqrtPriceX96 =", sqrtPriceX96);

        vm.stopBroadcast();

        // ── 7. Summary ────────────────────────────────────────────────────────
        console.log("===========================================");
        console.log(" Deployment summary");
        console.log("===========================================");
        console.log(" Hook             :", address(hook));
        console.log(" PoolManager      :", poolManagerAddr);
        console.log(" Distributor      :", distributorAddr);
        console.log(" Currency0        :", token0Addr);
        console.log(" Currency1        :", token1Addr);
        console.log(" Fee (dynamic)    : 0x800000");
        console.log(" Tick spacing     :", uint256(uint24(TICK_SPACING)));
        console.log(" Permissions      :", permissionsBitmap);
        console.log("===========================================");
        console.log("");
        console.log(" Standard LP fee  : 0.30%  (set by _afterInitialize)");
        console.log(" Affiliate LP fee : 0.25%  (overridden in beforeSwap)");
        console.log(" Distributor cut  : 0.05%  (taken via BeforeSwapDelta)");
        console.log("===========================================");
    }
}
