import time, os, json, warnings
from dotenv import load_dotenv
warnings.filterwarnings("ignore")
load_dotenv()
from pycardano import (
    BlockFrostChainContext, Network, Address,
    TransactionBuilder, TransactionOutput, Value,
    MultiAsset, Asset, PolicyId, AssetName,
    PlutusV2Script, Redeemer, RawPlutusData,
    PaymentExtendedSigningKey, PaymentSigningKey
)
import cbor2
from utility.cbor_utils import to_indefinite_cbor

def get_signer(sk_hex):
    sk_bytes = bytes.fromhex(sk_hex)
    if len(sk_bytes) == 64: return PaymentExtendedSigningKey.from_primitive(sk_bytes)
    return PaymentSigningKey.from_primitive(sk_bytes)

class MsgAgent:
    def __init__(self, network_name):
        self.network_name = network_name
        self.network = Network.MAINNET if network_name == 'mainnet' else Network.TESTNET
        self.context = BlockFrostChainContext(os.getenv("YOUR_BLOCKFROST_PROJECT_ID"), self.network)
        with open('config/contract_accounts.json', 'r') as f:
            conf = json.load(f)[network_name]
            self.contracts = conf['cardano']
            self.evm_token_home = conf['evm']['token_home']

        self.demo_policy = PolicyId.from_primitive(self.contracts['demo_token_policy'])
        self.demo_name = AssetName.from_primitive(bytes.fromhex(self.contracts['demo_token_name']))
        self.inbound_policy = PolicyId.from_primitive(self.contracts['inbound_token_policy'])
        self.outbound_policy = PolicyId.from_primitive(self.contracts['outbound_token_policy'])
        self.outbound_token_name = AssetName.from_primitive(b"OutboundTokenCoin")

    def get_plutus_address(self, addr_str):
        """Converts Bech32 address to Plutus Address structure for CBOR."""
        addr = Address.from_primitive(addr_str)
        p_cred = cbor2.CBORTag(121, [addr.payment_part.to_primitive()])
        if addr.staking_part:
            s_cred = cbor2.CBORTag(121, [cbor2.CBORTag(121, [cbor2.CBORTag(121, [addr.staking_part.to_primitive()])])])
        else:
            s_cred = cbor2.CBORTag(122, [])
        return cbor2.CBORTag(121, [p_cred, s_cred])

    def process_inbound(self, wallet):
        print(f"🔍 Monitoring Inbound: {self.contracts['inbound_demo']}")
        uts = self.context.utxos(self.contracts['inbound_demo']) or []
        for u in uts:
            if not u.output.datum: continue
            try:
                datum_bytes = u.output.datum.cbor if hasattr(u.output.datum, "cbor") else u.output.datum.to_cbor()
                datum_obj = cbor2.loads(datum_bytes)
                inner_call_data = datum_obj.value[6].value[1]
                beneficiary = cbor2.loads(inner_call_data)
                amount = beneficiary.value[1]

                # Reconstruct receiver address
                receiver_tag = beneficiary.value[0]
                if isinstance(receiver_tag, cbor2.CBORTag) and receiver_tag.tag == 122:
                    addr_fields = receiver_tag.value[0].value # [p_cred, s_cred]
                    p_hash = addr_fields[0].value[0]
                    s_hash = addr_fields[1].value[0].value[0].value[0] if isinstance(addr_fields[1], cbor2.CBORTag) and addr_fields[1].tag == 121 else None
                    receiver = Address(p_hash, s_hash, network=self.network)
                else: receiver = Address.from_primitive(wallet['address'])
                self.execute_inbound_tx(u, wallet, receiver, amount)
            except Exception as e: print(f"  ❌ Inbound Parse Error: {e}")

    def execute_inbound_tx(self, utxo, wallet, receiver, amount):
        sk = get_signer(wallet['private_key'])
        sender_addr = Address.from_primitive(wallet['address'])
        txb = TransactionBuilder(self.context)
        txb.add_input_address(sender_addr)
        collateral = next((u for u in (self.context.utxos(wallet['address']) or []) if u.output.amount.coin > 5000000), None)
        if not collateral: return
        txb.collaterals.append(collateral)

        redeemer = Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [
            bytes.fromhex(self.contracts['demo_token_policy']),
            bytes.fromhex(self.evm_token_home.replace('0x','').lower())
        ]))))
        txb.add_script_input(utxo, script=PlutusV2Script(bytes.fromhex(self.contracts['inbound_demo_cbor'])), redeemer=redeemer)

        it_name = None
        for p, assets in utxo.output.amount.multi_asset.items():
            if p == self.inbound_policy: it_name = list(assets.keys())[0]; break

        mint_assets = MultiAsset()
        if it_name: mint_assets[self.inbound_policy] = Asset({it_name: -1})
        mint_assets[self.demo_policy] = Asset({self.demo_name: int(amount)})
        txb.mint = mint_assets

        txb.add_minting_script(PlutusV2Script(bytes.fromhex(self.contracts['inbound_token_cbor'])), Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [])))))
        txb.add_minting_script(PlutusV2Script(bytes.fromhex(self.contracts['demo_token_cbor'])), Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [])))))
        txb.add_output(TransactionOutput(receiver, amount=Value(coin=2000000, multi_asset=MultiAsset({self.demo_policy: Asset({self.demo_name: int(amount)})})) ))

        try:
            stx = txb.build_and_sign([sk], change_address=sender_addr)
            self.context.submit_tx(stx.to_cbor())
            print(f"✅ Inbound Processed: {stx.id}")
        except Exception as e: print(f"❌ Inbound Error: {e}")

    def process_outbound(self, wallet):
        print(f"🔍 Monitoring Outbound: {self.contracts['outbound_demo']}")
        uts = self.context.utxos(self.contracts['outbound_demo']) or []
        for u in uts:
            if not u.output.datum: continue
            try:
                datum_bytes = u.output.datum.cbor if hasattr(u.output.datum, "cbor") else u.output.datum.to_cbor()
                datum_obj = cbor2.loads(datum_bytes)
                amount = datum_obj.value[1]
                self.execute_outbound_tx(u, wallet, amount)
            except Exception as e: print(f"  ❌ Outbound Parse Error: {e}")

    def execute_outbound_tx(self, utxo, wallet, amount):
        sk = get_signer(wallet['private_key'])
        sender_addr = Address.from_primitive(wallet['address'])
        txb = TransactionBuilder(self.context)
        txb.add_input_address(sender_addr)
        collateral = next((u for u in (self.context.utxos(wallet['address']) or []) if u.output.amount.coin > 5000000), None)
        if not collateral: return
        txb.collaterals.append(collateral)

        # Redeemer: conStr0([burn_policy, burn_token_name, xport, remoteContract])
        # xport is an Address structure in the TS redeemer
        xport_plutus_addr = self.get_plutus_address(self.contracts['xport'])
        redeemer_data = cbor2.CBORTag(121, [
            bytes.fromhex(self.contracts['demo_token_policy']),
            self.demo_name.payload,
            xport_plutus_addr,
            bytes.fromhex(self.evm_token_home.replace('0x','').lower())
        ])
        txb.add_script_input(utxo, script=PlutusV2Script(bytes.fromhex(self.contracts['outbound_demo_cbor'])), redeemer=Redeemer(RawPlutusData(to_indefinite_cbor(redeemer_data))))

        mint_assets = MultiAsset()
        mint_assets[self.demo_policy] = Asset({self.demo_name: -int(amount)})
        mint_assets[self.outbound_policy] = Asset({self.outbound_token_name: 1})
        txb.mint = mint_assets

        txb.add_minting_script(PlutusV2Script(bytes.fromhex(self.contracts['demo_token_cbor'])), Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [])))))
        txb.add_minting_script(PlutusV2Script(bytes.fromhex(self.contracts['outbound_token_cbor'])), Redeemer(RawPlutusData(to_indefinite_cbor(cbor2.CBORTag(121, [])))))

        txb.add_output(TransactionOutput(Address.from_primitive(self.contracts['xport']), amount=Value(coin=2000000, multi_asset=MultiAsset({self.outbound_policy: Asset({self.outbound_token_name: 1})})), datum=utxo.output.datum))

        try:
            stx = txb.build_and_sign([sk], change_address=sender_addr)
            self.context.submit_tx(stx.to_cbor())
            print(f"✅ Outbound Relayed: {stx.id}")
        except Exception as e: print(f"❌ Outbound Error: {e}")

    def run(self):
        if not os.path.exists("current_cardano_wallets.json"): return print("❌ No wallets.")
        with open("current_cardano_wallets.json", "r") as f:
            data = json.load(f)[0]
            redeemers = data.get('redeemer_wallets', data.get('batch_wallets'))
            inbound_wallet = redeemers[0]
            outbound_wallet = redeemers[1]

        print(f"🚀 Msg Agent Started ({self.network_name}). Polling scripts...")
        while True:
            try:
                self.process_inbound(inbound_wallet)
                self.process_outbound(outbound_wallet)
                time.sleep(15)
            except KeyboardInterrupt: break
            except Exception as e: print(f"⚠️ Agent Error: {e}"); time.sleep(10)

if __name__ == "__main__":
    import sys
    MsgAgent(sys.argv[1] if len(sys.argv) > 1 else 'preprod').run()
