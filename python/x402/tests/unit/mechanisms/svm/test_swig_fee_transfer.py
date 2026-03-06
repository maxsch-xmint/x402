"""Tests for Swig fee transfer filtering.

Validates fee transfer detection, filtering, and normalization against a real
confirmed Swig smart wallet USDC transfer on devnet with fee transfer:
  tx: XKr5pqRHyvh1LXfEPbRcNRJnXoQ1LHBFRy25h2MPR45gG9HXCokSqw1vdSK6bMPzNVGJDARkMqXSJdbMz9U4vUN
Contains 2 TransferChecked: merchant payment (1 USDC) + treasury fee (530 raw USDC)
Uses an Address Lookup Table (ALT): BoMp5p92bn66NYsdZu28bs4RA5UTGsWi2xnJrFiYZ9YE
"""

import base64

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from x402.mechanisms.svm.constants import (
    TOKEN_PROGRAM_ADDRESS,
    USDC_DEVNET_ADDRESS,
)
from x402.mechanisms.svm.normalizer import NormalizationContext, normalize_transaction
from x402.mechanisms.svm.swig import (
    filter_fee_transfers,
    is_swig_transaction,
    parse_swig_transaction,
)

REAL_SWIG_FEE_TX_BASE64 = "AhomrL2mhzI266oxGvibsSPwbGehiAj5dTairmeoUUxm5ndmXaKO9dnuho4yyD9j2SC8HyeCJ5Z4R4CzANSHJw9lTDRXSJfc8hnCmFdmDU2/wbxPE17BWC1/RJynEvCQtTUax4gcY7shMILIVUoD66Zzlbr+g2M/gm5MoFi2zvIOgAIBAwqZaoBA6PatAWpRvzksIlZIPBdwhETOtNqkgD0atmy0IupxmwFv0RBlHICES9rmToevW5l26rO4tAKBVKHpssHDPZHUnTCwsjJXxllTS5mu5oo6DcIi9P49lmiwxI/txFoeHPDMiy7/r3OLF/tlUqbaReCyBqu9GP11DpJAVoKVRjCbzjBy9aohOjeIENr1QZZ/AfpmFYZ1/alN4E9vtadvR9vYJ/mdYtQCwjHG4qEnHy5dk1aTy18yajQmI5q+CHt+o2lX5ca1zNVcdXZ9Jk+8k4JitaZit+6iX4Ck+mK93gMGRm/lIRcy/+ytunLDm+e8jOW7xfcSayxDmzpAAAAADQzpQuHnxQbiGN8NffHFL6/cNSnkjWdNHbJMdbVMzL47RCyzkSFX8TqTPQE0KC0DK1/+zQGi2/G3eQYI3wAup6oqdg/Bn1+vi2z5kPhad7qgn9TuiFfo+4qAWv7oCLwWAwcACQNkAAAAAAAAAAcABQKAGgYACAkCAwEKBAkFCgYuCwAlAAAAAAACAwQEBQYBCgAMAQAAAAAAAAAGBwQEBQgBCgAMEgIAAAAAAAAGAgGgdR5RdrVXonVRX7x2E50xA6Ssx93cJ6CFqANSV6MxwwABBQ=="

FEE_PAYER = "BKsZvzPUY6VT2GpLMxx6fA6fuC8MK3hVxwdjK8yqmqSR"
SWIG_PDA = "59LqtErLXz2hxyQsv2vyck6D9iXepEMgfoBjtDULKtX3"
PAY_TO = "EWVTHwKNzJRzRDb9jmZ89eq7X9KTygmRyBhoDj1pUmFW"


def _decode_tx() -> VersionedTransaction:
    raw = base64.b64decode(REAL_SWIG_FEE_TX_BASE64)
    return VersionedTransaction.from_bytes(raw)


def _resolve_fee_tx_account_keys(tx: VersionedTransaction) -> list[Pubkey]:
    """Return account_keys with ALT-resolved Token Program appended."""
    return list(tx.message.account_keys) + [Pubkey.from_string(TOKEN_PROGRAM_ADDRESS)]


class TestSwigFeeTransferIsSwigTransaction:
    def test_detected_as_swig(self):
        tx = _decode_tx()
        assert is_swig_transaction(tx) is True


class TestSwigFeeTransferParseSwigTransaction:
    def test_flattened_instruction_count_is_4(self):
        tx = _decode_tx()
        result = parse_swig_transaction(tx)
        assert len(result.instructions) == 4

    def test_swig_pda_matches(self):
        tx = _decode_tx()
        result = parse_swig_transaction(tx)
        assert result.swig_pda == SWIG_PDA

    def test_instruction_layout(self):
        tx = _decode_tx()
        result = parse_swig_transaction(tx)
        assert result.instructions[0].data[0] == 2  # SetComputeUnitLimit
        assert result.instructions[1].data[0] == 3  # SetComputeUnitPrice
        assert result.instructions[2].data[0] == 12  # TransferChecked
        assert result.instructions[3].data[0] == 12  # TransferChecked

    def test_merchant_transfer_amount_1(self):
        tx = _decode_tx()
        result = parse_swig_transaction(tx)
        data = result.instructions[2].data
        assert len(data) >= 9
        amount = int.from_bytes(data[1:9], "little")
        assert amount == 1

    def test_fee_transfer_amount_530(self):
        tx = _decode_tx()
        result = parse_swig_transaction(tx)
        data = result.instructions[3].data
        assert len(data) >= 9
        amount = int.from_bytes(data[1:9], "little")
        assert amount == 530


