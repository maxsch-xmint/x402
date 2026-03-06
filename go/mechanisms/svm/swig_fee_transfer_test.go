package svm_test

import (
	"context"
	"encoding/binary"
	"testing"

	solana "github.com/gagliardetto/solana-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/coinbase/x402/go/mechanisms/svm"
	"github.com/coinbase/x402/go/mechanisms/svm/exact/facilitator"
	"github.com/coinbase/x402/go/types"
)

// Real confirmed Swig smart wallet USDC transfer on devnet with fee transfer.
// tx: XKr5pqRHyvh1LXfEPbRcNRJnXoQ1LHBFRy25h2MPR45gG9HXCokSqw1vdSK6bMPzNVGJDARkMqXSJdbMz9U4vUN
// Contains 2 TransferChecked: merchant payment (1 USDC) + treasury fee (530 raw USDC)
// Uses an Address Lookup Table (ALT): BoMp5p92bn66NYsdZu28bs4RA5UTGsWi2xnJrFiYZ9YE
// The ALT provides TokenProgram (readonly index 5) as the 11th account key.
const realSwigFeeTxBase64 = "AhomrL2mhzI266oxGvibsSPwbGehiAj5dTairmeoUUxm5ndmXaKO9dnuho4yyD9j2SC8HyeCJ5Z4R4CzANSHJw9lTDRXSJfc8hnCmFdmDU2/wbxPE17BWC1/RJynEvCQtTUax4gcY7shMILIVUoD66Zzlbr+g2M/gm5MoFi2zvIOgAIBAwqZaoBA6PatAWpRvzksIlZIPBdwhETOtNqkgD0atmy0IupxmwFv0RBlHICES9rmToevW5l26rO4tAKBVKHpssHDPZHUnTCwsjJXxllTS5mu5oo6DcIi9P49lmiwxI/txFoeHPDMiy7/r3OLF/tlUqbaReCyBqu9GP11DpJAVoKVRjCbzjBy9aohOjeIENr1QZZ/AfpmFYZ1/alN4E9vtadvR9vYJ/mdYtQCwjHG4qEnHy5dk1aTy18yajQmI5q+CHt+o2lX5ca1zNVcdXZ9Jk+8k4JitaZit+6iX4Ck+mK93gMGRm/lIRcy/+ytunLDm+e8jOW7xfcSayxDmzpAAAAADQzpQuHnxQbiGN8NffHFL6/cNSnkjWdNHbJMdbVMzL47RCyzkSFX8TqTPQE0KC0DK1/+zQGi2/G3eQYI3wAup6oqdg/Bn1+vi2z5kPhad7qgn9TuiFfo+4qAWv7oCLwWAwcACQNkAAAAAAAAAAcABQKAGgYACAkCAwEKBAkFCgYuCwAlAAAAAAACAwQEBQYBCgAMAQAAAAAAAAAGBwQEBQgBCgAMEgIAAAAAAAAGAgGgdR5RdrVXonVRX7x2E50xA6Ssx93cJ6CFqANSV6MxwwABBQ=="

const (
	feePayerFee = "BKsZvzPUY6VT2GpLMxx6fA6fuC8MK3hVxwdjK8yqmqSR"
	swigPDAFee  = "59LqtErLXz2hxyQsv2vyck6D9iXepEMgfoBjtDULKtX3"
	payToFee    = "EWVTHwKNzJRzRDb9jmZ89eq7X9KTygmRyBhoDj1pUmFW"
)

func decodeFeeTx(t *testing.T) *solana.Transaction {
	t.Helper()
	tx, err := svm.DecodeTransaction(realSwigFeeTxBase64)
	require.NoError(t, err)
	return tx
}

// resolveFeeTxALTs resolves the Address Lookup Table for the fee transaction.
// The ALT at BoMp5p92bn66NYsdZu28bs4RA5UTGsWi2xnJrFiYZ9YE provides
// TokenProgram (readonly at table index 5) as the 11th account key.
// After this call, tx.Message.AccountKeys includes the ALT-resolved addresses.
func resolveFeeTxALTs(t *testing.T, tx *solana.Transaction) {
	t.Helper()
	// The ALT has no writable entries; 1 readonly entry = TokenProgram
	err := tx.Message.ResolveLookupsWith(
		nil, // no writable ALT addresses
		solana.PublicKeySlice{solana.TokenProgramID}, // readonly: Token Program
	)
	require.NoError(t, err)
}

