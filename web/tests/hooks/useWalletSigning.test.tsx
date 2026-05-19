/**
 * V7-045 — useWalletSigning hook spec.
 *
 * Required assertions per V7-045 brief:
 *  1. 30s freshness gate refuses with SIM_STALE when simTimestamp is
 *     older than the threshold.
 *  2. Calldata-hash bind refuses with CALLDATA_MISMATCH when the
 *     recomputed hash diverges from the artifact's expected hash.
 *
 * Bonus happy-path: with a mocked low-level wallet primitive returning
 * a fake signature, sign() resolves with that signature.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useWalletSigning,
  SimStaleError,
  CalldataMismatchError,
  SIM_FRESHNESS_SECONDS,
} from '../../hooks/useWalletSigning';
import { computeCalldataHash } from '../../lib/signer';
import * as metamask from '../../lib/wallets/metamask';

vi.mock('../../lib/wallets/metamask', async (orig) => {
  const real = await orig<typeof import('../../lib/wallets/metamask')>();
  return {
    ...real,
    sendTransaction: vi.fn(async () => '0xFAKE_TX_HASH'),
    signPermit2Typed: vi.fn(async () => '0xFAKE_SIG'),
  };
});

describe('useWalletSigning (V7-045)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rejects with SIM_STALE when the simulation is older than 30s', async () => {
    const { result } = renderHook(() => useWalletSigning());
    const staleTs = Date.now() / 1000 - (SIM_FRESHNESS_SECONDS + 1); // 31s old
    const tx = { to: '0xabc', data: '0xdeadbeef' };
    const hash = await computeCalldataHash(tx);

    await act(async () => {
      await expect(
        result.current.sign({
          mode: 'evm_send',
          tx,
          simTimestamp: staleTs,
          expectedCalldataHash: hash,
        }),
      ).rejects.toMatchObject({
        name: 'SimStaleError',
        code: 'SIM_STALE',
      });
    });

    // Wallet primitive must never have been touched on a stale gate.
    expect(metamask.sendTransaction).not.toHaveBeenCalled();
    expect(result.current.error).toBeInstanceOf(SimStaleError);
  });

  it('rejects with CALLDATA_MISMATCH when broadcast hash diverges from expected', async () => {
    const { result } = renderHook(() => useWalletSigning());
    const freshTs = Date.now() / 1000; // now
    const tx = { to: '0xabc', data: '0xdeadbeef' };
    // Intentionally wrong expected hash so the bind check trips.
    const wrongHash = 'f'.repeat(64);

    await act(async () => {
      await expect(
        result.current.sign({
          mode: 'evm_send',
          tx,
          simTimestamp: freshTs,
          expectedCalldataHash: wrongHash,
        }),
      ).rejects.toMatchObject({
        name: 'CalldataMismatchError',
        code: 'CALLDATA_MISMATCH',
      });
    });

    expect(metamask.sendTransaction).not.toHaveBeenCalled();
    expect(result.current.error).toBeInstanceOf(CalldataMismatchError);
  });

  it('happy path: forwards to the wallet and returns the broadcast tx hash', async () => {
    const { result } = renderHook(() => useWalletSigning());
    const freshTs = Date.now() / 1000;
    const tx = { to: '0xabc', data: '0xdeadbeef' };
    const correctHash = await computeCalldataHash(tx);

    let outcome: Awaited<ReturnType<typeof result.current.sign>> | null = null;
    await act(async () => {
      outcome = await result.current.sign({
        mode: 'evm_send',
        tx,
        simTimestamp: freshTs,
        expectedCalldataHash: correctHash,
      });
    });

    expect(outcome).not.toBeNull();
    expect(outcome!.txId).toBe('0xFAKE_TX_HASH');
    expect(metamask.sendTransaction).toHaveBeenCalledTimes(1);
    expect(metamask.sendTransaction).toHaveBeenCalledWith(tx);
    expect(result.current.error).toBeNull();
  });

  it('typed-data happy path returns the wallet signature', async () => {
    const { result } = renderHook(() => useWalletSigning());
    const freshTs = Date.now() / 1000;
    const domain = {
      name: 'Permit2' as const,
      chainId: 1,
      verifyingContract: '0x000000000022D473030F116dDEE9F6B43aC78BA3',
    };
    const message = {
      details: {
        token: '0xaaa',
        amount: '1',
        expiration: '0',
        nonce: '0',
      },
      spender: '0xbbb',
      sigDeadline: '0',
    };
    // Hash the canonical payload shape the hook uses internally so
    // the bind passes.
    const payload = {
      to: domain.verifyingContract,
      data: JSON.stringify({ domain, message }),
    };
    const correctHash = await computeCalldataHash(payload);

    let outcome: Awaited<ReturnType<typeof result.current.sign>> | null = null;
    await act(async () => {
      outcome = await result.current.sign({
        mode: 'evm_typed_data',
        domain,
        message,
        simTimestamp: freshTs,
        expectedCalldataHash: correctHash,
      });
    });

    expect(outcome).not.toBeNull();
    expect(outcome!.signature).toBe('0xFAKE_SIG');
    expect(outcome!.txId).toBeNull();
    expect(metamask.signPermit2Typed).toHaveBeenCalledTimes(1);
  });
});
