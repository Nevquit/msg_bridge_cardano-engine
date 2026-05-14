import sys, os, time, json, warnings
warnings.filterwarnings("ignore")
from dotenv import load_dotenv
load_dotenv()
import pandas as pd
from utility.prepare_assets import PrepareAssets
from utility.interaction_utils import *
from sendtransactions.cardano_msg import cardano_to_evm_msg, consume_inbound_utxo
from sendtransactions.evm_msg import Erc20TokenRemote

def check_coverage(case_file, direction):
    cases = pd.read_csv(os.path.join("testcases", direction, case_file))
    info = get_cardano_wallet_info() if direction == "cardano_to_evm" else get_evm_wallet_info()
    if not info or len(info[2]) < len(cases):
        print(f"❌ Need {len(cases)} batch wallets. Run option 1.")
        return False
    return True

def main_menu(direction, case_file, network):
    print(f"\n🚀 {direction} | {case_file} | {network}")
    asset_preparer = PrepareAssets(network)
    while True:
        is_card = direction == "cardano_to_evm"
        t_name = "Cardano" if is_card else "EVM"
        print(f"\n1. 🛠️ Wallets\n2. 🔍 Balances\n3. 💸 Distribute\n4. 🚀 Transactions")
        if not is_card: print("5. 📥 Consume UTXO")
        print(f"6. 🧹 Sweep\n7. 🔙 Back\n8. 🚪 Exit")
        c = input("Choice: ").strip()
        if c == '1': asset_preparer.generate_wallets(input("Mnemonic: ").strip() or None)
        elif c == '2':
            if check_coverage(case_file, direction):
                if is_card: asset_preparer.check_all_cardano_balances(case_file, get_cardano_wallet_info()[:3])
                else: asset_preparer.check_all_evm_balances(case_file, get_evm_wallet_info()[:3])
        elif c == '3':
            if check_coverage(case_file, direction):
                if is_card: asset_preparer.distribute_cardano_funds(case_file, get_cardano_wallet_info()[:3])
                else: asset_preparer.distribute_evm_funds(case_file, get_evm_wallet_info()[:3])
        elif c == '4':
            if check_coverage(case_file, direction):
                if is_card: run_cardano_to_evm(case_file, network, asset_preparer.cardano_context)
                else: run_evm_to_cardano(case_file, network)
        elif c == '5' and not is_card: run_consume(network, asset_preparer.cardano_context)
        elif c == '6':
            dest = get_confirmed_address(f"{t_name} Address: ")
            if is_card: asset_preparer.sweep_cardano_assets(dest, get_cardano_wallet_info()[:3])
            else: asset_preparer.sweep_evm_assets(dest, get_evm_wallet_info()[:3])
        elif c == '7': return
        elif c == '8': sys.exit(0)

def run_cardano_to_evm(cf, net, ctx):
    _, _, batch, _ = get_cardano_wallet_info()
    cases = pd.read_csv(os.path.join("testcases", "cardano_to_evm", cf)).to_dict('records')
    with open('config/contract_accounts.json', 'r') as f: con = json.load(f)[net]['cardano']
    for i, case in enumerate(cases):
        if i >= len(batch): break
        tid, err = cardano_to_evm_msg(ctx, batch[i]['private_key'], batch[i]['address'], case['to_address'], case['amount_raw'], con['outbound_demo'], con.get('outbound_token_policy', ''), demo_token_policy=con.get('demo_token_policy'), demo_token_name=con.get('demo_token_name'))
        print(f"  Result: {tid or err}")

def run_evm_to_cardano(cf, net):
    _, _, batch, _ = get_evm_wallet_info()
    cases = pd.read_csv(os.path.join("testcases", "evm_to_cardano", cf)).to_dict('records')
    with open('config/rpc.json', 'r') as f: rpc = json.load(f)['evm'][net]['url']
    with open('config/contract_accounts.json', 'r') as f: con = json.load(f)[net]['evm']
    rem = Erc20TokenRemote(rpc, con['token_home'], 'config/abis/ERC20TokenHome4CardanoV2.json')
    for i, case in enumerate(cases):
        if i >= len(batch): break
        print(f"Approving...")
        rem.approve(batch[i]['private_key'], con['gx_token'], con['token_home'], case['amount_raw'])
        tx, err = rem.send(batch[i]['private_key'], rem.encode_plutus_data(case['to_address'], case['amount_raw']))
        print(f"  Result: {tx or err}")

def run_consume(net, ctx):
    info = get_cardano_wallet_info()
    if not info:
        print("❌ Error: Wallets not created yet. Please use option 1 first.")
        return
    _, _, batch, _ = info
    with open('config/contract_accounts.json', 'r') as f:
        conf = json.load(f)[net]
        con_c = conf['cardano']
        evm_token_home = conf['evm']['token_home']
    h, idx = input("Hash: ").strip(), int(input("Index: ").strip())
    tid, err = consume_inbound_utxo(ctx, batch[0]['private_key'], batch[0]['address'], h, idx, con_c['inbound_demo'], con_c['inbound_demo_cbor'], con_c['inbound_token_cbor'], con_c['demo_token_cbor'], con_c['demo_token_policy'], evm_token_home)
    print(f"  Result: {tid or err}")

if __name__ == "__main__":
    net = get_network()
    while True:
        direc = get_direction()
        cf = get_case_file(direc)
        if cf: main_menu(direc, cf, net)