// resolvedFeeTxBase64 returns a base64-encoded version of the fee transaction
// with ALT addresses pre-resolved into static account keys. This allows
// scheme.Verify() (which decodes internally) to work without on-chain ALT data.
func resolvedFeeTxBase64(t *testing.T) string {
	t.Helper()
	tx := decodeFeeTx(t)
	resolveFeeTxALTs(t, tx)
	// Clear ALT lookups since all keys are now static
	tx.Message.SetAddressTableLookups(nil)
	encoded, err := svm.EncodeTransaction(tx)
	require.NoError(t, err)
	return encoded
}

// --- Test 1: IsSwigTransaction detection ---

func TestSwigFeeTransfer_IsSwigTransaction(t *testing.T) {
	tx := decodeFeeTx(t)
	assert.True(t, svm.IsSwigTransaction(tx), "expected real devnet fee tx to be detected as Swig")
}

// --- Test 2: ParseSwigTransaction ---

func TestSwigFeeTransfer_ParseSwigTransaction(t *testing.T) {
	tx := decodeFeeTx(t)
	result, err := svm.ParseSwigTransaction(tx)
	require.NoError(t, err)

	t.Run("flattened instruction count is 4", func(t *testing.T) {
		assert.Len(t, result.Instructions, 4, "should have 4 instructions: 2 compute budget + 2 TransferChecked")
	})

	t.Run("swig PDA matches", func(t *testing.T) {
		assert.Equal(t, swigPDAFee, result.SwigPDA)
	})

	t.Run("instruction layout: ComputeLimit, ComputePrice, TransferChecked, TransferChecked", func(t *testing.T) {
		assert.Equal(t, byte(2), result.Instructions[0].Data[0], "expected SetComputeUnitLimit at index 0")
		assert.Equal(t, byte(3), result.Instructions[1].Data[0], "expected SetComputeUnitPrice at index 1")
		assert.Equal(t, byte(12), result.Instructions[2].Data[0], "expected TransferChecked at index 2")
		assert.Equal(t, byte(12), result.Instructions[3].Data[0], "expected TransferChecked at index 3")
	})

	t.Run("merchant transfer amount=1 (instruction 2)", func(t *testing.T) {
		data := result.Instructions[2].Data
		require.True(t, len(data) >= 9, "transfer instruction data too short")
		amount := binary.LittleEndian.Uint64(data[1:9])
		assert.Equal(t, uint64(1), amount)
	})

	t.Run("fee transfer amount=530 (instruction 3)", func(t *testing.T) {
		data := result.Instructions[3].Data
		require.True(t, len(data) >= 9, "transfer instruction data too short")
		amount := binary.LittleEndian.Uint64(data[1:9])
		assert.Equal(t, uint64(530), amount)
	})
}

// --- Test 3: FilterFeeTransfers ---

func TestSwigFeeTransfer_FilterFeeTransfers(t *testing.T) {
	tx := decodeFeeTx(t)
	resolveFeeTxALTs(t, tx)
	result, err := svm.ParseSwigTransaction(tx)
	require.NoError(t, err)

	filtered, err := svm.FilterFeeTransfers(tx, result.Instructions, svm.USDCDevnetAddress, payToFee, []string{feePayerFee})
	require.NoError(t, err)

	t.Run("filters down to 3 instructions", func(t *testing.T) {
		assert.Len(t, filtered, 3, "should have 3 instructions: 2 compute budget + 1 merchant TransferChecked")
	})

	t.Run("merchant transfer preserved at index 2", func(t *testing.T) {
		assert.Equal(t, byte(12), filtered[2].Data[0], "expected TransferChecked at index 2")
		amount := binary.LittleEndian.Uint64(filtered[2].Data[1:9])
		assert.Equal(t, uint64(1), amount, "merchant transfer amount should be 1")
	})
}

