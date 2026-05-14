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

def cardano_to_evm_msg(context, sender_sk_hex, sender_addr_str, target_address_evm, amount, outbound_demo_addr, outbound_token_policy, demo_token_policy=None, demo_token_name=None):
    """
    Builds and submits a transaction to initiate a Cardano -> EVM cross-chain message.
    """
    sk_bytes = bytes.fromhex(sender_sk_hex)
    if len(sk_bytes) == 64:
        payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes)
    else:
        payment_signing_key = PaymentSigningKey.from_primitive(sk_bytes)

    sender_addr = Address.from_primitive(sender_addr_str)

    try:
        addr_bytes = bytes.fromhex(target_address_evm.replace('0x', ''))
    except:
        addr_bytes = target_address_evm.encode('utf-8')

    def to_ind_cbor(obj):
        if isinstance(obj, cbor2.CBORTag):
            res = b'\xd8' + bytes([obj.tag]) + b'\x9f'
            if isinstance(obj.value, list):
                for item in obj.value: res += to_ind_cbor(item)
            else: res += to_ind_cbor(obj.value)
            res += b'\xff'
            return res
        elif isinstance(obj, list):
            res = b'\x9f'
            for item in obj: res += to_ind_cbor(item)
            res += b'\xff'
            return res
        return cbor2.dumps(obj)

    msg_address = cbor2.CBORTag(121, [addr_bytes])
    beneficiary_data = cbor2.CBORTag(121, [msg_address, int(amount)])
    beneficiary_datum = Datum(RawPlutusData(to_ind_cbor(beneficiary_data)))

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)
    out_addr = Address.from_primitive(outbound_demo_addr)

    val = Value(coin=2000000)
    if demo_token_policy and demo_token_name:
        assets = MultiAsset({
            PolicyId.from_primitive(demo_token_policy): Asset({
                AssetName.from_primitive(demo_token_name): int(amount)
            })
        })
        val.multi_asset = assets

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
    if len(sk_bytes) == 64:
        payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes)
    else:
        payment_signing_key = PaymentSigningKey.from_primitive(sk_bytes)

    sender_addr = Address.from_primitive(sender_addr_str)
    utxos = context.utxos(script_addr)
    target_utxo = next((u for u in utxos if u.input.transaction_id.payload.hex() == tx_hash and u.input.index == tx_index), None)

    if not target_utxo: return None, f"UTXO {tx_hash}#{tx_index} not found at {script_addr}"
    if not target_utxo.output.datum: return None, "Target UTXO has no datum."

    try:
        datum_obj = cbor2.loads(target_utxo.output.datum.cbor)
        call_data_wrapped = datum_obj.value[6]
        inner_call_data_bytes = call_data_wrapped.value[1]
        beneficiary_datum = cbor2.loads(inner_call_data_bytes)
        amount = beneficiary_datum.value[1]
        target_receiver = sender_addr
    except Exception as e: return None, f"Failed to parse datum: {e}"

    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)
    sender_utxos = context.utxos(str(sender_addr))
    collateral = next((u for u in sender_utxos if u.output.amount.coin > 5000000), None)
    if not collateral: return None, "No suitable collateral UTXO found."
    tx_builder.collaterals.append(collateral)

    inbound_script = PlutusV2Script(bytes.fromhex(inbound_demo_cbor))
    evm_addr_bytes = bytes.fromhex(evm_contract_addr.replace('0x','').lower())
    redeemer_data = cbor2.CBORTag(121, [bytes.fromhex(demo_token_policy), evm_addr_bytes])
    tx_builder.add_script_input(target_utxo, script=inbound_script, redeemer=Redeemer(RawPlutusData(cbor2.dumps(redeemer_data))))

    it_policy, it_name, it_qty = None, None, 0
    for p, assets in target_utxo.output.amount.multi_asset.items():
        it_policy = p
        for n, q in assets.items():
            it_name = n
            it_qty = q
            break

    demo_token_name_bytes = bytes.fromhex("44656d6f546f6b656e")
    demo_policy_id = PolicyId.from_primitive(demo_token_policy)
    mint_assets = MultiAsset()
    if it_policy not in mint_assets: mint_assets[it_policy] = Asset()
    mint_assets[it_policy][it_name] = -it_qty
    if demo_policy_id not in mint_assets: mint_assets[demo_policy_id] = Asset()
    mint_assets[demo_policy_id][AssetName(demo_token_name_bytes)] = int(amount)
    tx_builder.mint = mint_assets

    tx_builder.add_minting_script(PlutusV2Script(bytes.fromhex(inbound_token_cbor)), Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))
    tx_builder.add_minting_script(PlutusV2Script(bytes.fromhex(demo_token_cbor)), Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))

    demo_val = Value(coin=2000000, multi_asset=MultiAsset({demo_policy_id: Asset({AssetName(demo_token_name_bytes): int(amount)})}))
    tx_builder.add_output(TransactionOutput(target_receiver, amount=demo_val))

    signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
    context.submit_tx(signed_tx.to_cbor())
    return signed_tx.id, None
