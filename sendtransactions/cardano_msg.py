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

def receive_from_evm_msg(context, wallet, tx_hash, receiver_addr_str, network_name):
    """
    Redeems an inbound message UTXO on Cardano.
    """
    with open('config/contract_accounts.json', 'r') as f:
        conf = json.load(f)[network_name]
        contracts = conf['cardano']
        evm_token_home = conf['evm']['token_home']

    inbound_demo_addr = contracts.get('inbound_demo_address')
    if not inbound_demo_addr:
        return None, "Error: inbound_demo_address not configured."

    uts = context.utxos(inbound_demo_addr) or []
    target_utxo = next((u for u in uts if u.input.transaction_id.payload.hex() == tx_hash), None)

    if not target_utxo:
        return None, f"Error: UTXO with Cardano TX hash {tx_hash} not found at script address {inbound_demo_addr}."

    if not target_utxo.output.datum:
        return None, "Error: Target UTXO has no datum."

    try:
        datum_bytes = target_utxo.output.datum.cbor if hasattr(target_utxo.output.datum, "cbor") else target_utxo.output.datum.to_cbor()
        datum_obj = cbor2.loads(datum_bytes)
        inner_call_data = datum_obj.value[6].value[1]
        beneficiary = cbor2.loads(inner_call_data)
        amount = beneficiary.value[1]
    except Exception as e:
        return None, f"Error parsing datum: {e}"

    sk_bytes = bytes.fromhex(wallet['private_key'])
    sk = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
    sender_addr = Address.from_primitive(wallet['address'])
    receiver_addr = Address.from_primitive(receiver_addr_str)

    txb = TransactionBuilder(context)
    txb.add_input_address(sender_addr)
    collateral = next((u for u in (context.utxos(wallet['address']) or []) if u.output.amount.coin > 5000000), None)
    if not collateral:
        return None, "Error: No suitable collateral UTXO found in main wallet (need > 5 ADA)."
    txb.collaterals.append(collateral)

    demo_policy = PolicyId.from_primitive(contracts['demo_token_policy'])
    demo_name = AssetName.from_primitive(bytes.fromhex(contracts['demo_token_name']))
    inbound_policy = PolicyId.from_primitive(contracts['inbound_token_policy'])

    try:
        redeemer_data = cbor2.CBORTag(121, [
            bytes.fromhex(contracts['demo_token_policy']),
            bytes.fromhex(evm_token_home.replace('0x','').lower())
        ])
        redeemer = Redeemer(RawPlutusData(to_indefinite_cbor(redeemer_data)))
        script_bytes = bytes.fromhex(contracts['inbound_demo_cbor'])
        txb.add_script_input(target_utxo, script=PlutusV2Script(script_bytes), redeemer=redeemer)
    except ValueError as e:
        return None, f"Configuration Error (hex parsing): {e}. Please check config/contract_accounts.json"

    it_name = None
    for p, assets in target_utxo.output.amount.multi_asset.items():
        if p == inbound_policy:
            it_name = list(assets.keys())[0]
            break

    mint_assets = MultiAsset()
    if it_name:
        mint_assets[inbound_policy] = Asset({it_name: -1})
    mint_assets[demo_policy] = Asset({demo_name: int(amount)})
    txb.mint = mint_assets

    txb.add_minting_script(PlutusV2Script(bytes.fromhex(contracts['inbound_token_cbor'])), Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [])))))
    txb.add_minting_script(PlutusV2Script(bytes.fromhex(contracts['demo_token_cbor'])), Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [])))))

    val = Value(coin=2000000, multi_asset=MultiAsset({demo_policy: Asset({demo_name: int(amount)})}))
    txb.add_output(TransactionOutput(receiver_addr, amount=val))

    try:
        stx = txb.build_and_sign([sk], change_address=sender_addr)
        context.submit_tx(stx.to_cbor())
        return stx.id, None
    except Exception as e:
        return None, f"Transaction submission failed: {e}"

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
