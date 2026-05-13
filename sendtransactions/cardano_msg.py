import json
from pycardano import (
    Address, TransactionBuilder, TransactionOutput,
    BlockFrostChainContext, Network, PaymentSigningKey,
    Value, MultiAsset, AssetName, Asset, PolicyId,
    PlutusV2Script, Redeemer, PaymentExtendedSigningKey,
    UTxO, TransactionInput
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

    # Construct BeneficiaryData datum using Indefinite-length CBOR tags
    try:
        addr_bytes = bytes.fromhex(target_address_evm.replace('0x', ''))
    except:
        addr_bytes = target_address_evm.encode('utf-8')

    def to_ind_cbor(obj):
        if isinstance(obj, cbor2.CBORTag):
            res = b'\xd8' + bytes([obj.tag]) + b'\x9f'
            if isinstance(obj.value, list):
                for item in obj.value:
                    res += to_ind_cbor(item)
            else:
                res += to_ind_cbor(obj.value)
            res += b'\xff'
            return res
        elif isinstance(obj, list):
            res = b'\x9f'
            for item in obj:
                res += to_ind_cbor(item)
            res += b'\xff'
            return res
        return cbor2.dumps(obj)

    # MsgAddress Tag 121 (ForeignAddress)
    msg_address = cbor2.CBORTag(121, [addr_bytes])

    # CCMessage content: [ msgAddress, amount ]
    beneficiary_data = cbor2.CBORTag(121, [msg_address, int(amount)])

    beneficiary_datum = Datum(RawPlutusData(to_ind_cbor(beneficiary_data)))

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
        # Note: Minting the OutboundToken requires the Outbound Policy Plutus script
        # and a valid Redeemer. These are omitted in this runner to avoid
        # TransactionBuilder crashes. The Relay Agent can still detect the
        # script output to OutboundDemo.
        pass

    signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
    context.submit_tx(signed_tx.to_cbor())

    return signed_tx.id, None

def consume_inbound_utxo(context, sender_sk_hex, tx_hash, tx_index, script_addr):
    """
    Manually consumes a UTXO from the InboundDemo script.
    Note: Requires script source or reference UTXO. For this engine,
    we assume the user has configured the script and we provide a structural consumption.
    """
    sk_bytes = bytes.fromhex(sender_sk_hex)
    if len(sk_bytes) == 64:
        payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes)
    else:
        payment_signing_key = PaymentSigningKey.from_primitive(sk_bytes)

    sender_addr = Address(payment_signing_key.to_verification_key().hash(), network=context.network)

    # 1. Fetch the target UTXO
    # In a real scenario, we'd fetch from context. Here we use the provided hash/index.
    # Note: Spending from script requires:
    # - The Script (PlutusV2)
    # - A Redeemer
    # - Collateral UTXO from the sender

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)

    # Placeholder for script spending logic
    # In the demo, the InboundDemo script usually has a simple redeemer

    print(f"  🔍 Consumption logic for {tx_hash}#{tx_index} initiated.")
    print("  ⚠️  Manual consumption requires the script source and redeemer which vary by deployment.")

    return None, "Manual consumption logic requires script/redeemer integration specific to the deployment."
