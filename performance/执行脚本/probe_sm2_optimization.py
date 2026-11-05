from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from api_service4.app.services.native_sm2 import native_sm2_backend
from api_service4.app.services.payment_crypto import generate_sm2_keypair, sm2_encrypt
from gmssl import sm2

def main():
    native = native_sm2_backend()
    assert native is not None, 'Native OpenSSL SM2 support is required for this optimization'
    pair = generate_sm2_keypair()
    plaintext=b'00112233445566778899aabbccddeeff'
    ciphertext=bytes.fromhex(sm2_encrypt(pair['public_key'],plaintext))
    assert native.decrypt(pair['private_key'],ciphertext)==plaintext
    tampered=ciphertext[:-1]+bytes([ciphertext[-1]^1])
    try: native.decrypt(pair['private_key'],tampered)
    except ValueError: pass
    else: raise AssertionError('C3 tampering was not rejected')
    old=sm2.CryptSM2(public_key='',private_key=pair['private_key'])
    for name,fn in [('gmssl',lambda:old.decrypt(ciphertext)),('OpenSSL EVP',lambda:native.decrypt(pair['private_key'],ciphertext))]:
        start=perf_counter()
        for _ in range(100): assert fn()==plaintext
        print(name,round((perf_counter()-start)*10,3),'ms per decrypt')
    with ThreadPoolExecutor(max_workers=9) as pool:
        assert all(r==plaintext for r in pool.map(lambda _:native.decrypt(pair['private_key'],ciphertext),range(200)))
    print('Interop, tamper rejection and concurrent contexts passed; library:',native.path)

if __name__=='__main__':main()
