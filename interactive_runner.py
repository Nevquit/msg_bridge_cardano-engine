import sys
import os
import time
import warnings
import json
from dotenv import load_dotenv

# Suppress Deprecation Warnings from dependencies (e.g. cryptography on older Python versions)
warnings.filterwarnings("ignore")
try:
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass

load_dotenv()
import pandas as pd
from pycardano import BlockFrostChainContext, Network

from utility.prepare_assets import PrepareAssets
from utility.interaction_utils import (
    get_network, get_case_file,
    get_cardano_wallet_info, get_evm_wallet_info, get_confirmed_address
)
from sendtransactions.evm_msg import Erc20TokenRemote

def check_wallet_coverage(case_file):
    cases = pd.read_csv(os.path.join("testcases", "evm_to_cardano", case_file))
    res = get_evm_wallet_info()

    if not res:
        print("❌ Error: Wallets not created yet. Please use option 1 first.")
        return False

    batch_wallets = res[2]
    if len(batch_wallets) < len(cases):
        print(f"❌ Error: Need {len(cases)} batch addresses, but have {len(batch_wallets)}.")
        print("💡 Hint: Run option 1 (Create Wallets) to update the wallet set for this case.")
        return False
    return True

def main_menu(case_file, network):
    print(f"\n🚀 XPort Bridge Runner | Direction: EVM -> Cardano | Case: {case_file} | Net: {network}")
    try:
        asset_preparer = PrepareAssets(network)
    except Exception as e:
        print(f"❌ Error: Could not initialize backend: {e}")
        sys.exit(1)

    try:
        cases_df = pd.read_csv(os.path.join("testcases", "evm_to_cardano", case_file))
    except Exception as e:
        print(f"❌ Error reading case file: {e}")
        return

    while True:
        print("\n" + "="*50)
        print(f"📬 EVM -> Cardano Bridge Menu")
        print("="*50)
        print("1. 🛠️  Create Wallets (Cardano + EVM)")
        print(f"2. 🔍 Check EVM Balances")
        print(f"3. 💸 Distribute Funds (EVM)")
        print("4. 🚀 Run Transactions")
        print("5. 🧹 Sweep Assets")
        print("6. 🔙 Change Case")
        print("7. 🚪 Exit")
        print("="*50)
        choice = input("👉 Choice: ").strip()

        if choice == '1':
            mnemonic = input("👉 Enter mnemonic (24 words) or press Enter to generate: ").strip()
            if not mnemonic: mnemonic = None
            asset_preparer.generate_wallets(mnemonic)

        elif choice == '2':
            if check_wallet_coverage(case_file):
                info = get_evm_wallet_info()
                asset_preparer.check_all_evm_balances(case_file, info)

        elif choice == '3':
            if check_wallet_coverage(case_file):
                info = get_evm_wallet_info()
                asset_preparer.distribute_evm_funds(case_file, info)

        elif choice == '4':
            if check_wallet_coverage(case_file):
                run_evm_to_cardano(case_file, network)

        elif choice == '5':
            dest_addr = get_confirmed_address(f"👉 Enter Destination EVM Address: ")
            info = get_evm_wallet_info()
            if info: asset_preparer.sweep_evm_assets(dest_addr, info[:3])

        elif choice == '6': return
        elif choice == '7': sys.exit(0)

def run_evm_to_cardano(case_file, network):
    info = get_evm_wallet_info()
    if not info: return
    _, _, batch_wallets = info
    cases = pd.read_csv(os.path.join("testcases", "evm_to_cardano", case_file)).to_dict('records')

    with open('config/rpc.json', 'r') as f:
        rpc_url = json.load(f)['evm'][network]['url']
    with open('config/contract_accounts.json', 'r') as f:
        conf = json.load(f)[network]
        contracts = conf['evm']

    remote = Erc20TokenRemote(rpc_url, contracts['token_home'], 'config/abis/ERC20TokenHome4CardanoV2.json')

    print(f"🚀 Running {len(cases)} EVM -> Cardano transactions...")
    for i, case in enumerate(cases):
        if i >= len(batch_wallets): break
        wallet = batch_wallets[i]

        # 1. ERC20 Approval
        print(f"[{i+1}/{len(cases)}] Approving tokens for {wallet['address'][:10]}...")
        app_hash, app_err = remote.approve(wallet['private_key'], contracts['gx_token'], contracts['token_home'], case['amount_raw'])
        if app_err:
            print(f"  ❌ Approval Error: {app_err}")
            continue
        if app_hash != "Already Approved":
            print(f"  ✅ Approved! Hash: {app_hash}")
            time.sleep(5)
        else:
            print("  ℹ️ Already approved.")

        # 2. Bridge Send
        plutus_data = remote.encode_plutus_data(case['to_address'], case['amount_raw'])
        print(f"  📤 Sending cross-chain...")
        tx_hash, err = remote.send(wallet['private_key'], plutus_data)
        if tx_hash: print(f"  ✅ Success! Hash: {tx_hash}")
        else: print(f"  ❌ Error: {err}")

def run():
    print("\n👋 Welcome to Cardano-EVM XPort Bridge Runner")
    network = get_network()
    while True:
        case_file = get_case_file()
        if not case_file:
            print("❌ No CSV files found.")
            continue
        main_menu(case_file, network)

if __name__ == "__main__":
    try: run()
    except KeyboardInterrupt: sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}")
