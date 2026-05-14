import os
import json
from mnemonic import Mnemonic
from pycardano import (
    Address, Network, BlockFrostChainContext, TransactionBuilder, TransactionOutput,
    HDWallet, PaymentExtendedSigningKey, StakeExtendedSigningKey, Value, MultiAsset, Asset, PolicyId, AssetName
)
from web3 import Web3
from eth_account import Account
import pandas as pd

class PrepareAssets:
    def __init__(self, network_name):
        self.network_name = network_name
        with open('config/rpc.json', 'r') as f: self.rpc_config = json.load(f)
        self.cardano_network = Network.MAINNET if network_name == 'mainnet' else Network.TESTNET
        self.blockfrost_project_id = os.getenv("YOUR_BLOCKFROST_PROJECT_ID")
        if not self.blockfrost_project_id: raise ValueError("YOUR_BLOCKFROST_PROJECT_ID not set")
        self.cardano_context = BlockFrostChainContext(self.blockfrost_project_id, self.cardano_network)
        self.evm_url = self.rpc_config['evm'][network_name]['url']
        self.w3 = Web3(Web3.HTTPProvider(self.evm_url))

    def _get_max_cases(self, direction):
        folder = os.path.join("testcases", direction)
        if not os.path.exists(folder): return 0
        max_c = 0
        for f in os.listdir(folder):
            if f.endswith('.csv'):
                try: max_c = max(max_c, len(pd.read_csv(os.path.join(folder, f))))
                except: pass
        return max_c

    def generate_wallets(self, mnemonic_phrase=None):
        if not mnemonic_phrase: mnemonic_phrase = Mnemonic("english").generate(strength=256)
        wallet_set_id = os.urandom(4).hex()
        cardano_count, evm_count = self._get_max_cases("cardano_to_evm"), self._get_max_cases("evm_to_cardano")
        hd_wallet = HDWallet.from_mnemonic(mnemonic_phrase)

        def derive_cardano(index):
            p_hd, s_hd = hd_wallet.derive_from_path(f"m/1852'/1815'/0'/0/{index}"), hd_wallet.derive_from_path("m/1852'/1815'/0'/2/0")
            p_sk, s_sk = PaymentExtendedSigningKey.from_primitive(p_hd.xprivate_key), StakeExtendedSigningKey.from_primitive(s_hd.xprivate_key)
            addr = Address(p_sk.to_verification_key().hash(), s_sk.to_verification_key().hash(), network=self.cardano_network)
            return {"address": str(addr), "private_key": p_sk.to_primitive().hex()}

        main_cardano = derive_cardano(0)
        batch_cardano = [derive_cardano(i) for i in range(1, cardano_count + 1)]
        with open("current_cardano_wallets.json", "w") as f: json.dump([{"mnemonic": mnemonic_phrase, "main_wallet": main_cardano, "batch_wallets": batch_cardano}], f, indent=4)

        Account.enable_unaudited_hdwallet_features()
        main_evm_acc = Account.from_mnemonic(mnemonic_phrase, account_path="m/44'/60'/0'/0/0")
        batch_evm = [{"address": Account.from_mnemonic(mnemonic_phrase, account_path=f"m/44'/60'/0'/0/{i}").address, "private_key": Account.from_mnemonic(mnemonic_phrase, account_path=f"m/44'/60'/0'/0/{i}").key.hex()} for i in range(1, evm_count + 1)]
        with open("current_evm_wallets.json", "w") as f: json.dump([{"mnemonic": mnemonic_phrase, "main_wallet": {"address": main_evm_acc.address, "private_key": main_evm_acc.key.hex()}, "batch_wallets": batch_evm}], f, indent=4)
        print(f"✅ Wallets Generated. Mnemonic: {mnemonic_phrase}")

    def check_all_cardano_balances(self, case_file, wallets_info):
        _, main, batch = wallets_info
        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        with open('config/contract_accounts.json', 'r') as f: contracts = json.load(f)[self.network_name]['cardano']
        policy, token_name = contracts.get('demo_token_policy', ''), contracts.get('demo_token_name', '')
        def get_info(addr):
            try:
                uts = self.cardano_context.utxos(addr)
                coin = sum([u.output.amount.coin for u in uts])
                tk = 0
                for u in uts:
                    if u.output.amount.multi_asset:
                        for p, assets in u.output.amount.multi_asset.items():
                            if str(p) == policy: tk += assets.get(AssetName.from_primitive(token_name), 0) if token_name else sum(assets.values())
                return coin, tk
            except: return 0, 0
        c, t = get_info(main['address'])
        print(f"MAIN: {main['address']} | ADA: {c/1000000:.2f} | TOKEN: {t}")
        for i, w in enumerate(batch):
            if i >= len(cases): break
            c, t = get_info(w['address'])
            print(f"BATCH {i+1}: {w['address'][:10]} | ADA: {c/1000000:.2f} | TOKEN: {t}")

    def check_all_evm_balances(self, case_file, wallets_info):
        _, main, batch = wallets_info
        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        with open('config/contract_accounts.json', 'r') as f: contracts = json.load(f)[self.network_name]['evm']
        token_addr = contracts.get('gx_token', '')
        token_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(token_addr), abi=[{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]) if token_addr else None
        def get_info(addr):
            c_addr = self.w3.to_checksum_address(addr)
            return self.w3.eth.get_balance(c_addr), token_contract.functions.balanceOf(c_addr).call() if token_contract else 0
        c, t = get_info(main['address'])
        print(f"MAIN: {main['address']} | WAN: {self.w3.from_wei(c, 'ether'):.4f} | TOKEN: {t}")
        for i, w in enumerate(batch):
            if i >= len(cases): break
            c, t = get_info(w['address'])
            print(f"BATCH {i+1}: {w['address'][:10]} | WAN: {self.w3.from_wei(c, 'ether'):.4f} | TOKEN: {t}")

    def distribute_cardano_funds(self, case_file, wallets_info):
        _, main, batch = wallets_info
        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        with open('config/contract_accounts.json', 'r') as f: contracts = json.load(f)[self.network_name]['cardano']
        sk_bytes = bytes.fromhex(main['private_key'])
        main_sk = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
        main_addr = Address.from_primitive(main['address'])
        tx_builder = TransactionBuilder(self.cardano_context)
        tx_builder.add_input_address(main_addr)
        for i, w in enumerate(batch):
            if i >= len(cases): break
            val = Value(coin=5000000)
            if contracts.get('demo_token_policy'):
                val.multi_asset = MultiAsset({PolicyId.from_primitive(contracts['demo_token_policy']): Asset({AssetName.from_primitive(contracts.get('demo_token_name', '')): int(cases[i]['amount_raw'])})})
            tx_builder.add_output(TransactionOutput(Address.from_primitive(w['address']), amount=val))
        stx = tx_builder.build_and_sign([main_sk], change_address=main_addr)
        self.cardano_context.submit_tx(stx.to_cbor())
        print(f"✅ Cardano Distribution: {stx.id}")

    def distribute_evm_funds(self, case_file, wallets_info):
        _, main, batch = wallets_info
        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        with open('config/contract_accounts.json', 'r') as f: contracts = json.load(f)[self.network_name]['evm']
        main_addr = self.w3.to_checksum_address(main['address'])
        nonce = self.w3.eth.get_transaction_count(main_addr)
        for i, w in enumerate(batch):
            if i >= len(cases): break
            dest = self.w3.to_checksum_address(w['address'])
            tx_wan = {'nonce': nonce, 'to': dest, 'value': self.w3.to_wei(0.1, 'ether'), 'gas': 21000, 'gasPrice': self.w3.eth.gas_price, 'chainId': self.w3.eth.chain_id}
            h_wan = self.w3.eth.send_raw_transaction(self.w3.eth.account.sign_transaction(tx_wan, main['private_key']).raw_transaction)
            nonce += 1
            if contracts.get('gx_token'):
                tk_c = self.w3.eth.contract(address=self.w3.to_checksum_address(contracts['gx_token']), abi=[{"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}])
                tx_tk = tk_c.functions.transfer(dest, int(cases[i]['amount_raw'])).build_transaction({'from': main_addr, 'nonce': nonce, 'gas': 100000, 'gasPrice': self.w3.eth.gas_price, 'chainId': self.w3.eth.chain_id})
                self.w3.eth.send_raw_transaction(self.w3.eth.account.sign_transaction(tx_tk, main['private_key']).raw_transaction)
                nonce += 1
            print(f"  Sent to {w['address'][:10]}")

    def sweep_cardano_assets(self, destination_address, wallets_info):
        _, main, batch = wallets_info
        dest_addr = Address.from_primitive(destination_address)
        for w in [main] + batch:
            uts = self.cardano_context.utxos(w['address'])
            if not uts: continue
            sk_bytes = bytes.fromhex(w['private_key'])
            sk = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
            txb = TransactionBuilder(self.cardano_context)
            txb.add_input_address(Address.from_primitive(w['address']))
            stx = txb.build_and_sign([sk], change_address=dest_addr)
            self.cardano_context.submit_tx(stx.to_cbor())
            print(f"  Swept {w['address'][:10]}")

    def sweep_evm_assets(self, destination_address, wallets_info):
        _, main, batch = wallets_info
        dest = self.w3.to_checksum_address(destination_address)
        with open('config/contract_accounts.json', 'r') as f: contracts = json.load(f)[self.network_name]['evm']
        tk_addr = contracts.get('gx_token', '')
        tk_c = self.w3.eth.contract(address=self.w3.to_checksum_address(tk_addr), abi=[{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}, {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}]) if tk_addr else None
        for w in [main] + batch:
            addr = self.w3.to_checksum_address(w['address'])
            nonce = self.w3.eth.get_transaction_count(addr)
            if tk_c:
                bal = tk_c.functions.balanceOf(addr).call()
                if bal > 0:
                    tx = tk_c.functions.transfer(dest, bal).build_transaction({'from': addr, 'nonce': nonce, 'gas': 100000, 'gasPrice': self.w3.eth.gas_price, 'chainId': self.w3.eth.chain_id})
                    self.w3.eth.send_raw_transaction(self.w3.eth.account.sign_transaction(tx, w['private_key']).raw_transaction)
                    nonce += 1
            wan = self.w3.eth.get_balance(addr)
            fee = self.w3.eth.gas_price * 21000
            if wan > fee:
                tx = {'nonce': nonce, 'to': dest, 'value': wan - fee, 'gas': 21000, 'gasPrice': self.w3.eth.gas_price, 'chainId': self.w3.eth.chain_id}
                self.w3.eth.send_raw_transaction(self.w3.eth.account.sign_transaction(tx, w['private_key']).raw_transaction)
            print(f"  Swept {w['address'][:10]}")
