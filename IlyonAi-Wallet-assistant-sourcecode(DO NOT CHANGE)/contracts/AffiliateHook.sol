// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

// ─────────────────────────────────────────────────────────────────────────────
// DEPENDENCIES (install with Foundry):
//
//   forge install pancakeswap/pancake-v4-core
//   forge install pancakeswap/infinity-hooks
//   forge install OpenZeppelin/openzeppelin-contracts
//
// remappings.txt (add to your project root):
//
//   pancake-v4-core/=lib/pancake-v4-core/
//   infinity-core/=lib/pancake-v4-core/
//   @pancakeswap/v4-hooks/=lib/infinity-hooks/src/
//   @openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
// ─────────────────────────────────────────────────────────────────────────────

// BaseHook — copy from pancakeswap/infinity-hooks or install the package.
// Path may differ depending on your setup; adjust if needed.
import {CLBaseHook} from "@pancakeswap/v4-hooks/pool-cl/CLBaseHook.sol";

import {ICLPoolManager} from "infinity-core/src/pool-cl/interfaces/ICLPoolManager.sol";
import {IVault} from "infinity-core/src/interfaces/IVault.sol";
import {PoolKey} from "infinity-core/src/types/PoolKey.sol";
import {BalanceDelta} from "infinity-core/src/types/BalanceDelta.sol";
import {
    BeforeSwapDelta,
    BeforeSwapDeltaLibrary,
    toBeforeSwapDelta
} from "infinity-core/src/types/BeforeSwapDelta.sol";
import {LPFeeLibrary} from "infinity-core/src/libraries/LPFeeLibrary.sol";
import {Currency, CurrencyLibrary} from "infinity-core/src/types/Currency.sol";

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title  AffiliateHook
 * @notice PancakeSwap V4 (Infinity) Concentrated-Liquidity hook that detects
 *         affiliate swaps via `hookData`, applies a reduced LP-fee override,
 *         and routes a platform distributor cut to a designated distributor
 *         contract.
 *
 * ──────────────────────────────────────────────────────────────────────────
 * Architecture overview
 * ──────────────────────────────────────────────────────────────────────────
 *
 *  Pool setup
 *  ├─ Pool fee field MUST equal LPFeeLibrary.DYNAMIC_FEE_FLAG (0x800000)
 *  ├─ After initialization _afterInitialize sets the default stored fee
 *  └─ PoolKey.parameters (first 16 bits) carries the permissions bitmap
 *
 *  Affiliate detection (hookData encoding)
 *  ├─ Empty / len < 32  → normal swap
 *  └─ abi.encode(bool)  → affiliate if true
 *
 *  Fee flow for affiliate swaps
 *  ├─ LP fee overridden to AFFILIATE_LP_FEE (lower rate, user incentive)
 *  ├─ DISTRIBUTOR_FEE taken from input amount via BeforeSwapDelta
 *  └─ Distributor cut accumulated in pendingFees[currency]
 *
 *  Vault accounting for BeforeSwapDelta
 *  ├─ Returning a positive specifiedDelta causes the vault to credit the hook
 *  │  with that token amount (taken from the user's input before the swap).
 *  └─ distributeFeesFor() opens a new vault lock and calls vault.take() to
 *     spend that credit, forwarding tokens to the distributorContract.
 */
contract AffiliateHook is CLBaseHook, Ownable {
    using LPFeeLibrary for uint24;
    using CurrencyLibrary for Currency;
    using SafeERC20 for IERC20;

    // ─── Fee constants (PancakeSwap V4 fee scale: 1_000_000 = 100%) ───────────

    /// @notice LP fee applied to non-affiliate swaps (stored in pool at init).
    uint24 public constant STANDARD_LP_FEE = 3000; // 0.30 %

    /// @notice LP fee override for affiliate swaps — reduced as user incentive.
    uint24 public constant AFFILIATE_LP_FEE = 2500; // 0.25 %

    /// @notice Distributor cut taken on top of the LP fee for affiliate swaps.
    ///         Expressed in the same scale as LP fees (1_000_000 = 100%).
    uint24 public constant DISTRIBUTOR_FEE = 500;   // 0.05 %

    uint256 private constant FEE_DENOMINATOR = 1_000_000;

    // ─── State ────────────────────────────────────────────────────────────────

    /// @notice Contract that receives platform fee distributions.
    address public distributorContract;

    /**
     * @notice Unclaimed fees per currency, accumulated from affiliate swaps.
     * @dev    These tokens are held as credits in the Vault (not in this
     *         contract's token balance). distributeFeesFor() spends the credits.
     */
    mapping(Currency => uint256) public pendingFees;

    // ─── Events ───────────────────────────────────────────────────────────────

    event AffiliateSwapRecorded(
        address indexed sender,
        Currency indexed feeCurrency,
        uint256 distributorCut
    );
    event DistributorUpdated(
        address indexed oldDistributor,
        address indexed newDistributor
    );
    event FeesDistributed(Currency indexed currency, uint256 amount);

    // ─── Errors ───────────────────────────────────────────────────────────────

    error InvalidDistributor();
    error NoFeesToDistribute();

    // ─── Constructor ──────────────────────────────────────────────────────────

    /**
     * @param _poolManager  Deployed ICLPoolManager address.
     * @param _distributor  Initial distributor contract address.
     */
    constructor(ICLPoolManager _poolManager, address _distributor)
        CLBaseHook(_poolManager)
        Ownable(msg.sender)
    {
        if (_distributor == address(0)) revert InvalidDistributor();
        distributorContract = _distributor;
    }

    // ─── Hook permissions bitmap ──────────────────────────────────────────────

    /**
     * @notice Returns the permissions bitmap stored in the first 16 bits of
     *         PoolKey.parameters during pool registration.
     *
     *         Bits enabled:
     *           afterInitialize       (bit  1)  → set initial stored fee
     *           beforeSwap            (bit  6)  → detect affiliate & override fee
     *           beforeSwapReturnDelta (bit 10)  → take distributor cut via delta
     *
     *         Resulting bitmap: (1<<1) | (1<<6) | (1<<10) = 0x0442
     */
    function getHooksRegistrationBitmap()
        external
        pure
        override
        returns (uint16)
    {
        return _hooksRegistrationBitmapFrom(
            Permissions({
                beforeInitialize:              false,
                afterInitialize:               true,   // bit 1
                beforeAddLiquidity:            false,
                afterAddLiquidity:             false,
                beforeRemoveLiquidity:         false,
                afterRemoveLiquidity:          false,
                beforeSwap:                    true,   // bit 6
                afterSwap:                     false,
                beforeDonate:                  false,
                afterDonate:                   false,
                beforeSwapReturnDelta:         true,   // bit 10
                afterSwapReturnDelta:          false,
                afterAddLiquidityReturnDelta:  false,
                afterRemoveLiquidityReturnDelta: false
            })
        );
    }

    // ─── Hook callbacks ───────────────────────────────────────────────────────

    /**
     * @dev Called once right after the pool is created.
     *      Sets the initial stored LP fee so the pool starts at STANDARD_LP_FEE.
     *      Requires pool fee == LPFeeLibrary.DYNAMIC_FEE_FLAG in PoolKey.
     */
    function _afterInitialize(
        address,
        PoolKey calldata key,
        uint160,
        int24
    ) internal override returns (bytes4) {
        poolManager.updateDynamicLPFee(key, STANDARD_LP_FEE);
        return this.afterInitialize.selector;
    }

    /**
     * @dev Core hook logic — called before every swap.
     *
     *      Step 1  Decode hookData.
     *              • Empty / len < 32 → normal swap (no override, no delta).
     *              • abi.encode(true) → affiliate swap.
     *
     *      Step 2  (Affiliate only) Override LP fee via lpFeeOverride.
     *              Requires OVERRIDE_FEE_FLAG | AFFILIATE_LP_FEE.
     *
     *      Step 3  (Affiliate only, exact-input only) Compute distributor cut
     *              as DISTRIBUTOR_FEE / FEE_DENOMINATOR of the input amount
     *              and return it as a positive BeforeSwapDelta on the specified
     *              (input) side.  The vault credits the hook with this amount;
     *              it is tracked in pendingFees[feeCurrency] for later payout.
     *
     * @return selector    Must equal this.beforeSwap.selector.
     * @return delta       Tokens the hook claims from the swap input.
     * @return feeOverride OVERRIDE_FEE_FLAG | new_fee, or 0 for no override.
     */
    function _beforeSwap(
        address sender,
        PoolKey calldata key,
        ICLPoolManager.SwapParams calldata params,
        bytes calldata hookData
    ) internal override returns (bytes4, BeforeSwapDelta, uint24) {

        // ── Step 1: Decode affiliate flag ─────────────────────────────────────
        bool isAffiliate;
        if (hookData.length >= 32) {
            isAffiliate = abi.decode(hookData, (bool));
        }

        if (!isAffiliate) {
            // Normal swap: no LP-fee override, no distributor cut.
            return (
                this.beforeSwap.selector,
                BeforeSwapDeltaLibrary.ZERO_DELTA,
                0
            );
        }

        // ── Step 2: Build LP fee override ────────────────────────────────────
        uint24 feeOverride = LPFeeLibrary.OVERRIDE_FEE_FLAG | AFFILIATE_LP_FEE;

        // ── Step 3: Distributor cut (exact-input swaps only) ─────────────────
        // amountSpecified > 0  →  exact-input  (we know the input amount)
        // amountSpecified < 0  →  exact-output (input unknown; skip distributor)
        if (params.amountSpecified <= 0) {
            return (
                this.beforeSwap.selector,
                BeforeSwapDeltaLibrary.ZERO_DELTA,
                feeOverride
            );
        }

        uint256 inputAmount  = uint256(params.amountSpecified);
        uint256 distributorCut = (inputAmount * DISTRIBUTOR_FEE) / FEE_DENOMINATOR;

        if (distributorCut == 0) {
            return (
                this.beforeSwap.selector,
                BeforeSwapDeltaLibrary.ZERO_DELTA,
                feeOverride
            );
        }

        // Input currency: currency0 for zeroForOne, currency1 for oneForZero.
        Currency feeCurrency = params.zeroForOne ? key.currency0 : key.currency1;

        // Accumulate for distribution. Tokens are held as a vault credit.
        pendingFees[feeCurrency] += distributorCut;

        emit AffiliateSwapRecorded(sender, feeCurrency, distributorCut);

        // toBeforeSwapDelta(specifiedDelta, unspecifiedDelta)
        // Positive specifiedDelta → hook takes tokens from the input side.
        BeforeSwapDelta delta = toBeforeSwapDelta(
            int128(uint128(distributorCut)),
            0
        );

        return (this.beforeSwap.selector, delta, feeOverride);
    }

    // ─── Fee distribution ─────────────────────────────────────────────────────

    /**
     * @notice Distributes all accrued platform fees for `currency` to the
     *         distributor contract.
     *
     *         This function acquires a vault lock, calls vault.take() to spend
     *         the hook's accumulated vault credit (built up via BeforeSwapDelta
     *         across many swaps), and forwards the tokens to distributorContract.
     *
     *         Callable by anyone; permissionless distribution keeps the protocol
     *         trustless and allows keepers / the distributor itself to trigger it.
     *
     * @param currency Token to distribute. Use CurrencyLibrary.NATIVE for BNB.
     */
    function distributeFeesFor(Currency currency) external {
        uint256 amount = pendingFees[currency];
        if (amount == 0) revert NoFeesToDistribute();

        // Clear before re-entry (CEI pattern).
        pendingFees[currency] = 0;

        // Acquire a vault lock so we can call vault.take() safely.
        // The vault will call lockAcquired(data) on this contract, which then
        // delegates to _settleDistribution via address(this).call(data).
        vault.lock(
            abi.encodeCall(this._settleDistribution, (currency, amount))
        );

        emit FeesDistributed(currency, amount);
    }

    /**
     * @dev Executed inside the vault's lock context via lockAcquired.
     *      Spends the hook's vault credit and sends tokens to the distributor.
     *
     *      selfOnly modifier ensures this can ONLY be called via lockAcquired
     *      (i.e. msg.sender == address(this)), preventing external abuse.
     *
     * @param currency Token to withdraw.
     * @param amount   Exact amount to forward to distributorContract.
     */
    function _settleDistribution(Currency currency, uint256 amount)
        external
        selfOnly
    {
        // vault.take() withdraws `amount` of `currency` from the vault to
        // `distributorContract`, spending the hook's previously accumulated
        // credit.  If credit < amount the vault reverts the entire lock.
        vault.take(currency, distributorContract, amount);
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

    /**
     * @notice Updates the distributor contract address.
     * @param newDistributor New recipient of platform fee distributions.
     */
    function setDistributor(address newDistributor) external onlyOwner {
        if (newDistributor == address(0)) revert InvalidDistributor();
        emit DistributorUpdated(distributorContract, newDistributor);
        distributorContract = newDistributor;
    }

    /// @dev Accept native BNB sent directly to this contract.
    receive() external payable {}
}
