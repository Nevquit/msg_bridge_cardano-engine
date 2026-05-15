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

def consume_inbound_utxo(context, sender_sk_hex, sender_addr_str, tx_hash, tx_index, script_addr,
                         inbound_demo_cbor, inbound_token_cbor, demo_token_cbor,
                         demo_token_policy, evm_contract_addr):
    """
    Manually consumes a UTXO from the InboundDemo script.
    """
    sk_bytes = bytes.fromhex(sender_sk_hex)
    payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
    sender_addr = Address.from_primitive(sender_addr_str)

    utxos = context.utxos(script_addr)
    target_utxo = next((u for u in utxos if u.input.transaction_id.payload.hex() == tx_hash and u.input.index == tx_index), None)
    if not target_utxo: return None, f"UTXO {tx_hash}#{tx_index} not found."

    try:
        datum_obj = cbor2.loads(target_utxo.output.datum.cbor)
        beneficiary_datum = cbor2.loads(datum_obj.value[6].value[1])
        amount = beneficiary_datum.value[1]
        target_receiver = sender_addr
    except Exception as e: return None, f"Datum parse error: {e}"

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)
    sender_uts = context.utxos(sender_addr_str)
    collateral = next((u for u in sender_uts if u.output.amount.coin > 5000000), None)
    if not collateral: return None, "No collateral UTXO."
    tx_builder.collaterals.append(collateral)

    inbound_script = PlutusV2Script(bytes.fromhex(inbound_demo_cbor))
    redeemer = Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [bytes.fromhex(demo_token_policy), bytes.fromhex(evm_contract_addr.replace('0x','').lower())]))))
    tx_builder.add_script_input(target_utxo, script=inbound_script, redeemer=redeemer)

    it_policy, it_name, it_qty = None, None, 0
    if target_utxo.output.amount.multi_asset:
        for p, assets in target_utxo.output.amount.multi_asset.items():
            it_policy, it_name, it_qty = p, *list(assets.items())[0]
            break

    demo_policy_id = PolicyId.from_primitive(demo_token_policy)
    demo_name = AssetName.from_primitive(bytes.fromhex("44656d6f546f6b656e"))
    mint_assets = MultiAsset()
    mint_assets[it_policy] = Asset({it_name: -it_qty})
    mint_assets[demo_policy_id] = Asset({demo_name: int(amount)})
    tx_builder.mint = mint_assets

    tx_builder.add_minting_script(PlutusV2Script(bytes.fromhex(inbound_token_cbor)), Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))
    tx_builder.add_minting_script(PlutusV2Script(bytes.fromhex(demo_token_cbor)), Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))

    demo_val = Value(coin=2000000, multi_asset=MultiAsset({demo_policy_id: Asset({demo_name: int(amount)})}))
    tx_builder.add_output(TransactionOutput(target_receiver, amount=demo_val))

    signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
    context.submit_tx(signed_tx.to_cbor())
    return signed_tx.id, None
