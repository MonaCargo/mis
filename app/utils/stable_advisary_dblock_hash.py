import hashlib

# This is used to generate consitent hash for taking db lock (not affected on basisi of server restart )



def stable_int32_lock_key(key_str: str) -> int:
    hash_bytes = hashlib.sha256(key_str.encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:4], byteorder="big", signed=True)