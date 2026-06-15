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
    get_network, get_direction, get_case_file,
    get_cardano_wallet_info, get_evm_wallet_info, get_confirmed_address
)
from sendtransactions.cardano_msg import cardano_to_evm_msg, receive_from_evm_msg
from sendtransactions.evm_msg import Erc20TokenRemote

def check_wallet_coverage(case_file, direction):
    cases = pd.read_csv(os.path.join("testcases", direction, case_file))
    is_cardano = direction == "cardano_to_evm"
    res = get_cardano_wallet_info() if is_cardano else get_evm_wallet_info()

    if not res:
        print("❌ Error: Wallets not created yet. Please use option 1 first.")
        return False

    batch_wallets = res[2]
    if len(batch_wallets) < len(cases):
        print(f"❌ Error: Need {len(cases)} batch addresses, but have {len(batch_wallets)}.")
        print("💡 Hint: Run option 1 (Create Wallets) to update the wallet set for this case.")
        return False
    return True

def main_menu(direction, case_file, network):
    print(f"\n🚀 XPort Bridge Runner | Direction: {direction} | Case: {case_file} | Net: {network}")
    try:
        asset_preparer = PrepareAssets(network)
    except Exception as e:
        print(f"❌ Error: Could not initialize backend: {e}")
        sys.exit(1)

    try:
        cases_df = pd.read_csv(os.path.join("testcases", direction, case_file))
    except Exception as e:
        print(f"❌ Error reading case file: {e}")
        return

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
        print("5. 🧹 Sweep Assets")
        if not is_cardano:
            print("6. 📥 Receive messages from other chains")

        last_option = '6' if is_cardano else '7'
        exit_option = '7' if is_cardano else '8'
        print(f"{last_option}. 🔙 Change Direction/Case")
        print(f"{exit_option}. 🚪 Exit")
        print("="*50)
        choice = input("👉 Choice: ").strip()

        if choice == '1':
            mnemonic = input("👉 Enter mnemonic (24 words) or press Enter to generate: ").strip()
            if not mnemonic: mnemonic = None
            asset_preparer.generate_wallets(mnemonic)

        elif choice == '2':
            if check_wallet_coverage(case_file, direction):
                if is_cardano:
                    info = get_cardano_wallet_info()
                    asset_preparer.check_all_cardano_balances(case_file, info)
                else:
                    info = get_evm_wallet_info()
                    asset_preparer.check_all_evm_balances(case_file, info)

        elif choice == '3':
            if check_wallet_coverage(case_file, direction):
                if is_cardano:
                    info = get_cardano_wallet_info()
                    asset_preparer.distribute_cardano_funds(case_file, info)
                else:
                    info = get_evm_wallet_info()
                    asset_preparer.distribute_evm_funds(case_file, info)

        elif choice == '4':
            if check_wallet_coverage(case_file, direction):
                if is_cardano:
                    run_cardano_to_evm(case_file, network, asset_preparer.cardano_context)
                else:
                    run_evm_to_cardano(case_file, network)

        elif choice == '5':
            dest_addr = get_confirmed_address(f"👉 Enter Destination {target_name} Address: ")
            if is_cardano:
                info = get_cardano_wallet_info()
                if info: asset_preparer.sweep_cardano_assets(dest_addr, info)
            else:
                info = get_evm_wallet_info()
                if info: asset_preparer.sweep_evm_assets(dest_addr, info[:3])

        elif choice == '6' and not is_cardano:
            run_receive_messages(network, asset_preparer.cardano_context)

        elif choice == last_option: return
        elif choice == exit_option: sys.exit(0)

def run_cardano_to_evm(case_file, network, context):
    info = get_cardano_wallet_info()
    if not info: return
    _, _, batch_wallets, _ = info
    cases = pd.read_csv(os.path.join("testcases", "cardano_to_evm", case_file)).to_dict('records')

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
            wallet['address'],
            case['to_address'],
            case['amount_raw'],
            contracts['outbound_demo_address'],
            contracts.get('outbound_token_policy', ''),
            demo_token_policy=contracts.get('demo_token_policy'),
            demo_token_name=contracts.get('demo_token_name')
        )
        if tx_id: print(f"  ✅ Success! TX ID: {tx_id}")
        else: print(f"  ❌ Error: {err}")

def run_receive_messages(network, context):
    info = get_cardano_wallet_info()
    if not info:
        print("❌ Error: Cardano wallets not found.")
        return
    _, main_wallet, _, _ = info

    tx_hash = input("👉 Enter Cardano transaction hash (from Step 1): ").strip()
    if tx_hash.startswith("0x"):
        tx_hash = tx_hash[2:]

    receiver_addr = input("👉 Enter receiving Cardano address: ").strip()
    if not receiver_addr:
        print("❌ Error: Receiver address is required.")
        return

    print(f"🚀 Attempting to consume InBoundToken for TX {tx_hash}...")
    try:
        tx_id, err = receive_from_evm_msg(context, main_wallet, tx_hash, receiver_addr, network)
    except Exception as e:
        tx_id, err = None, str(e)

    if tx_id:
        print(f"  ✅ Success! Cardano TX ID: {tx_id}")
    else:
        print(f"  ❌ Error: {err}")

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
        direction = get_direction()
        case_file = get_case_file(direction)
        if not case_file:
            print("❌ No CSV files found.")
            continue
        main_menu(direction, case_file, network)

if __name__ == "__main__":
    try: run()
    except KeyboardInterrupt: sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}")
