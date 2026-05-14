import time
import os
import json
import warnings
from dotenv import load_dotenv

# Suppress Deprecation Warnings
warnings.filterwarnings("ignore")
try:
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass

load_dotenv()
from pycardano import (
    BlockFrostChainContext, Network, Address,
    TransactionBuilder, TransactionOutput, Value,
    MultiAsset, Asset, PolicyId, AssetName,
    PlutusV2Script, Redeemer, RawPlutusData,
    PaymentExtendedSigningKey, PaymentSigningKey
)
import cbor2

def get_signer(sk_hex):
    sk_bytes = bytes.fromhex(sk_hex)
    if len(sk_bytes) == 64: return PaymentExtendedSigningKey.from_primitive(sk_bytes)
    return PaymentSigningKey.from_primitive(sk_bytes)

class MsgAgent:
    def __init__(self, network_name):
        self.network_name = network_name
        self.network = Network.MAINNET if network_name == 'mainnet' else Network.TESTNET
        bf_id = os.getenv("YOUR_BLOCKFROST_PROJECT_ID")
        self.context = BlockFrostChainContext(bf_id, self.network)

        with open('config/contract_accounts.json', 'r') as f:
            self.contracts = json.load(f)[network_name]['cardano']

        with open('config/rpc.json', 'r') as f:
            self.rpc = json.load(f)
            self.evm_token_home = self.rpc['evm'][network_name].get('token_home', '0xd6Ed4F1F50Cae0c5c7F514F3D0B1220c4a78F71d')

    def process_inbound(self, wallet):
        script_addr = self.contracts['inbound_demo']
        print(f"🔍 Monitoring Inbound: {script_addr}")
        utxos = self.context.utxos(script_addr)
        for utxo in utxos:
            if not utxo.output.datum: continue
            print(f"📦 Found Inbound UTXO: {utxo.input}")
            try:
                datum_obj = cbor2.loads(utxo.output.datum.cbor)
                inner_call_data = datum_obj.value[6].value[1]
                beneficiary = cbor2.loads(inner_call_data)
                amount = beneficiary.value[1]
                # Reconstruct receiver address
                receiver_tag = beneficiary.value[0]
                if isinstance(receiver_tag, cbor2.CBORTag) and receiver_tag.tag == 122:
                    # Cardano Address: Tag 121 [ p_cred, s_cred ]
                    addr_data = receiver_tag.value[0]
                    p_hash = addr_data.value[0].value[0]
                    s_hash = None
                    if isinstance(addr_data.value[1], cbor2.CBORTag) and addr_data.value[1].tag == 121:
                        s_hash = addr_data.value[1].value[0].value[0].value[0]
                    receiver = Address(p_hash, s_hash, network=self.network)
                else:
                    receiver = Address.from_primitive(wallet['address'])

                self.execute_inbound_tx(utxo, wallet, receiver, amount)
            except Exception as e: print(f"  ❌ Error: {e}")

    def process_outbound(self, wallet):
        script_addr = self.contracts['outbound_demo']
        print(f"🔍 Monitoring Outbound: {script_addr}")
        utxos = self.context.utxos(script_addr)
        for utxo in utxos:
            if not utxo.output.datum: continue
            print(f"📦 Found Outbound UTXO: {utxo.input}")
            try:
                # TS: const beneficiary = getBeneficiaryFromCbor(utxo.output.plutusData);
                datum_obj = cbor2.loads(utxo.output.datum.cbor)
                amount = datum_obj.value[1]
                self.execute_outbound_tx(utxo, wallet, amount)
            except Exception as e: print(f"  ❌ Error: {e}")

    def execute_inbound_tx(self, utxo, wallet, receiver, amount):
        sk = get_signer(wallet['private_key'])
        sender_addr = Address.from_primitive(wallet['address'])

        tx_builder = TransactionBuilder(self.context)
        tx_builder.add_input_address(sender_addr)

        # Collateral
        collateral = next((u for u in self.context.utxos(str(sender_addr)) if u.output.amount.coin > 5000000), None)
        if not collateral:
            print("  ❌ No collateral found.")
            return
        tx_builder.collaterals.append(collateral)

        # Script Input
        inbound_script = PlutusV2Script(bytes.fromhex(self.contracts['inbound_demo_cbor']))
        redeemer = Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [
            bytes.fromhex(self.contracts['demo_token_policy']),
            bytes.fromhex(self.evm_token_home.replace('0x',''))
        ]))))
        tx_builder.add_script_input(utxo, script=inbound_script, redeemer=redeemer)

        # Mint/Burn
        it_policy, it_name, it_qty = None, None, 0
        for p, assets in utxo.output.amount.multi_asset.items():
            it_policy, it_name, it_qty = p, *list(assets.items())[0]
            break

        demo_policy = PolicyId.from_primitive(self.contracts['demo_token_policy'])
        demo_name = AssetName.from_primitive(bytes.fromhex(self.contracts['demo_token_name']))

        mint_assets = MultiAsset()
        mint_assets[it_policy] = Asset({it_name: -it_qty})
        mint_assets[demo_policy] = Asset({demo_name: int(amount)})
        tx_builder.mint = mint_assets

        tx_builder.add_minting_script(PlutusV2Script(bytes.fromhex(self.contracts['inbound_token_cbor'])), Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))
        tx_builder.add_minting_script(PlutusV2Script(bytes.fromhex(self.contracts['demo_token_cbor'])), Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [])))))

        # Output
        val = Value(coin=2000000, multi_asset=MultiAsset({demo_policy: Asset({demo_name: int(amount)})}))
        tx_builder.add_output(TransactionOutput(receiver, amount=val))

        try:
            signed_tx = tx_builder.build_and_sign([sk], change_address=sender_addr)
            self.context.submit_tx(signed_tx.to_cbor())
            print(f"  ✅ Inbound TX Success: {signed_tx.id}")
        except Exception as e:
            print(f"  ❌ Inbound TX Failed: {e}")

    def execute_outbound_tx(self, utxo, wallet, amount):
        sk = get_signer(wallet['private_key'])
        sender_addr = Address.from_primitive(wallet['address'])
        tx_builder = TransactionBuilder(self.context)
        tx_builder.add_input_address(sender_addr)

        sender_utxos = self.context.utxos(str(sender_addr))
        collateral = next((u for u in sender_utxos if u.output.amount.coin > 5000000), None)
        if not collateral: return
        tx_builder.collaterals.append(collateral)

        outbound_script = PlutusV2Script(bytes.fromhex(self.contracts['inbound_demo_cbor'])) # Outbound demo uses same base logic in demo
        # TS: const outboundRedeemer = mConStr0([demoTokenPolicy, demoTokenName, xportAddress, evmContractAddress]);
        redeemer = Redeemer(RawPlutusData(cbor2.dumps(cbor2.CBORTag(121, [
            bytes.fromhex(self.contracts['demo_token_policy']),
            bytes.fromhex(self.contracts['demo_token_name']),
            bytes.fromhex("00" * 28), # Mock XPort
            bytes.fromhex(self.evm_token_home.replace('0x',''))
        ]))))
        tx_builder.add_script_input(utxo, script=outbound_script, redeemer=redeemer)

        try:
            signed_tx = tx_builder.build_and_sign([sk], change_address=sender_addr)
            self.context.submit_tx(signed_tx.to_cbor())
            print(f"  ✅ Outbound TX Success: {signed_tx.id}")
        except Exception as e: print(f"  ❌ Outbound TX Failed: {e}")

    def run(self):
        if not os.path.exists("current_cardano_wallets.json"):
            print("❌ No wallets found.")
            return
        with open("current_cardano_wallets.json", "r") as f:
            wallet = json.load(f)[0]['batch_wallets'][0]
        print("🚀 Msg Agent Started.")
        while True:
            try:
                self.process_inbound(wallet)
                self.process_outbound(wallet)
                time.sleep(15)
            except KeyboardInterrupt: break
            except Exception as e:
                print(f"⚠️  Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    import sys
    net = sys.argv[1] if len(sys.argv) > 1 else 'preprod'
    MsgAgent(net).run()
