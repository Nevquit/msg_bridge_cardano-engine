import requests
import json

def inspect():
    bf_id = "preprod2Q5B1rd51PaEDkV2ZwoNc5381DZ8uczS"
    tx_hash = "bbba1fbc4a6c4d5ab5884dff7350f26c69c68f185a481eca67e98d939a3406fd"
    url = f"https://cardano-preprod.blockfrost.io/api/v0/txs/{tx_hash}/utxos"
    res = requests.get(url, headers={"project_id": bf_id})
    utxos = res.json()

    print(f"--- Outputs of TX {tx_hash} ---")
    for out in utxos.get('outputs', []):
        print(f"Address: {out['address']}")
        print(f"Amount: {out['amount']}")
        if out['inline_datum']:
             print(f"Inline Datum: {out['inline_datum'][:50]}...")

if __name__ == '__main__':
    inspect()
