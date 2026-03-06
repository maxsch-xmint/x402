import { describe, it, expect, vi } from "vitest";
import {
  getBase64Encoder,
  getTransactionDecoder,
  getCompiledTransactionMessageDecoder,
  decompileTransactionMessage,
  type Address,
} from "@solana/kit";
import { TOKEN_PROGRAM_ADDRESS } from "@solana-program/token";
import { isSwigTransaction, parseSwigTransaction } from "../../src/utils";
import { normalizeTransaction } from "../../src/normalizer";
import { ExactSvmScheme } from "../../src/exact/facilitator/scheme";
import type { FacilitatorSvmSigner } from "../../src/signer";
import type { PaymentPayload, PaymentRequirements } from "@x402/core/types";
import { SOLANA_DEVNET_CAIP2, USDC_DEVNET_ADDRESS } from "../../src/constants";

// Real confirmed Swig smart wallet USDC transfer on devnet with fee transfer
// tx: XKr5pqRHyvh1LXfEPbRcNRJnXoQ1LHBFRy25h2MPR45gG9HXCokSqw1vdSK6bMPzNVGJDARkMqXSJdbMz9U4vUN
// Contains 2 TransferChecked: merchant payment (1 USDC) + treasury fee (530 raw USDC)
// Uses an Address Lookup Table (ALT)
const REAL_SWIG_FEE_TX_BASE64 =
  "AhomrL2mhzI266oxGvibsSPwbGehiAj5dTairmeoUUxm5ndmXaKO9dnuho4yyD9j2SC8HyeCJ5Z4R4CzANSHJw9lTDRXSJfc8hnCmFdmDU2/wbxPE17BWC1/RJynEvCQtTUax4gcY7shMILIVUoD66Zzlbr+g2M/gm5MoFi2zvIOgAIBAwqZaoBA6PatAWpRvzksIlZIPBdwhETOtNqkgD0atmy0IupxmwFv0RBlHICES9rmToevW5l26rO4tAKBVKHpssHDPZHUnTCwsjJXxllTS5mu5oo6DcIi9P49lmiwxI/txFoeHPDMiy7/r3OLF/tlUqbaReCyBqu9GP11DpJAVoKVRjCbzjBy9aohOjeIENr1QZZ/AfpmFYZ1/alN4E9vtadvR9vYJ/mdYtQCwjHG4qEnHy5dk1aTy18yajQmI5q+CHt+o2lX5ca1zNVcdXZ9Jk+8k4JitaZit+6iX4Ck+mK93gMGRm/lIRcy/+ytunLDm+e8jOW7xfcSayxDmzpAAAAADQzpQuHnxQbiGN8NffHFL6/cNSnkjWdNHbJMdbVMzL47RCyzkSFX8TqTPQE0KC0DK1/+zQGi2/G3eQYI3wAup6oqdg/Bn1+vi2z5kPhad7qgn9TuiFfo+4qAWv7oCLwWAwcACQNkAAAAAAAAAAcABQKAGgYACAkCAwEKBAkFCgYuCwAlAAAAAAACAwQEBQYBCgAMAQAAAAAAAAAGBwQEBQgBCgAMEgIAAAAAAAAGAgGgdR5RdrVXonVRX7x2E50xA6Ssx93cJ6CFqANSV6MxwwABBQ==";

const FEE_PAYER = "BKsZvzPUY6VT2GpLMxx6fA6fuC8MK3hVxwdjK8yqmqSR";
const SWIG_PDA = "59LqtErLXz2hxyQsv2vyck6D9iXepEMgfoBjtDULKtX3";
const PAY_TO = "EWVTHwKNzJRzRDb9jmZ89eq7X9KTygmRyBhoDj1pUmFW";
const MERCHANT_ATA = "5qWNvco9re9nodJmkyy7sne99FpwBcBSdXZUQx5igjmt";
const TREASURY_ATA = "9XLtjGT6N4UXzkpMqHLmc3h895NhYZAjYiNNz3EChPb3";
const USDC_MINT = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU";

// ALT resolution: BoMp5p92bn66NYsdZu28bs4RA5UTGsWi2xnJrFiYZ9YE, index 5 = Token Program
const ALT_ADDRESS = "BoMp5p92bn66NYsdZu28bs4RA5UTGsWi2xnJrFiYZ9YE";
const TOKEN_PROGRAM_ADDR = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

function decodeRealTx() {
  const base64Encoder = getBase64Encoder();
  const transactionBytes = base64Encoder.encode(REAL_SWIG_FEE_TX_BASE64);
  const transactionDecoder = getTransactionDecoder();
  return transactionDecoder.decode(transactionBytes);
}

function decompileRealTx() {
  const transaction = decodeRealTx();
  const compiled = getCompiledTransactionMessageDecoder().decode(transaction.messageBytes);

  // This tx has an ALT. Provide the lookup table addresses directly for offline decompilation.
  const addressesByLookupTableAddress: Record<string, Address[]> = {
    [ALT_ADDRESS]: [
      // index 0-4 are unused by this tx, fill with placeholders
      "11111111111111111111111111111111" as Address,
      "11111111111111111111111111111111" as Address,
      "11111111111111111111111111111111" as Address,
      "11111111111111111111111111111111" as Address,
      "11111111111111111111111111111111" as Address,
      // index 5 = Token Program
      TOKEN_PROGRAM_ADDR as Address,
    ],
  };

  const decompiled = decompileTransactionMessage(compiled, {
    addressesByLookupTableAddress,
  });
  return {
    transaction,
    compiled,
    decompiled,
    instructions: decompiled.instructions ?? [],
    staticAccounts: compiled.staticAccounts ?? [],
  };
}

