import cbor2
from pycardano import Address as CardanoAddress, VerificationKeyHash, ScriptHash

def encode_plutus_data(target_cardano_addr, amount):
    addr = CardanoAddress.from_primitive(target_cardano_addr)
    payment_cred = addr.payment_part.to_primitive()
    stake_cred = addr.staking_part.to_primitive() if addr.staking_part else None

    p_tag = 0 if isinstance(addr.payment_part, VerificationKeyHash) else 1

    # Plutus Address constructor (Tag 121)
    plutus_addr = cbor2.CBORTag(121, [
        cbor2.CBORTag(121 + p_tag, [payment_cred]),
        cbor2.CBORTag(121, [cbor2.CBORTag(121, [stake_cred])]) if stake_cred else cbor2.CBORTag(122, [])
    ])

    # LocalAddress constructor (Tag 122)
    # The contract expects msgAddress.arrayValue.length == 1
    # Inside msgAddress is msgAddressFields, which also has arrayValue.length == 1
    # Inside msgAddressFields is receiver, which is a Tag

    msg_address_fields = cbor2.CBORTag(121, [plutus_addr])
    msg_address = cbor2.CBORTag(122, [msg_address_fields])

    # BeneficiaryData Tag 121 (Constructor 0)
    beneficiary_data = cbor2.CBORTag(121, [msg_address, int(amount)])

    # The contract starts with require(cb.arrayValue.length == 1)
    # Then fields = cb.arrayValue[0]
    final_cbor = [beneficiary_data]

    return cbor2.dumps(final_cbor).hex()

addr = "addr_test1qpv3ww25tec4s2gzpglfpc0d34cfjnn8swhcpvler5t0xu30s4dpfufyvz7gdqusv2cjhjkfgju67zqy39l2rw8anhzq8y2f2g"
print(encode_plutus_data(addr, 10000))
