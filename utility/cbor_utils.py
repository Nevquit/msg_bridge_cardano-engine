import cbor2

def to_indefinite_cbor(obj):
    """
    Recursive encoder for indefinite-length CBOR structures (9f ... ff)
    with support for Plutus-style Tag (Major Type 6) constructors.
    """
    if obj is None:
        return cbor2.dumps(None)
    if isinstance(obj, cbor2.CBORTag):
        # d8 <tag> 9f ... ff
        res = b'\xd8' + bytes([obj.tag]) + b'\x9f'
        if isinstance(obj.value, list):
            for item in obj.value:
                res += to_indefinite_cbor(item)
        else:
            res += to_indefinite_cbor(obj.value)
        res += b'\xff'
        return res
    elif isinstance(obj, list):
        # 9f ... ff
        res = b'\x9f'
        for item in obj:
            res += to_indefinite_cbor(item)
        res += b'\xff'
        return res
    elif isinstance(obj, bytes) and len(obj) > 64:
        # Long bytes can be definite (58 1c ...) as shown in success hex
        return cbor2.dumps(obj)
    else:
        return cbor2.dumps(obj)
