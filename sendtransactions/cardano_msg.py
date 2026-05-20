import json
from pycardano import (
    Address, TransactionBuilder, TransactionOutput,
    Value, MultiAsset, AssetName, Asset, PolicyId,
    PlutusV2Script, Redeemer, PaymentExtendedSigningKey,
    PaymentSigningKey, UTxO, TransactionInput
)
from pycardano import Datum, RawPlutusData
import cbor2
from utility.cbor_utils import to_indefinite_cbor

def cardano_to_evm_msg(context, sender_sk_hex, sender_addr_str, target_address_evm, amount, outbound_demo_addr, outbound_token_policy, demo_token_policy=None, demo_token_name=None):
    """
    Builds and submits a transaction to initiate a Cardano -> EVM cross-chain message.
    """
    sk_bytes = bytes.fromhex(sender_sk_hex)
    payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
    sender_addr = Address.from_primitive(sender_addr_str)

    try:
        addr_bytes = bytes.fromhex(target_address_evm.replace('0x', ''))
    except:
        addr_bytes = target_address_evm.encode('utf-8')

    msg_address = cbor2.CBORTag(121, [addr_bytes])
    beneficiary_data = cbor2.CBORTag(121, [msg_address, int(amount)])
    beneficiary_datum = RawPlutusData(to_indefinite_cbor(beneficiary_data))

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)
    out_addr = Address.from_primitive(outbound_demo_addr)

    val = Value(coin=2000000)
    if demo_token_policy and demo_token_name:
        val.multi_asset = MultiAsset({
            PolicyId.from_primitive(demo_token_policy): Asset({
                AssetName.from_primitive(demo_token_name): int(amount)
            })
        })

    tx_builder.add_output(TransactionOutput(out_addr, amount=val, datum=beneficiary_datum))

    signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
    context.submit_tx(signed_tx.to_cbor())
    return signed_tx.id, None
