import json
from pycardano import (
    Address, TransactionBuilder, TransactionOutput,
    BlockFrostChainContext, Network, PaymentSigningKey,
    Value, MultiAsset, AssetName, Asset, PolicyId,
    PlutusV2Script, Redeemer, PaymentExtendedSigningKey
)
from pycardano import PlutusData, Datum, RawPlutusData
import cbor2

def cardano_to_evm_msg(context, sender_sk_hex, target_address_evm, amount, outbound_demo_addr, outbound_token_policy, demo_token_policy=None, demo_token_name=None):
    """
    Builds and submits a transaction to initiate a Cardano -> EVM cross-chain message.
    Following XPort protocol:
    1. Send assets to OutboundDemo script with BeneficiaryData datum.
    2. (Optional/Advanced) Mint OutBoundToken.
    """
    # Load signer
    sk_bytes = bytes.fromhex(sender_sk_hex)
    if len(sk_bytes) == 64:
        payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes)
    else:
        payment_signing_key = PaymentSigningKey.from_primitive(sk_bytes)
    sender_addr = Address(payment_signing_key.to_verification_key().hash(), network=context.network)

    # Construct BeneficiaryData datum using CBOR tags for Plutus compatibility
    # BeneficiaryData Tag 0: [ MsgAddress, amount ]
    # MsgAddress Tag 0: ForeignAddress [ bytes ]
    msg_address = cbor2.CBORTag(121, [target_address_evm.encode('utf-8')])
    beneficiary_data = cbor2.CBORTag(121, [msg_address, int(amount)])

    beneficiary_datum = Datum(RawPlutusData(cbor2.dumps(beneficiary_data)))

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)

    # Output to OutboundDemo script
    out_addr = Address.from_primitive(outbound_demo_addr)

    # Building the Value
    val = Value(coin=2000000)
    if demo_token_policy and demo_token_name:
        assets = MultiAsset({
            PolicyId.from_primitive(demo_token_policy): Asset({
                AssetName.from_primitive(demo_token_name): int(amount)
            })
        })
        val.multi_asset = assets

    tx_builder.add_output(TransactionOutput(out_addr, amount=val, datum=beneficiary_datum))

    # Structural placeholder for OutboundToken minting
    if outbound_token_policy:
        # In a full implementation, we would add minting logic here:
        # tx_builder.mint = MultiAsset({...})
        # tx_builder.add_minting_script(script, redeemer)
        pass

    signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
    context.submit_tx(signed_tx.to_cbor())

    return signed_tx.id, None