describe("Swig transaction with fee transfer (multi-TransferChecked)", () => {
  describe("isSwigTransaction", () => {
    it("should detect as Swig", () => {
      const { instructions } = decompileRealTx();
      expect(isSwigTransaction(instructions)).toBe(true);
    });
  });

  describe("parseSwigTransaction", () => {
    it("should flatten to 4 instructions", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      expect(result.instructions).toHaveLength(4);
    });

    it("should extract correct swig PDA", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      expect(result.swigPda).toBe(SWIG_PDA);
    });

    it("should have instruction layout: [ComputeLimit, ComputePrice, TransferChecked, TransferChecked]", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      // [0] SetComputeUnitLimit (disc=2)
      expect(result.instructions[0].data[0]).toBe(2);
      // [1] SetComputeUnitPrice (disc=3)
      expect(result.instructions[1].data[0]).toBe(3);
      // [2] TransferChecked (disc=12) — merchant payment
      expect(result.instructions[2].data[0]).toBe(12);
      // [3] TransferChecked (disc=12) — fee transfer
      expect(result.instructions[3].data[0]).toBe(12);
    });

    it("should have merchant transfer amount=1 (instruction 2)", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      const data = result.instructions[2].data;
      const amount = new DataView(data.buffer, data.byteOffset).getBigUint64(1, true);
      expect(amount).toBe(1n);
    });

    it("should have fee transfer amount=530 (instruction 3)", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      const data = result.instructions[3].data;
      const amount = new DataView(data.buffer, data.byteOffset).getBigUint64(1, true);
      expect(amount).toBe(530n);
    });

    it("merchant transfer destination should be merchant ATA", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      // TransferChecked accounts: [source, mint, destination, authority]
      const destAddress = result.instructions[2].accounts[2].address.toString();
      expect(destAddress).toBe(MERCHANT_ATA);
    });

    it("fee transfer destination should be treasury ATA", async () => {
      const { instructions, staticAccounts } = decompileRealTx();
      const result = await parseSwigTransaction(instructions, staticAccounts);
      const destAddress = result.instructions[3].accounts[2].address.toString();
      expect(destAddress).toBe(TREASURY_ATA);
    });
  });

  describe("normalizeTransaction", () => {
    it("should return swig PDA as payer", async () => {
      const { transaction, instructions, staticAccounts } = decompileRealTx();
      const normalized = await normalizeTransaction(instructions, staticAccounts, transaction);
      expect(normalized.payer).toBe(SWIG_PDA);
    });

    it("should return 4 instructions", async () => {
      const { transaction, instructions, staticAccounts } = decompileRealTx();
      const normalized = await normalizeTransaction(instructions, staticAccounts, transaction);
      expect(normalized.instructions).toHaveLength(4);
    });
  });

  describe("verify pipeline", () => {
    it("should verify as valid with mock signer (no ALT needed after normalization)", async () => {
      // The verify() method needs to decompile the transaction.
      // Since this tx has an ALT, verify() will try to fetch it via RPC.
      // We mock the module to bypass ALT resolution for unit testing.
      const { decompileTransactionMessageFetchingLookupTables: _original } = await import("@solana/kit");

      // Build the decompiled instructions manually (same as decompileRealTx)
      const transaction = decodeRealTx();
      const compiled = getCompiledTransactionMessageDecoder().decode(transaction.messageBytes);

      const addressesByLookupTableAddress: Record<string, Address[]> = {
        [ALT_ADDRESS]: [
          "11111111111111111111111111111111" as Address,
          "11111111111111111111111111111111" as Address,
          "11111111111111111111111111111111" as Address,
          "11111111111111111111111111111111" as Address,
          "11111111111111111111111111111111" as Address,
          TOKEN_PROGRAM_ADDR as Address,
        ],
      };

      // Mock the @solana/kit module to provide ALT data without RPC
      vi.doMock("@solana/kit", async (importOriginal) => {
        const original = await importOriginal<typeof import("@solana/kit")>();
        return {
          ...original,
          decompileTransactionMessageFetchingLookupTables: async (
            compiledMsg: unknown,
            _rpc: unknown,
          ) => {
            return original.decompileTransactionMessage(compiledMsg as never, {
              addressesByLookupTableAddress,
            });
          },
        };
      });

      // Re-import scheme after mocking
      const { ExactSvmScheme: MockedScheme } = await import(
        "../../src/exact/facilitator/scheme"
      );

      const mockSigner: FacilitatorSvmSigner = {
        getAddresses: vi.fn().mockReturnValue([FEE_PAYER]) as never,
        signTransaction: vi.fn().mockResolvedValue(REAL_SWIG_FEE_TX_BASE64) as never,
        simulateTransaction: vi.fn().mockResolvedValue(undefined) as never,
        sendTransaction: vi.fn().mockResolvedValue("mockSignature123") as never,
        confirmTransaction: vi.fn().mockResolvedValue(undefined) as never,
      };

      const scheme = new MockedScheme(mockSigner);

      const requirements: PaymentRequirements = {
        scheme: "exact",
        network: SOLANA_DEVNET_CAIP2,
        asset: USDC_DEVNET_ADDRESS,
        amount: "1",
        payTo: PAY_TO,
        maxTimeoutSeconds: 3600,
        extra: { feePayer: FEE_PAYER },
      };

      const payload: PaymentPayload = {
        x402Version: 2,
        resource: {
          url: "http://example.com/protected",
          description: "Test resource",
          mimeType: "application/json",
        },
        accepted: requirements,
        payload: { transaction: REAL_SWIG_FEE_TX_BASE64 },
      };

      const result = await scheme.verify(payload, requirements);
      expect(result.isValid).toBe(true);
      expect(result.payer).toBe(SWIG_PDA);

      vi.doUnmock("@solana/kit");
    });
  });
});
