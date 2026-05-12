import os
import json
import binascii
from mnemonic import Mnemonic
from pycardano import (
    Address, Network, PaymentKeyPair, StakeKeyPair,
    BlockFrostChainContext, TransactionBuilder, TransactionOutput,
    HDWallet, PaymentSigningKey, StakeSigningKey, PaymentVerificationKey, StakeVerificationKey,
    PaymentExtendedSigningKey, StakeExtendedSigningKey, Value, MultiAsset, Asset, PolicyId, AssetName
)
from web3 import Web3
from eth_account import Account
import pandas as pd

class PrepareAssets:
    def __init__(self, network_name):
        self.network_name = network_name
        with open('config/rpc.json', 'r') as f:
            self.rpc_config = json.load(f)

        self.cardano_network = Network.MAINNET if network_name == 'mainnet' else Network.TESTNET
        self.blockfrost_project_id = os.getenv("YOUR_BLOCKFROST_PROJECT_ID")
        if not self.blockfrost_project_id:
            raise ValueError("YOUR_BLOCKFROST_PROJECT_ID environment variable is not set")
        self.cardano_context = BlockFrostChainContext(self.blockfrost_project_id, self.cardano_network)

        self.evm_url = self.rpc_config['evm'][network_name]['url']
        self.w3 = Web3(Web3.HTTPProvider(self.evm_url))

    def _get_max_cases(self, direction):
        folder = os.path.join("testcases", direction)
        if not os.path.exists(folder): return 0
        max_c = 0
        for f in os.listdir(folder):
            if f.endswith('.csv'):
                try:
                    df = pd.read_csv(os.path.join(folder, f))
                    max_c = max(max_c, len(df))
                except: pass
        return max_c

    def generate_wallets(self, mnemonic_phrase=None):
        if not mnemonic_phrase:
            mnemo = Mnemonic("english")
            mnemonic_phrase = mnemo.generate(strength=256)
            print(f"✨ Generated new mnemonic: {mnemonic_phrase}")

        wallet_set_id = os.urandom(4).hex()

        cardano_count = self._get_max_cases("cardano_to_evm")
        evm_count = self._get_max_cases("evm_to_cardano")

        # Generate Cardano Wallets
        hd_wallet = HDWallet.from_mnemonic(mnemonic_phrase)

        def derive_cardano(index):
            # CIP-1852 path: m/1852'/1815'/0'/0/index
            payment_hd = hd_wallet.derive_from_path(f"m/1852'/1815'/0'/0/{index}")
            stake_hd = hd_wallet.derive_from_path(f"m/1852'/1815'/0'/2/0")

            payment_sk = PaymentExtendedSigningKey.from_primitive(payment_hd.xprivate_key)
            stake_sk = StakeExtendedSigningKey.from_primitive(stake_hd.xprivate_key)

            payment_vk = payment_sk.to_verification_key()
            stake_vk = stake_sk.to_verification_key()

            addr = Address(payment_vk.hash(), stake_vk.hash(), network=self.cardano_network)
            return {
                "address": str(addr),
                "private_key": payment_sk.to_primitive().hex()
            }

        main_cardano = derive_cardano(0)
        batch_cardano = [derive_cardano(i) for i in range(1, cardano_count + 1)]

        cardano_wallet_data = {
            "wallet_name": f"cardano_key_set_{wallet_set_id}",
            "mnemonic": mnemonic_phrase,
            "main_wallet": main_cardano,
            "batch_wallets": batch_cardano
        }

        with open("current_cardano_wallets.json", "w") as f:
            json.dump([cardano_wallet_data], f, indent=4)

        # Generate EVM Wallets
        Account.enable_unaudited_hdwallet_features()
        main_evm_acc = Account.from_mnemonic(mnemonic_phrase, account_path="m/44'/60'/0'/0/0")
        main_evm = {
            "address": main_evm_acc.address,
            "private_key": main_evm_acc.key.hex()
        }

        batch_evm = []
        for i in range(1, evm_count + 1):
            acc = Account.from_mnemonic(mnemonic_phrase, account_path=f"m/44'/60'/0'/0/{i}")
            batch_evm.append({
                "address": acc.address,
                "private_key": acc.key.hex()
            })

        evm_wallet_data = {
            "wallet_name": f"evm_key_set_{wallet_set_id}",
            "mnemonic": mnemonic_phrase,
            "main_wallet": main_evm,
            "batch_wallets": batch_evm
        }

        with open("current_evm_wallets.json", "w") as f:
            json.dump([evm_wallet_data], f, indent=4)

        if not os.path.exists("wallets"): os.makedirs("wallets")

        with open(os.path.join("wallets", f"{cardano_wallet_data['wallet_name']}.json"), "w") as f:
            json.dump(cardano_wallet_data, f, indent=4)
        with open(os.path.join("wallets", f"{evm_wallet_data['wallet_name']}.json"), "w") as f:
            json.dump(evm_wallet_data, f, indent=4)

        print(f"✅ Generated batch wallets: Cardano={cardano_count}, EVM={evm_count}")
        print(f"✅ Saved to current_cardano_wallets.json, current_evm_wallets.json and wallets/ directory")

    def check_all_cardano_balances(self, case_file, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"\n--- 💰 Cardano Balance Diagnostics ({self.network_name}) ---")

        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        total_token_needed = sum([int(c['amount_raw']) for c in cases])
        total_ada_needed = (len(cases) * 2) + 5 # 2 ADA per case + 5 ADA buffer

        with open('config/contract_accounts.json', 'r') as f:
            contracts = json.load(f)[self.network_name]['cardano']

        policy = contracts.get('demo_token_policy', '')
        token_name = contracts.get('demo_token_name', '')

        def get_info(addr):
            try:
                utxos = self.cardano_context.utxos(addr)
                lovelace = sum([utxo.output.amount.coin for utxo in utxos])
                tokens = 0
                for utxo in utxos:
                    if utxo.output.amount.multi_asset:
                        for p, assets in utxo.output.amount.multi_asset.items():
                            if str(p) == policy:
                                if token_name:
                                    tokens += assets.get(AssetName.from_primitive(token_name), 0)
                                else:
                                    tokens += sum([qty for name, qty in assets.items()])
                return lovelace, tokens
            except:
                return 0, 0

        main_ada, main_tk = get_info(main_wallet['address'])
        print(f"MAIN WALLET: {main_wallet['address']}")
        print(f"  ADA: {main_ada/1000000:.2f} (Need: {total_ada_needed:.2f}) {'✅' if main_ada/1000000 >= total_ada_needed else '❌'}")
        print(f"  Token: {main_tk} (Need: {total_token_needed}) {'✅' if main_tk >= total_token_needed else '❌'}")

        print("-" * 55)
        print(f"{'BATCH':<6} | {'ADA (Bal/Need)':<18} | {'TOKEN (Bal/Need)':<18}")
        print("-" * 55)
        for i, w in enumerate(batch_wallets):
            if i >= len(cases): break
            ada, tk = get_info(w['address'])
            need_ada = 2.0
            need_tk = int(cases[i]['amount_raw'])

            ada_status = "✔" if ada/1000000 >= need_ada else "❌"
            tk_status = "✔" if tk >= need_tk else "❌"

            print(f"{i+1:<6} | {ada/1000000:0.2f}/{need_ada:0.2f} {ada_status:<2} | {tk}/{need_tk} {tk_status}")

    def check_all_evm_balances(self, case_file, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"\n--- 💰 EVM Balance Diagnostics ({self.network_name}) ---")

        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        total_token_needed = sum([int(c['amount_raw']) for c in cases])
        total_wan_needed = (len(cases) * 0.1) + 0.5 # 0.1 WAN per case + 0.5 WAN buffer

        with open('config/contract_accounts.json', 'r') as f:
            contracts = json.load(f)[self.network_name]['evm']

        token_addr = contracts.get('gx_token', '')
        erc20_abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]
        token_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(token_addr), abi=erc20_abi) if token_addr else None

        def get_info(addr):
            c_addr = self.w3.to_checksum_address(addr)
            wan = self.w3.eth.get_balance(c_addr)
            tk = token_contract.functions.balanceOf(c_addr).call() if token_contract else 0
            return wan, tk

        main_wan, main_tk = get_info(main_wallet['address'])
        main_wan_f = float(self.w3.from_wei(main_wan, 'ether'))
        print(f"MAIN WALLET: {main_wallet['address']}")
        print(f"  WAN: {main_wan_f:.4f} (Need: {total_wan_needed:.4f}) {'✅' if main_wan_f >= total_wan_needed else '❌'}")
        print(f"  Token: {main_tk} (Need: {total_token_needed}) {'✅' if main_tk >= total_token_needed else '❌'}")

        print("-" * 55)
        print(f"{'BATCH':<6} | {'WAN (Bal/Need)':<18} | {'TOKEN (Bal/Need)':<18}")
        print("-" * 55)
        for i, w in enumerate(batch_wallets):
            if i >= len(cases): break
            wan, tk = get_info(w['address'])
            wan_f = float(self.w3.from_wei(wan, 'ether'))
            need_wan = 0.1
            need_tk = int(cases[i]['amount_raw'])

            wan_status = "✔" if wan_f >= need_wan else "❌"
            tk_status = "✔" if tk >= need_tk else "❌"

            print(f"{i+1:<6} | {wan_f:0.4f}/{need_wan:0.4f} {wan_status:<2} | {tk}/{need_tk} {tk_status}")

    def distribute_cardano_funds(self, case_file, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"💸 Distributing ADA & Tokens from {main_wallet['address'][:10]} to batch wallets...")

        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        with open('config/contract_accounts.json', 'r') as f:
            contracts = json.load(f)[self.network_name]['cardano']
        policy_id_hex = contracts.get('demo_token_policy', '')
        token_name_hex = contracts.get('demo_token_name', '')

        sk_bytes = bytes.fromhex(main_wallet['private_key'])
        main_sk = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
        main_addr = Address.from_primitive(main_wallet['address'])

        tx_builder = TransactionBuilder(self.cardano_context)
        tx_builder.add_input_address(main_addr)

        for i, w in enumerate(batch_wallets):
            if i >= len(cases): break
            dest_addr = Address.from_primitive(w['address'])
            amount_tk = int(cases[i]['amount_raw'])

            val = Value(coin=5000000) # 5 ADA
            if policy_id_hex:
                val.multi_asset = MultiAsset({
                    PolicyId.from_primitive(policy_id_hex): Asset({
                        AssetName.from_primitive(token_name_hex) if token_name_hex else AssetName(b""): amount_tk
                    })
                })
            tx_builder.add_output(TransactionOutput(dest_addr, amount=val))

        signed_tx = tx_builder.build_and_sign([main_sk], change_address=main_addr)
        self.cardano_context.submit_tx(signed_tx.to_cbor())
        print(f"✅ Distribution TX submitted: {signed_tx.id}")
        print("⏳ Waiting for confirmation (Cardano can take a minute)...")

    def distribute_evm_funds(self, case_file, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"💸 Distributing WAN & Tokens from {main_wallet['address'][:10]} to batch wallets...")

        cases = pd.read_csv(os.path.join("testcases", case_file)).to_dict('records')
        with open('config/contract_accounts.json', 'r') as f:
            contracts = json.load(f)[self.network_name]['evm']
        token_addr = contracts.get('gx_token', '')

        main_pk = main_wallet['private_key']
        main_addr = self.w3.to_checksum_address(main_wallet['address'])

        nonce = self.w3.eth.get_transaction_count(main_addr)
        for i, w in enumerate(batch_wallets):
            if i >= len(cases): break
            dest_addr = self.w3.to_checksum_address(w['address'])

            # 1. Send WAN
            tx_wan = {
                'nonce': nonce,
                'to': dest_addr,
                'value': self.w3.to_wei(0.1, 'ether'),
                'gas': 21000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            }
            signed_wan = self.w3.eth.account.sign_transaction(tx_wan, main_pk)
            tx_hash_wan = self.w3.eth.send_raw_transaction(signed_wan.raw_transaction)
            print(f"  Sent WAN to {w['address'][:10]}, TX: {tx_hash_wan.hex()}")
            nonce += 1

            tx_hash_tk = None
            # 2. Send Token
            if token_addr:
                amount_tk = int(cases[i]['amount_raw'])
                erc20_abi = [{"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}]
                token_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(token_addr), abi=erc20_abi)
                tx_tk = token_contract.functions.transfer(dest_addr, amount_tk).build_transaction({
                    'from': main_addr,
                    'nonce': nonce,
                    'gas': 100000,
                    'gasPrice': self.w3.eth.gas_price,
                    'chainId': self.w3.eth.chain_id
                })
                signed_tk = self.w3.eth.account.sign_transaction(tx_tk, main_pk)
                tx_hash_tk = self.w3.eth.send_raw_transaction(signed_tk.raw_transaction)
                print(f"  Sent Token to {w['address'][:10]}, TX: {tx_hash_tk.hex()}")
                nonce += 1

            print("    ⏳ Waiting for confirmations...")
            try:
                self.w3.eth.wait_for_transaction_receipt(tx_hash_wan, timeout=300)
                print("    ✅ WAN Distribution Success!")
                if tx_hash_tk:
                    self.w3.eth.wait_for_transaction_receipt(tx_hash_tk, timeout=300)
                    print("    ✅ Token Distribution Success!")
            except Exception as e:
                print(f"    ⚠️ Warning: Timeout waiting for distribution receipt: {e}")

    def sweep_cardano_assets(self, destination_address, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        all_wallets = [main_wallet] + batch_wallets
        dest_addr = Address.from_primitive(destination_address)

        print(f"🧹 Sweeping all Cardano assets to {destination_address}...")

        for w in all_wallets:
            sk_bytes = bytes.fromhex(w['private_key'])
            sk = PaymentExtendedSigningKey.from_primitive(sk_bytes) if len(sk_bytes) == 64 else PaymentSigningKey.from_primitive(sk_bytes)
            addr = Address.from_primitive(w['address'])

            utxos = self.cardano_context.utxos(w['address'])
            if not utxos: continue

            print(f"  - Sweeping wallet {w['address'][:10]}...")
            tx_builder = TransactionBuilder(self.cardano_context)
            tx_builder.add_input_address(addr)

            signed_tx = tx_builder.build_and_sign([sk], change_address=dest_addr)
            self.cardano_context.submit_tx(signed_tx.to_cbor())
            print(f"    🚀 Cardano Sweep TX Submitted: {signed_tx.id}")
            print("    ✅ Cardano Sweep Success!")

    def sweep_evm_assets(self, destination_address, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        all_wallets = [main_wallet] + batch_wallets
        dest_addr = self.w3.to_checksum_address(destination_address)

        with open('config/contract_accounts.json', 'r') as f:
            contracts = json.load(f)[self.network_name]['evm']
        token_addr = contracts.get('gx_token', '')
        erc20_abi = [
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
            {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
        ]
        token_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(token_addr), abi=erc20_abi) if token_addr else None

        print(f"🧹 Sweeping all EVM assets to {destination_address}...")

        for w in all_wallets:
            try:
                pk = w['private_key']
                addr = self.w3.to_checksum_address(w['address'])
                nonce = self.w3.eth.get_transaction_count(addr)

                # 1. Sweep Tokens
                if token_contract:
                    tk_bal = token_contract.functions.balanceOf(addr).call()
                else:
                    tk_bal = 0

                if tk_bal > 0:
                    print(f"  - Sweeping {tk_bal} tokens from {w['address'][:10]}...")
                    tx_tk = token_contract.functions.transfer(dest_addr, tk_bal).build_transaction({
                        'from': addr,
                        'nonce': nonce,
                        'gas': 100000,
                        'gasPrice': self.w3.eth.gas_price,
                        'chainId': self.w3.eth.chain_id
                    })
                    signed_tk = self.w3.eth.account.sign_transaction(tx_tk, pk)
                    tx_hash_tk = self.w3.eth.send_raw_transaction(signed_tk.raw_transaction)
                    print(f"    🚀 Token Sweep TX Submitted: {tx_hash_tk.hex()}")
                    try:
                        self.w3.eth.wait_for_transaction_receipt(tx_hash_tk, timeout=300)
                        print("    ✅ Token Sweep Success!")
                    except Exception as e:
                        print(f"    ⚠️ Warning: Timeout waiting for token sweep receipt: {e}")
                    nonce += 1

                # 2. Sweep Native
                wan_bal = self.w3.eth.get_balance(addr)
                gas_price = self.w3.eth.gas_price
                gas_limit = 21000
                total_fee = gas_price * gas_limit

                if wan_bal > total_fee:
                    print(f"  - Sweeping {self.w3.from_wei(wan_bal - total_fee, 'ether')} WAN from {w['address'][:10]}...")
                    tx_wan = {
                        'nonce': nonce,
                        'to': dest_addr,
                        'value': wan_bal - total_fee,
                        'gas': gas_limit,
                        'gasPrice': gas_price,
                        'chainId': self.w3.eth.chain_id
                    }
                    signed_wan = self.w3.eth.account.sign_transaction(tx_wan, pk)
                    tx_hash_wan = self.w3.eth.send_raw_transaction(signed_wan.raw_transaction)
                    print(f"    🚀 WAN Sweep TX Submitted: {tx_hash_wan.hex()}")
                    try:
                        self.w3.eth.wait_for_transaction_receipt(tx_hash_wan, timeout=300)
                        print("    ✅ WAN Sweep Success!")
                    except Exception as e:
                        print(f"    ⚠️ Warning: Timeout waiting for WAN sweep receipt: {e}")
            except Exception as e:
                print(f"  ❌ Error sweeping wallet {w['address'][:10]}: {e}")