// --- Test 4: NormalizeTransaction with context ---

func TestSwigFeeTransfer_NormalizeWithContext(t *testing.T) {
	tx := decodeFeeTx(t)
	resolveFeeTxALTs(t, tx)
	normCtx := &svm.NormalizationContext{
		Asset:           svm.USDCDevnetAddress,
		PayTo:           payToFee,
		SignerAddresses: []string{feePayerFee},
	}
	normalized, err := svm.NormalizeTransaction(tx, normCtx)
	require.NoError(t, err)

	t.Run("returns 3 instructions (fee filtered)", func(t *testing.T) {
		assert.Len(t, normalized.Instructions, 3)
	})

	t.Run("payer is swig PDA", func(t *testing.T) {
		assert.Equal(t, swigPDAFee, normalized.Payer)
	})
}

// --- Test 5: NormalizeTransaction without context ---

func TestSwigFeeTransfer_NormalizeWithoutContext(t *testing.T) {
	tx := decodeFeeTx(t)
	normalized, err := svm.NormalizeTransaction(tx, nil)
	require.NoError(t, err)

	t.Run("returns 4 instructions (no filtering)", func(t *testing.T) {
		assert.Len(t, normalized.Instructions, 4)
	})

	t.Run("payer is swig PDA", func(t *testing.T) {
		assert.Equal(t, swigPDAFee, normalized.Payer)
	})
}

// --- Test 6: Full verify pipeline ---

type mockFeeTransferSigner struct{}

func (m *mockFeeTransferSigner) GetAddresses(_ context.Context, _ string) []solana.PublicKey {
	return []solana.PublicKey{solana.MustPublicKeyFromBase58(feePayerFee)}
}

func (m *mockFeeTransferSigner) SignTransaction(_ context.Context, _ *solana.Transaction, _ solana.PublicKey, _ string) error {
	return nil
}

func (m *mockFeeTransferSigner) SimulateTransaction(_ context.Context, _ *solana.Transaction, _ string) error {
	return nil
}

func (m *mockFeeTransferSigner) SendTransaction(_ context.Context, _ *solana.Transaction, _ string) (solana.Signature, error) {
	return solana.Signature{}, nil
}

func (m *mockFeeTransferSigner) ConfirmTransaction(_ context.Context, _ solana.Signature, _ string) error {
	return nil
}

func TestSwigFeeTransfer_VerifyPipeline(t *testing.T) {
	// Use a pre-resolved version of the transaction (ALT addresses inlined as static keys)
	// so that scheme.Verify() can decode and process it without on-chain ALT data.
	resolvedBase64 := resolvedFeeTxBase64(t)

	signer := &mockFeeTransferSigner{}
	scheme := facilitator.NewExactSvmScheme(signer)

	requirements := types.PaymentRequirements{
		Scheme:  "exact",
		Network: svm.SolanaDevnetCAIP2,
		Asset:   svm.USDCDevnetAddress,
		Amount:  "1",
		PayTo:   payToFee,
		Extra:   map[string]interface{}{"feePayer": feePayerFee},
	}

	payload := types.PaymentPayload{
		X402Version: 2,
		Resource: &types.ResourceInfo{
			URL:         "http://example.com/protected",
			Description: "Test resource",
			MimeType:    "application/json",
		},
		Accepted: requirements,
		Payload:  map[string]interface{}{"transaction": resolvedBase64},
	}

	ctx := context.Background()
	result, err := scheme.Verify(ctx, payload, requirements, nil)

	t.Run("verify returns no error", func(t *testing.T) {
		assert.NoError(t, err)
		require.NotNil(t, result)
	})

	t.Run("verify is valid", func(t *testing.T) {
		require.NotNil(t, result)
		assert.True(t, result.IsValid)
	})

	t.Run("payer is swig PDA", func(t *testing.T) {
		require.NotNil(t, result)
		assert.Equal(t, swigPDAFee, result.Payer)
	})
}
