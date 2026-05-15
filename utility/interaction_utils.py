import json
import os

def get_network():
    print("\n👉 Select Network:\n1. Mainnet\n2. Preprod (Testnet)")
    c = input("Choice: ").strip()
    return 'mainnet' if c == '1' else 'preprod'

def get_direction():
    print("\n👉 Select Direction:\n1. Cardano -> EVM (Outbound)\n2. EVM -> Cardano (Inbound)")
    c = input("Choice: ").strip()
    return 'cardano_to_evm' if c == '1' else 'evm_to_cardano'

def get_case_file(direction):
    d = os.path.join("testcases", direction)
    files = [f for f in os.listdir(d) if f.endswith('.csv')]
    if not files: return None
    print("\n👉 Select Case File:")
    for i, f in enumerate(files): print(f"{i+1}. {f}")
    c = int(input("Choice: ")) - 1
    return files[c]

def get_cardano_wallet_info():
    if not os.path.exists("current_cardano_wallets.json"): return None
    with open("current_cardano_wallets.json", "r") as f:
        d = json.load(f)[0]
        return d['mnemonic'], d['main_wallet'], d['batch_wallets'], d.get('redeemer_wallets', [])

def get_evm_wallet_info():
    if not os.path.exists("current_evm_wallets.json"): return None
    with open("current_evm_wallets.json", "r") as f:
        d = json.load(f)[0]
        return d['mnemonic'], d['main_wallet'], d['batch_wallets'], d.get('wallet_name')

def get_confirmed_address(prompt):
    while True:
        a = input(prompt).strip()
        if input(f"Confirm {a}? (y/n): ").lower() == 'y': return a
