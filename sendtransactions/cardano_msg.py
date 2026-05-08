import json
from pycardano import (
    Address, TransactionBuilder, TransactionOutput,
    BlockFrostChainContext, Network, PaymentSigningKey,
    Value, MultiAsset, AssetName, Asset
)
from cbor2 import dumps

def cardano_to_evm_msg(context, sender_sk_hex, target_address_evm, amount, outbound_demo_addr, outbound_token_policy, demo_token_policy=None, demo_token_name=None):
    # Load signer
    payment_signing_key = PaymentSigningKey.from_primitive(bytes.fromhex(sender_sk_hex))
    sender_addr = Address(payment_signing_key.to_verification_key().hash(), network=context.network)

    # Outbound message:
    # 1. Send DemoToken to OutboundDemo script with Beneficiary datum.
    # 2. Mint OutBoundToken and send to XPort script with CrossMsgData datum.

    beneficiary_datum = {
        0: [ # Constructor 0: BeneficiaryData
            {0: [target_address_evm.encode('utf-8')]}, # ForeignAddress
            int(amount)
        ]
    }

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)

    # Output to OutboundDemo script
    out_addr = Address.from_primitive(outbound_demo_addr)
    tx_builder.add_output(TransactionOutput(out_addr, amount=2000000, datum=beneficiary_datum))

    # Logic for minting OutBoundToken would go here
    # This requires providing the script and redeemer for the minting policy

    signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
    context.submit_tx(signed_tx.to_cbor())

    return signed_tx.id, None
