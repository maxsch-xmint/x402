"""Transaction normalization for different wallet types (regular, Swig, etc.)."""

from dataclasses import dataclass, field

try:
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction
except ImportError as e:
    raise ImportError(
        "SVM mechanism requires solana packages. Install with: pip install x402[svm]"
    ) from e

from .swig import (
    NormalizedInstruction,
    filter_fee_transfers,
    is_swig_transaction,
    parse_swig_transaction,
)
from .utils import get_token_payer_from_transaction


@dataclass
class NormalizedTransaction:
    """A flat instruction list and the address of the entity paying the token transfer."""

    instructions: list[NormalizedInstruction]
    payer: str


@dataclass
class NormalizationContext:
    """Payment context for fee filtering during normalization."""

    asset: str  # Token mint address
    pay_to: str  # Merchant owner address
    signer_addresses: list[str] = field(default_factory=list)  # Facilitator fee payer addresses
    account_keys_override: list[Pubkey] | None = None  # Override for ALT-resolved keys


class SwigNormalizer:
    """Detects and flattens Swig smart-wallet transactions."""

    def can_handle(self, tx: VersionedTransaction) -> bool:
        return is_swig_transaction(tx)

    def normalize(
        self, tx: VersionedTransaction, ctx: NormalizationContext | None = None
    ) -> NormalizedTransaction:
        result = parse_swig_transaction(tx)
        instructions = result.instructions
        if ctx is not None:
            account_keys = (
                ctx.account_keys_override
                if ctx.account_keys_override is not None
                else list(tx.message.account_keys)
            )
            instructions = filter_fee_transfers(
                account_keys,
                instructions,
                ctx.asset,
                ctx.pay_to,
                ctx.signer_addresses,
            )
        return NormalizedTransaction(
            instructions=instructions,
            payer=result.swig_pda,
        )


class RegularNormalizer:
    """Fallback normalizer for standard (non-smart-wallet) transactions."""

    def can_handle(self, tx: VersionedTransaction) -> bool:
        return True

    def normalize(
        self, tx: VersionedTransaction, ctx: NormalizationContext | None = None
    ) -> NormalizedTransaction:
        payer = get_token_payer_from_transaction(tx)
        if not payer:
            raise ValueError("invalid_exact_svm_payload_no_transfer_instruction")
        instructions = [
            NormalizedInstruction(
                program_id_index=ix.program_id_index,
                accounts=list(ix.accounts),
                data=bytes(ix.data),
            )
            for ix in tx.message.instructions
        ]
        return NormalizedTransaction(instructions=instructions, payer=payer)


_DEFAULT_NORMALIZERS = [SwigNormalizer(), RegularNormalizer()]


def normalize_transaction(
    tx: VersionedTransaction, ctx: NormalizationContext | None = None
) -> NormalizedTransaction:
    """Run the default normalizer chain and return the first successful result."""
    for normalizer in _DEFAULT_NORMALIZERS:
        if normalizer.can_handle(tx):
            return normalizer.normalize(tx, ctx)
    raise ValueError("no normalizer found for transaction")
