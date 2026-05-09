import os
import json
import binascii
from mnemonic import Mnemonic
from pycardano import (
    Address, Network, PaymentKeyPair, StakeKeyPair,
    BlockFrostChainContext, TransactionBuilder, TransactionOutput,
    HDWallet, PaymentSigningKey, StakeSigningKey, PaymentVerificationKey, StakeVerificationKey,
    PaymentExtendedSigningKey, StakeExtendedSigningKey
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
        num_batch = max(cardano_count, evm_count, 5)

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
        batch_cardano = [derive_cardano(i) for i in range(1, num_batch + 1)]

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
        for i in range(1, num_batch + 1):
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

        print(f"✅ Wallets generated and saved to current_cardano_wallets.json, current_evm_wallets.json and wallets/ directory")

    def check_all_cardano_balances(self, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"\n--- 💰 Cardano Balances ({self.network_name}) ---")

        def get_bal(addr):
            try:
                return self.cardano_context.utxos(addr)
            except:
                return []

        main_utxos = get_bal(main_wallet['address'])
        main_lovelace = sum([utxo.output.amount.coin for utxo in main_utxos])
        print(f"Main Wallet: {main_wallet['address']} | Balance: {main_lovelace/1000000} ADA")

        for i, w in enumerate(batch_wallets):
            utxos = get_bal(w['address'])
            lovelace = sum([utxo.output.amount.coin for utxo in utxos])
            print(f"Batch {i+1}: {w['address']} | Balance: {lovelace/1000000} ADA")

    def check_all_evm_balances(self, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"\n--- 💰 EVM Balances ({self.network_name}) ---")

        main_bal = self.w3.eth.get_balance(main_wallet['address'])
        print(f"Main Wallet: {main_wallet['address']} | Balance: {self.w3.from_wei(main_bal, 'ether')} WAN")

        for i, w in enumerate(batch_wallets):
            bal = self.w3.eth.get_balance(w['address'])
            print(f"Batch {i+1}: {w['address']} | Balance: {self.w3.from_wei(bal, 'ether')} WAN")

    def distribute_cardano_funds(self, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"💸 Distributing ADA from {main_wallet['address'][:10]} to batch wallets...")

        sk_bytes = bytes.fromhex(main_wallet['private_key'])
        if len(sk_bytes) == 64:
            main_sk = PaymentExtendedSigningKey.from_primitive(sk_bytes)
        else:
            main_sk = PaymentSigningKey.from_primitive(sk_bytes)
        main_addr = Address.from_primitive(main_wallet['address'])

        tx_builder = TransactionBuilder(self.cardano_context)
        tx_builder.add_input_address(main_addr)

        for w in batch_wallets:
            tx_builder.add_output(TransactionOutput(Address.from_primitive(w['address']), amount=5000000)) # 5 ADA

        signed_tx = tx_builder.build_and_sign([main_sk], change_address=main_addr)
        self.cardano_context.submit_tx(signed_tx.to_cbor())
        print(f"✅ Distribution TX submitted: {signed_tx.id}")
        print("⏳ Waiting for confirmation (Cardano can take a minute)...")
        # In a real tool we might wait for the TX to be seen in a block,
        # but for this script we'll just inform the user.

    def distribute_evm_funds(self, wallets_info):
        _, main_wallet, batch_wallets = wallets_info
        print(f"💸 Distributing WAN from {main_wallet['address'][:10]} to batch wallets...")

        main_pk = main_wallet['private_key']
        main_addr = main_wallet['address']

        nonce = self.w3.eth.get_transaction_count(main_addr)
        for w in batch_wallets:
            tx = {
                'nonce': nonce,
                'to': w['address'],
                'value': self.w3.to_wei(0.1, 'ether'),
                'gas': 21000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            }
            signed_tx = self.w3.eth.account.sign_transaction(tx, main_pk)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"  Sent to {w['address'][:10]}, TX Hash: {tx_hash.hex()}")
            print("    ⏳ Waiting for confirmation...")
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            nonce += 1
