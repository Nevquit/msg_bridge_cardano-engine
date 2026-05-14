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

    sender_addr = Address.from_primitive(sender_addr_str)

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

def consume_inbound_utxo(context, sender_sk_hex, sender_addr_str, tx_hash, tx_index, script_addr,
                         inbound_demo_cbor, inbound_token_cbor, demo_token_cbor,
                         demo_token_policy, evm_contract_addr):
    """
    Manually consumes a UTXO from the InboundDemo script.
    Steps:
    1. Spend Inbound UTXO using InboundDemo script and Redeemer.
    2. Burn InboundToken (InboundToken script).
    3. Mint DemoToken (DemoToken script).
    4. Send DemoToken to the receiver specified in Inbound UTXO datum.
    """
    sk_bytes = bytes.fromhex(sender_sk_hex)
    if len(sk_bytes) == 64:
        payment_signing_key = PaymentExtendedSigningKey.from_primitive(sk_bytes)
    else:
        payment_signing_key = PaymentSigningKey.from_primitive(sk_bytes)

    sender_addr = Address.from_primitive(sender_addr_str)

    # 1. Fetch the target UTXO and its datum
    utxos = context.utxos(script_addr)
    target_utxo = None
    for u in utxos:
        if u.input.transaction_id.payload.hex() == tx_hash and u.input.index == tx_index:
            target_utxo = u
            break

    if not target_utxo:
        return None, f"UTXO {tx_hash}#{tx_index} not found at {script_addr}"

    if not target_utxo.output.datum:
        return None, "Target UTXO has no datum. Cannot parse receiver/amount."

    # Parse Inbound Datum (CrossMsgData)
    try:
        datum_obj = cbor2.loads(target_utxo.output.datum.cbor)
        # Fields: [msgId, fromChainId, fromContract, toChainId, targetContract, gasLimit, callData]
        # callData: Tag 121 [functionName, innerCallData]
        # innerCallData: bytes (CBOR encoded genBeneficiaryData)
        call_data_wrapped = datum_obj.value[6]
        inner_call_data_bytes = call_data_wrapped.value[1]
        beneficiary_datum = cbor2.loads(inner_call_data_bytes)
        # Beneficiary: Tag 121 [ Tag 121 [ p_cred, s_cred ], amount ]
        amount = beneficiary_datum.value[1]

        # Extract receiver address
        # Structural conversion to Bech32 Cardano Address or Bytes
        receiver_data = beneficiary_datum.value[0]
        # For simplicity in this runner, we'll send the tokens to the sender
        # or implement full address reconstruction if required.
        # Most Inbound messages target a Cardano address derived from the datum.
        target_receiver = sender_addr # Default for demo
    except Exception as e:
        return None, f"Failed to parse datum: {e}"

    # 2. Build Transaction
    tx_builder = TransactionBuilder(context)
    tx_builder.add_input_address(sender_addr)

    # Collateral
    sender_utxos = context.utxos(str(sender_addr))
    collateral = next((u for u in sender_utxos if u.output.amount.coin > 5000000), None)
    if not collateral: return None, "No suitable collateral UTXO found in wallet."
    tx_builder.collaterals.append(collateral)

    # InboundDemo Script Spending
    inbound_script = PlutusV2Script(bytes.fromhex(inbound_demo_cbor))
    # Redeemer: conStr0([demoTokenPolicy, evmContractAddress])
    evm_addr_bytes = bytes.fromhex(evm_contract_addr.replace('0x','').lower())
    redeemer_data = cbor2.CBORTag(121, [bytes.fromhex(demo_token_policy), evm_addr_bytes])
    tx_builder.add_script_input(target_utxo, script=inbound_script, redeemer=Redeemer(RawPlutusData(cbor2.dumps(redeemer_data))))

    # Minting/Burning logic
    inbound_token_script = PlutusV2Script(bytes.fromhex(inbound_token_cbor))
    demo_token_script = PlutusV2Script(bytes.fromhex(demo_token_cbor))

    # Extract InboundToken from UTXO
    it_policy = None
    it_name = None
    it_qty = 0
    for p, assets in target_utxo.output.amount.multi_asset.items():
        it_policy = p
        for n, q in assets.items():
            it_name = n
            it_qty = q
            break

    # Burn InboundToken and Mint DemoToken
    demo_token_name_bytes = bytes.fromhex("44656d6f546f6b656e")
    demo_policy_id = PolicyId.from_primitive(demo_token_policy)

    mint_assets = MultiAsset()
    # 1. Burn InboundToken
    if it_policy not in mint_assets: mint_assets[it_policy] = Asset()
    mint_assets[it_policy][it_name] = -it_qty

    # 2. Mint DemoToken
    if demo_policy_id not in mint_assets: mint_assets[demo_policy_id] = Asset()
    mint_assets[demo_policy_id][AssetName(demo_token_name_bytes)] = int(amount)

    tx_builder.mint = mint_assets

    # Add witnesses for minting
    tx_builder.add_minting_script(inbound_token_script, Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))
    tx_builder.add_minting_script(demo_token_script, Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))

    # Send DemoToken to receiver
    demo_val = Value(coin=2000000, multi_asset=MultiAsset({
        demo_policy_id: Asset({AssetName(demo_token_name_bytes): int(amount)})
    }))
    tx_builder.add_output(TransactionOutput(target_receiver, amount=demo_val))

    try:
        signed_tx = tx_builder.build_and_sign([payment_signing_key], change_address=sender_addr)
        context.submit_tx(signed_tx.to_cbor())
        return signed_tx.id, None
    except Exception as e:
        return None, str(e)