class TestSwigFeeTransferFilterFeeTransfers:
    def test_filters_down_to_3_instructions(self):
        tx = _decode_tx()
        account_keys = _resolve_fee_tx_account_keys(tx)
        result = parse_swig_transaction(tx)

        filtered = filter_fee_transfers(
            account_keys, result.instructions, USDC_DEVNET_ADDRESS, PAY_TO, [FEE_PAYER]
        )
        assert len(filtered) == 3

    def test_merchant_transfer_preserved(self):
        tx = _decode_tx()
        account_keys = _resolve_fee_tx_account_keys(tx)
        result = parse_swig_transaction(tx)

        filtered = filter_fee_transfers(
            account_keys, result.instructions, USDC_DEVNET_ADDRESS, PAY_TO, [FEE_PAYER]
        )
        assert filtered[2].data[0] == 12  # TransferChecked
        amount = int.from_bytes(filtered[2].data[1:9], "little")
        assert amount == 1


class TestSwigFeeTransferNormalizeWithContext:
    def test_returns_3_instructions(self):
        tx = _decode_tx()
        account_keys = _resolve_fee_tx_account_keys(tx)
        ctx = NormalizationContext(
            asset=USDC_DEVNET_ADDRESS,
            pay_to=PAY_TO,
            signer_addresses=[FEE_PAYER],
            account_keys_override=account_keys,
        )
        normalized = normalize_transaction(tx, ctx)
        assert len(normalized.instructions) == 3

    def test_payer_is_swig_pda(self):
        tx = _decode_tx()
        account_keys = _resolve_fee_tx_account_keys(tx)
        ctx = NormalizationContext(
            asset=USDC_DEVNET_ADDRESS,
            pay_to=PAY_TO,
            signer_addresses=[FEE_PAYER],
            account_keys_override=account_keys,
        )
        normalized = normalize_transaction(tx, ctx)
        assert normalized.payer == SWIG_PDA


class TestSwigFeeTransferNormalizeWithoutContext:
    def test_returns_4_instructions(self):
        tx = _decode_tx()
        normalized = normalize_transaction(tx)
        assert len(normalized.instructions) == 4

    def test_payer_is_swig_pda(self):
        tx = _decode_tx()
        normalized = normalize_transaction(tx)
        assert normalized.payer == SWIG_PDA


class TestSwigFeeTransferVerifyPipeline:
    """Full verify pipeline using pre-resolved transaction."""

    def _make_resolved_base64(self) -> str:
        """Build a transaction with ALT keys inlined as static keys."""
        from solders.hash import Hash
        from solders.message import MessageV0, MessageHeader
        from solders.instruction import CompiledInstruction

        tx = _decode_tx()
        msg = tx.message

        # Extend static account keys with ALT-resolved Token Program
        extended_keys = list(msg.account_keys) + [Pubkey.from_string(TOKEN_PROGRAM_ADDRESS)]

        # Reconstruct MessageV0 with extended keys and no ALT lookups
        new_msg = MessageV0(
            header=MessageHeader(
                msg.header.num_required_signatures,
                msg.header.num_readonly_signed_accounts,
                msg.header.num_readonly_unsigned_accounts,
            ),
            account_keys=extended_keys,
            recent_blockhash=Hash.from_string(str(msg.recent_blockhash)),
            instructions=[
                CompiledInstruction(ix.program_id_index, ix.data, bytes(ix.accounts))
                for ix in msg.instructions
            ],
            address_table_lookups=[],
        )

        resolved_tx = VersionedTransaction.populate(new_msg, list(tx.signatures))
        return base64.b64encode(bytes(resolved_tx)).decode()

    def test_verify_is_valid(self):
        from x402.mechanisms.svm import SOLANA_DEVNET_CAIP2
        from x402.mechanisms.svm.exact import ExactSvmFacilitatorScheme
        from x402.schemas import PaymentPayload, PaymentRequirements, ResourceInfo

        resolved_base64 = self._make_resolved_base64()

        signer = _MockFeeTransferSigner()
        facilitator = ExactSvmFacilitatorScheme(signer)

        requirements = PaymentRequirements(
            scheme="exact",
            network=SOLANA_DEVNET_CAIP2,
            asset=USDC_DEVNET_ADDRESS,
            amount="1",
            pay_to=PAY_TO,
            max_timeout_seconds=3600,
            extra={"feePayer": FEE_PAYER},
        )
        payload = PaymentPayload(
            x402_version=2,
            resource=ResourceInfo(
                url="http://example.com/protected",
                description="Test resource",
                mime_type="application/json",
            ),
            accepted=requirements,
            payload={"transaction": resolved_base64},
        )

        result = facilitator.verify(payload, requirements)
        assert result.is_valid is True
        assert result.payer == SWIG_PDA


class _MockFeeTransferSigner:
    """Mock facilitator signer for fee transfer testing."""

    def get_addresses(self) -> list[str]:
        return [FEE_PAYER]

    def sign_transaction(self, tx_base64: str, fee_payer: str, network: str) -> str:
        return tx_base64

    def simulate_transaction(self, tx_base64: str, network: str) -> None:
        pass

    def send_transaction(self, tx_base64: str, network: str) -> str:
        return "mockSignature123"

    def confirm_transaction(self, signature: str, network: str) -> None:
        pass
