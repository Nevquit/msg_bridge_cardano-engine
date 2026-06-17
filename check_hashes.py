import cbor2
import hashlib
import json
from pycardano import PlutusV1Script, PlutusV2Script, PlutusV3Script, plutus_script_hash, Address, Network

with open('config/contract_accounts.json', 'r') as f:
    conf = json.load(f)['preprod']['cardano']

def check(name, cbor_hex, expected_addr):
    print(f"--- {name} ---")
    data = bytes.fromhex(cbor_hex)
    # Check if it's already wrapped in a CBOR byte string
    try:
        unwrapped = cbor2.loads(data)
        if isinstance(unwrapped, bytes):
            print(f"  {name} is wrapped in CBOR byte string")
            raw = unwrapped
        else:
            print(f"  {name} is NOT wrapped in CBOR byte string (loaded {type(unwrapped)})")
            raw = data
    except:
        print(f"  {name} is NOT wrapped in CBOR byte string (decode failed)")
        raw = data

    for v, cls in [("V1", PlutusV1Script), ("V2", PlutusV2Script), ("V3", PlutusV3Script)]:
        try:
            # We hash the raw bytes as they would appear in the UPLC
            # PyCardano plutus_script_hash hashes the CBOR-wrapped version (with length prefix)
            script = cls(raw)
            h = plutus_script_hash(script)
            addr = Address(h, network=Network.TESTNET)
            status = "MATCH!" if str(addr) == expected_addr else ""
            print(f"  {v} with raw bytes: {addr} {status}")

            # Also try hashing the hex as-is if it's already a CBOR-wrapped script
            # In this case we don't wrap it again
            # But plutus_script_hash expects a PlutusScript object
        except Exception as e:
            print(f"  {v} failed: {e}")

check("Inbound Demo", conf['inbound_demo_cbor'], conf['inbound_demo_address'])
check("Outbound Demo", conf['outbound_demo_cbor'], conf['outbound_demo_address'])
