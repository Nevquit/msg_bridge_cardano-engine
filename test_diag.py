from pycardano import Address
import cbor2

def diag():
    addr_str = "addr_test1qpv3ww25tec4s2gzpglfpc0d34cfjnn8swhcpvler5t0xu30s4dpfufyvz7gdqusv2cjhjkfgju67zqy39l2rw8anhzq8y2f2g"
    addr = Address.from_primitive(addr_str)
    print(f"Payment part type: {type(addr.payment_part)}")
    print(f"Payment part primitive: {addr.payment_part.to_primitive().hex()}")
    print(f"Staking part type: {type(addr.staking_part)}")
    print(f"Staking part primitive: {addr.staking_part.to_primitive().hex()}")

    p_tag = 0 # PubKeyHash
    payment_cred = addr.payment_part.to_primitive()
    stake_cred = addr.staking_part.to_primitive()

    plutus_addr = cbor2.CBORTag(121, [
        cbor2.CBORTag(121 + p_tag, [payment_cred]),
        cbor2.CBORTag(121, [cbor2.CBORTag(121, [cbor2.CBORTag(121, [stake_cred])])])
    ])

    print(f"Plutus address fields count: {len(plutus_addr.value)}")

    # Redundant wrapping check
    msg_address_bad = cbor2.CBORTag(122, [cbor2.CBORTag(121, plutus_addr)])
    print(f"Bad MsgAddress fields count: {len(msg_address_bad.value)}")
    print(f"Bad MsgAddress first field type: {type(msg_address_bad.value[0])}")

    msg_address_good = cbor2.CBORTag(122, [plutus_addr])
    print(f"Good MsgAddress fields count: {len(msg_address_good.value)}")
    print(f"Good MsgAddress first field fields count: {len(msg_address_good.value[0].value)}")

diag()
