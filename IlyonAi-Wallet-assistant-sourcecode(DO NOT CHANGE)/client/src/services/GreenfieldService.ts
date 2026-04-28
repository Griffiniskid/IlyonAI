import {
  Client,
  VisibilityType,
  RedundancyType,
  Long,
  AuthType,
} from '@bnb-chain/greenfield-js-sdk';
import { computeChecksums, selectOptimalSp } from './spUtils';

// ---------------------------------------------------------------------------
// Testnet constants
// ---------------------------------------------------------------------------

const GRPC_URL =
  'https://gnfd-testnet-fullnode-tendermint-ap.bnbchain.org';
const GREENFIELD_CHAIN_ID = '5600';
const BNB_DENOM = 'BNB';

/** Key used to persist off-chain auth in chrome.storage.local */
const AUTH_STORAGE_KEY = 'greenfield_offchain_auth';

// ---------------------------------------------------------------------------
// Minimal EIP-1193 provider type (MetaMask / window.ethereum)
// ---------------------------------------------------------------------------

interface EthereumProvider {
  request(args: { method: 'eth_requestAccounts' }): Promise<string[]>;
  request(args: {
    method: 'eth_signTypedData_v4';
    params: [string, string];
  }): Promise<string>;
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
}

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

// ---------------------------------------------------------------------------
// Persisted auth shape
// ---------------------------------------------------------------------------

interface StoredAuth {
  address: string;
  seedString: string;
  expiresAt: number; // Unix ms
}

// ---------------------------------------------------------------------------
// GreenfieldManager
// ---------------------------------------------------------------------------

export class GreenfieldManager {
  private readonly client: ReturnType<typeof Client.create>;

  constructor() {
    this.client = Client.create(GRPC_URL, GREENFIELD_CHAIN_ID);
  }

  // -------------------------------------------------------------------------
  // Step 3 — Off-chain auth
  // -------------------------------------------------------------------------

