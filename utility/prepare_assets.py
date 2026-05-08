import os
import json
import binascii
from mnemonic import Mnemonic
from pycardano import (
    Address, Network, PaymentKeyPair, StakeKeyPair,
    BlockFrostChainContext, TransactionBuilder, TransactionOutput,
    HDWallet, PaymentSigningKey, StakeSigningKey, PaymentVerificationKey, StakeVerificationKey
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
        self.blockfrost_project_id = os.getenv("BLOCKFROST_API_KEY")
        if not self.blockfrost_project_id:
            raise ValueError("BLOCKFROST_API_KEY environment variable is not set")
        self.cardano_context = BlockFrostChainContext(self.blockfrost_project_id, self.cardano_network)

        self.evm_url = self.rpc_config['evm'][network_name]['url']
        self.w3 = Web3(Web3.HTTPProvider(self.evm_url))

    def generate_wallets(self, mnemonic_phrase, num_batch=5):
        # Generate Cardano Wallets
        hd_wallet = HDWallet.from_mnemonic(mnemonic_phrase)

        def derive_cardano(index):
            # CIP-1852 path: m/1852'/1815'/0'/0/index
            payment_hd = hd_wallet.derive_from_path(f"m/1852'/1815'/0'/0/{index}")
            stake_hd = hd_wallet.derive_from_path(f"m/1852'/1815'/0'/2/0")

            payment_sk = PaymentSigningKey.from_primitive(payment_hd.xprivate_key)
            stake_sk = StakeSigningKey.from_primitive(stake_hd.xprivate_key)

            payment_vk = payment_sk.to_verification_key()
            stake_vk = stake_sk.to_verification_key()

            addr = Address(payment_vk.hash(), stake_vk.hash(), network=self.cardano_network)
            return {
                "address": str(addr),
                "private_key": payment_sk.to_primitive().hex()
            }

        main_cardano = derive_cardano(0)

        batch_cardano = []
        for i in range(1, num_batch + 1):
            batch_cardano.append(derive_cardano(i))

        cardano_data = {
            "wallet_name": "Default",
            "main_wallet": main_cardano,
            "batch_wallets": batch_cardano
        }

        with open("current_cardano_wallets.json", "w") as f:
            json.dump([cardano_data], f, indent=4)

        # Generate EVM Wallets
        Account.enable_unaudited_hdwallet_features()
        main_evm_acc = Account.from_mnemonic(mnemonic_phrase)
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

        evm_data = {
            "wallet_name": "Default",
            "main_wallet": main_evm,
            "batch_wallets": batch_evm
        }

        with open("current_evm_wallets.json", "w") as f:
            json.dump([evm_data], f, indent=4)

        print("✅ Wallets generated and saved to current_cardano_wallets.json and current_evm_wallets.json")

    def check_all_cardano_balances(self, case_file, wallets_info):
        _, main_wallet, batch_wallets, _ = wallets_info
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

    def check_all_evm_balances(self, case_file, wallets_info):
        _, main_wallet, batch_wallets, _ = wallets_info
        print(f"\n--- 💰 EVM Balances ({self.network_name}) ---")

        main_bal = self.w3.eth.get_balance(main_wallet['address'])
        print(f"Main Wallet: {main_wallet['address']} | Balance: {self.w3.from_wei(main_bal, 'ether')} WAN")

        for i, w in enumerate(batch_wallets):
            bal = self.w3.eth.get_balance(w['address'])
            print(f"Batch {i+1}: {w['address']} | Balance: {self.w3.from_wei(bal, 'ether')} WAN")

    def distribute_cardano_funds(self, case_file, wallets_info):
        _, main_wallet, batch_wallets, _ = wallets_info
        print(f"💸 Distributing ADA from {main_wallet['address'][:10]} to batch wallets...")

        main_sk = PaymentSigningKey.from_primitive(bytes.fromhex(main_wallet['private_key']))
        main_addr = Address.from_primitive(main_wallet['address'])

        tx_builder = TransactionBuilder(self.cardano_context)
        tx_builder.add_input_address(main_addr)

        for w in batch_wallets:
            tx_builder.add_output(TransactionOutput(Address.from_primitive(w['address']), amount=5000000)) # 5 ADA

        signed_tx = tx_builder.build_and_sign([main_sk], change_address=main_addr)
        self.cardano_context.submit_tx(signed_tx.to_cbor())
        print(f"✅ Distribution TX submitted: {signed_tx.id}")

    def distribute_evm_funds(self, case_file, wallets_info):
        _, main_wallet, batch_wallets, _ = wallets_info
        print(f"💸 Distributing WAN from {main_wallet['address'][:10]} to batch wallets...")

        main_pk = main_wallet['private_key']
        main_addr = main_wallet['address']

        for w in batch_wallets:
            nonce = self.w3.eth.get_transaction_count(main_addr)
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
