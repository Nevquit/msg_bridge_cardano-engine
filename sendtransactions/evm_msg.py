from web3 import Web3
import json
from pycardano import Address as CardanoAddress
import cbor2
from utility.cbor_utils import to_indefinite_cbor

class Erc20TokenRemote:
    def __init__(self, node_url, token_home_addr, abi_path):
        self.w3 = Web3(Web3.HTTPProvider(node_url))
        with open(abi_path, 'r') as f:
            abi = json.load(f)
            if 'abi' in abi: abi = abi['abi']
        self.contract = self.w3.eth.contract(address=token_home_addr, abi=abi)

    def encode_plutus_data(self, target_cardano_addr, amount):
        try:
            addr = CardanoAddress.from_primitive(target_cardano_addr)
            p_hash = addr.payment_part.to_primitive()
            s_hash = addr.staking_part.to_primitive() if addr.staking_part else None
            p_cred = cbor2.CBORTag(121, [p_hash])
            if s_hash:
                s_cred = cbor2.CBORTag(121, [cbor2.CBORTag(121, [cbor2.CBORTag(121, [s_hash])])])
            else:
                s_cred = cbor2.CBORTag(122, [])
            mesh_address = cbor2.CBORTag(121, [p_cred, s_cred])
            msg_address = cbor2.CBORTag(121, [mesh_address])
            cc_message = cbor2.CBORTag(121, [msg_address, int(amount)])
            return to_indefinite_cbor(cc_message)
        except:
            msg_address = cbor2.CBORTag(121, [target_cardano_addr.encode('utf-8')])
            cc_message = cbor2.CBORTag(121, [msg_address, int(amount)])
            return to_indefinite_cbor(cc_message)

    def approve(self, private_key, token_addr, spender_addr, amount, gas_limit=100000):
        account = self.w3.eth.account.from_key(private_key)
        with open('config/abis/XToken.json', 'r') as f:
            token_abi = json.load(f)
            if 'abi' in token_abi: token_abi = token_abi['abi']
        token_contract = self.w3.eth.contract(address=token_addr, abi=token_abi)
        allowance = token_contract.functions.allowance(account.address, spender_addr).call()
        if allowance >= int(amount): return "Already Approved", None
        tx = token_contract.functions.approve(spender_addr, int(amount)).build_transaction({
            'from': account.address, 'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': gas_limit, 'gasPrice': self.w3.eth.gas_price
        })
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex(), None

    def send(self, private_key, plutus_data, gas_limit=300000):
        account = self.w3.eth.account.from_key(private_key)
        tx = self.contract.functions.send(plutus_data).build_transaction({
            'from': account.address, 'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': gas_limit, 'gasPrice': self.w3.eth.gas_price
        })
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex(), None