  /**
   * Requests a wallet signature via window.ethereum to generate an EdDSA
   * key pair for off-chain authenticated SP requests, then persists the
   * result in chrome.storage.local.
   */
  async generateOffChainAuth(address: string): Promise<StoredAuth> {
    const ethereum = this.requireEthereum();

    // Fetch active storage providers from chain
    const { storageProviders } = await this.client.sp.getStorageProviders();

    // chrome-extension:// origin is the "domain" that SPs will whitelist
    const domain = `chrome-extension://${chrome.runtime.id}`;
    const expirationMs = 7 * 24 * 60 * 60 * 1000; // 7 days

    const authResult =
      await this.client.offchainauth.genOffChainAuthKeyPairAndUpload(
        {
          sps: storageProviders,
          chainId: GREENFIELD_CHAIN_ID,
          expirationMs,
          domain,
          address,
        },
        ethereum,
      );

    const stored: StoredAuth = {
      address,
      seedString: authResult.seedString,
      expiresAt: Date.now() + expirationMs,
    };

    await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: stored });
    return stored;
  }

  // -------------------------------------------------------------------------
  // Step 4 — Agent bucket
  // -------------------------------------------------------------------------

  /**
   * Ensures the user's agent bucket exists.  If headBucket returns a 404 /
   * error the bucket is created and the on-chain tx is broadcast via the
   * connected wallet.
   *
   * Bucket name rules: 3-63 chars, lowercase alphanumeric + hyphens.
   */
  async createAgentBucket(address: string): Promise<void> {
    const bucketName = this.bucketNameFor(address);

    const exists = await this.bucketExists(bucketName);
    if (exists) return;

    const ethereum = this.requireEthereum();

    const primarySp = await selectOptimalSp(this.client);

    const createBucketTx = await this.client.bucket.createBucket({
      bucketName,
      creator: address,
      visibility: VisibilityType.VISIBILITY_TYPE_PRIVATE,
      chargedReadQuota: Long.fromNumber(0),
      primarySpAddress: primarySp.operatorAddress,
      paymentAddress: address,
    });

    const simulateInfo = await createBucketTx.simulate({ denom: BNB_DENOM });

    await createBucketTx.broadcast({
      denom: BNB_DENOM,
      gasLimit: Number(simulateInfo.gasLimit),
      gasPrice: simulateInfo.gasPrice ?? '5000000000',
      payer: address,
      granter: '',
      signTypedDataCallback: async (addr: string, message: string) =>
        ethereum.request({
          method: 'eth_signTypedData_v4',
          params: [addr, message],
        }),
    });
  }

  // -------------------------------------------------------------------------
  // Step 5 — Save agent memory
  // -------------------------------------------------------------------------

  /**
   * Serialises `jsonPayload` as bytes, computes Reed-Solomon checksums,
   * creates the on-chain object metadata transaction, broadcasts it, then
   * uploads the actual bytes to the storage provider.
   *
   * Returns the object name that was created.
   *
   * Upload flow:
   *   1. encode bytes → checksums
   *   2. client.object.createObject  (on-chain metadata tx)
   *   3. simulate → broadcast  (waits for inclusion)
   *   4. client.object.uploadObject  (SP upload using txnHash)
   */
  async saveAgentMemory(address: string, jsonPayload: string): Promise<string> {
    const ethereum = this.requireEthereum();

    // Ensure bucket exists before writing
    await this.createAgentBucket(address);

    const bucketName = this.bucketNameFor(address);
    const objectName = `memory/agent-memory-${Date.now()}.json`;
    const bytes = new TextEncoder().encode(jsonPayload);
    const contentType = 'application/json';

    // --- Step 1: Reed-Solomon checksums ---
    const { expectChecksums, payloadSize } = await computeChecksums(bytes);

    // --- Step 2: Create object metadata tx ---
    const createObjectTx = await this.client.object.createObject({
      bucketName,
      objectName,
      creator: address,
      visibility: VisibilityType.VISIBILITY_TYPE_PRIVATE,
      contentType,
      redundancyType: RedundancyType.REDUNDANCY_EC_TYPE,
      payloadSize: Long.fromNumber(payloadSize),
      expectChecksums,
    });

    // --- Step 3: Simulate + broadcast ---
    const simulateInfo = await createObjectTx.simulate({ denom: BNB_DENOM });

    const broadcastRes = await createObjectTx.broadcast({
      denom: BNB_DENOM,
      gasLimit: Number(simulateInfo.gasLimit),
      gasPrice: simulateInfo.gasPrice ?? '5000000000',
      payer: address,
      granter: '',
      signTypedDataCallback: async (addr: string, message: string) =>
        ethereum.request({
          method: 'eth_signTypedData_v4',
          params: [addr, message],
        }),
    });

    if (broadcastRes.code !== 0) {
      throw new Error(
        `createObject tx failed: code=${broadcastRes.code} log=${broadcastRes.rawLog}`,
      );
    }

    // --- Step 4: Upload bytes to SP (requires confirmed txnHash) ---
    const auth = await this.requireAuth(address);
    const domain = `chrome-extension://${chrome.runtime.id}`;

    await this.client.object.uploadObject(
      {
        bucketName,
        objectName,
        body: new File([bytes], objectName, { type: contentType }),
        txnHash: broadcastRes.transactionHash,
      },
      {
        type: AuthType.AUTH_TYPE_EDDSA,
        seed: auth.seedString,
        domain,
        address,
      },
    );

    return objectName;
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  /** Lowercase 3-36 char bucket name derived from the wallet address. */
  private bucketNameFor(address: string): string {
    // EVM addresses are 42 chars (0x + 40 hex).  Strip 0x, lowercase, prefix.
    return `agent-${address.replace(/^0x/i, '').toLowerCase().slice(0, 30)}`;
  }

  private async bucketExists(bucketName: string): Promise<boolean> {
    try {
      await this.client.bucket.headBucket(bucketName);
      return true;
    } catch {
      return false;
    }
  }

  private requireEthereum(): EthereumProvider {
    if (!window.ethereum) {
      throw new Error(
        'No Ethereum provider found. Please install MetaMask.',
      );
    }
    return window.ethereum;
  }

  /** Load stored auth; re-generates if missing or expired. */
  private async requireAuth(address: string): Promise<StoredAuth> {
    const result = await chrome.storage.local.get(AUTH_STORAGE_KEY);
    const stored = result[AUTH_STORAGE_KEY] as StoredAuth | undefined;

    if (stored && stored.address === address && stored.expiresAt > Date.now()) {
      return stored;
    }

    return this.generateOffChainAuth(address);
  }
}
