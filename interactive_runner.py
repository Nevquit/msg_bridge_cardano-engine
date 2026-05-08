import sys
import os
import time
import json
import pandas as pd
from pycardano import BlockFrostChainContext, Network

from utility.prepare_assets import PrepareAssets
from utility.interaction_utils import (
    get_network, get_direction, get_case_file,
    get_cardano_wallet_info, get_evm_wallet_info, get_confirmed_address
)
from sendtransactions.cardano_msg import cardano_to_evm_msg
from sendtransactions.evm_msg import Erc20TokenRemote

def main_menu(direction, case_file, network):
    print(f"\n🚀 XPort Bridge Runner | Direction: {direction} | Case: {case_file} | Net: {network}")
    try:
        asset_preparer = PrepareAssets(network)
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize backend (likely missing API keys): {e}")
        asset_preparer = None

    try:
        cases_df = pd.read_csv(os.path.join("testcases", case_file))
    except Exception as e:
        print(f"❌ Error reading case file: {e}")
        return
    num_cases = len(cases_df)

    while True:
        is_cardano = direction == "cardano_to_evm"
        target_name = "Cardano" if is_cardano else "EVM"

        print("\n" + "="*50)
        print(f"📬 {target_name} -> {'EVM' if is_cardano else 'Cardano'} Bridge Menu")
        print("="*50)
        print("1. 🛠️  Create Wallets (Cardano + EVM)")
        print(f"2. 🔍 Check {target_name} Balances")
        print(f"3. 💸 Distribute Funds ({target_name})")
        print("4. 🚀 Run Transactions")
        print("6. 🔙 Change Direction/Case")
        print("7. 🚪 Exit")
        print("="*50)
        choice = input("👉 Choice: ").strip()

        if choice == '1':
            mnemonic = input("👉 Enter mnemonic (24 words): ").strip()
            if asset_preparer: asset_preparer.generate_wallets(mnemonic)
            else: print("❌ Asset preparer not initialized.")

        elif choice == '2':
            if not asset_preparer:
                print("❌ Asset preparer not initialized.")
                continue
            if is_cardano:
                info = get_cardano_wallet_info()
                if info: asset_preparer.check_all_cardano_balances(case_file, info[:3])
                else: print("❌ No Cardano wallets found.")
            else:
                info = get_evm_wallet_info()
                if info: asset_preparer.check_all_evm_balances(case_file, info[:3])
                else: print("❌ No EVM wallets found.")

        elif choice == '3':
            if not asset_preparer:
                print("❌ Asset preparer not initialized.")
                continue
            if is_cardano:
                info = get_cardano_wallet_info()
                if info: asset_preparer.distribute_cardano_funds(case_file, info[:3])
            else:
                info = get_evm_wallet_info()
                if info: asset_preparer.distribute_evm_funds(case_file, info[:3])

        elif choice == '4':
            if not asset_preparer:
                print("❌ Asset preparer not initialized.")
                continue
            if is_cardano:
                run_cardano_to_evm(case_file, network, asset_preparer.cardano_context)
            else:
                run_evm_to_cardano(case_file, network)

        elif choice == '6': return
        elif choice == '7': sys.exit(0)

def run_cardano_to_evm(case_file, network, context):
    info = get_cardano_wallet_info()
    if not info: return
    _, _, batch_wallets, _ = info
    cases = pd.read_csv(case_file).to_dict('records')

    with open('config/contract_accounts.json', 'r') as f:
        contracts = json.load(f)[network]['cardano']

    print(f"🚀 Running {len(cases)} Cardano -> EVM transactions...")
    for i, case in enumerate(cases):
        if i >= len(batch_wallets): break
        wallet = batch_wallets[i]
        print(f"[{i+1}/{len(cases)}] Sending from {wallet['address'][:10]}...")
        tx_id, err = cardano_to_evm_msg(
            context,
            wallet['private_key'],
            case['to_address'],
            case['amount_raw'],
            contracts['outbound_demo'],
            contracts.get('outbound_token_policy', '')
        )
        if tx_id: print(f"  ✅ Success! TX ID: {tx_id}")
        else: print(f"  ❌ Error: {err}")

def run_evm_to_cardano(case_file, network):
    info = get_evm_wallet_info()
    if not info: return
    _, _, batch_wallets, _ = info
    cases = pd.read_csv(case_file).to_dict('records')

    with open('config/rpc.json', 'r') as f:
        rpc_url = json.load(f)['evm'][network]['url']
    with open('config/contract_accounts.json', 'r') as f:
        contracts = json.load(f)[network]['evm']

    remote = Erc20TokenRemote(rpc_url, contracts['token_home'], 'config/abis/ERC20TokenHome4CardanoV2.json')

    print(f"🚀 Running {len(cases)} EVM -> Cardano transactions...")
    for i, case in enumerate(cases):
        if i >= len(batch_wallets): break
        wallet = batch_wallets[i]
        plutus_data = remote.encode_plutus_data(case['to_address'], case['amount_raw'])
        print(f"[{i+1}/{len(cases)}] Sending from {wallet['address'][:10]}...")
        tx_hash, err = remote.send(wallet['private_key'], plutus_data)
        if tx_hash: print(f"  ✅ Success! Hash: {tx_hash}")
        else: print(f"  ❌ Error: {err}")

def run():
    print("👋 Welcome to Cardano-EVM XPort Bridge Runner")
    network = get_network()
    while True:
        direction = get_direction()
        case_file = get_case_file(direction)
        if not case_file: continue
        main_menu(direction, case_file, network)

if __name__ == "__main__":
    try: run()
    except KeyboardInterrupt: sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}")
