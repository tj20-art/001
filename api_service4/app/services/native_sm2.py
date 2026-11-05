"""Optional in-process OpenSSL EVP SM2 decryption for gmssl C1C2C3 packets.

Only encoding changes here; OpenSSL performs SM2 and verifies its C3 digest.
Each call owns an EVP context. Cached keys are immutable and bounded to 16.
"""
import ctypes as C
from ctypes.util import find_library
from functools import lru_cache
from pathlib import Path
import os
import shutil
from gmssl import sm2


def _tlv(tag, value):
    size = len(value)
    length = bytes([size]) if size < 128 else bytes([0x80+(size.bit_length()+7)//8])+size.to_bytes((size.bit_length()+7)//8,'big')
    return bytes([tag])+length+value


def _integer(raw):
    raw = raw.lstrip(b'\0') or b'\0'
    if raw[0] & 0x80: raw = b'\0'+raw
    return _tlv(2,raw)


def _cipher_der(raw):
    if len(raw) < 97: raise ValueError('SM2 ciphertext is too short')
    # The application's established wire format is C1(x,y) || C2 || C3.
    return _tlv(0x30,_integer(raw[:32])+_integer(raw[32:64])+_tlv(4,raw[-32:])+_tlv(4,raw[64:-32]))


class _Key:
    def __init__(self, lib, pointer): self.lib,self.pointer = lib,pointer
    def __del__(self):
        if self.pointer: self.lib.EVP_PKEY_free(self.pointer)


class NativeSM2:
    def __init__(self, path):
        self.path = str(path)
        self.lib = C.CDLL(self.path)
        lib = self.lib
        uchar = C.POINTER(C.c_ubyte)
        signatures = {
            'd2i_AutoPrivateKey': (C.c_void_p,[C.c_void_p,C.POINTER(uchar),C.c_long]),
            'EVP_PKEY_free': (None,[C.c_void_p]),
            'EVP_PKEY_CTX_new': (C.c_void_p,[C.c_void_p,C.c_void_p]),
            'EVP_PKEY_CTX_free': (None,[C.c_void_p]),
            'EVP_PKEY_decrypt_init': (C.c_int,[C.c_void_p]),
            'EVP_PKEY_decrypt': (C.c_int,[C.c_void_p,C.c_void_p,C.POINTER(C.c_size_t),C.c_void_p,C.c_size_t]),
            'ERR_clear_error': (None,[]),
        }
        for name,(restype,argtypes) in signatures.items():
            f = getattr(lib,name); f.restype = restype; f.argtypes = argtypes

    @lru_cache(maxsize=16)
    def _key(self, private):
        scalar = int(private,16)
        if len(private)!=64 or not 0 < scalar < int(sm2.default_ecc_table['n'],16):
            raise ValueError('Invalid SM2 private key')
        engine = sm2.CryptSM2(public_key='',private_key=private)
        point = b'\x04'+bytes.fromhex(engine._kg(scalar,sm2.default_ecc_table['g']))
        # RFC 5915 ECPrivateKey, explicit SM2 named-curve OID 1.2.156.10197.1.301.
        der = _tlv(0x30,_integer(b'\x01')+_tlv(4,bytes.fromhex(private))+
                   _tlv(0xa0,bytes.fromhex('06082a811ccf5501822d'))+_tlv(0xa1,_tlv(3,b'\0'+point)))
        buffer = (C.c_ubyte*len(der)).from_buffer_copy(der)
        position = C.cast(buffer,C.POINTER(C.c_ubyte))
        pointer = self.lib.d2i_AutoPrivateKey(None,C.byref(position),len(der))
        if not pointer:
            self.lib.ERR_clear_error()
            raise ValueError('OpenSSL could not import SM2 key')
        return _Key(self.lib,pointer)

    def decrypt(self, private, ciphertext):
        key = self._key(private.zfill(64))
        ctx = self.lib.EVP_PKEY_CTX_new(key.pointer,None)
        if not ctx: raise RuntimeError('Cannot allocate SM2 context')
        try:
            if self.lib.EVP_PKEY_decrypt_init(ctx)!=1: raise RuntimeError('SM2 decryption is unavailable')
            der = _cipher_der(ciphertext)
            source = C.create_string_buffer(der)
            length = C.c_size_t()
            if self.lib.EVP_PKEY_decrypt(ctx,None,C.byref(length),source,len(der))!=1:
                raise ValueError('Invalid SM2 ciphertext')
            output = C.create_string_buffer(length.value)
            if self.lib.EVP_PKEY_decrypt(ctx,output,C.byref(length),source,len(der))!=1:
                raise ValueError('SM2 integrity verification failed')
            return output.raw[:length.value]
        finally:
            self.lib.EVP_PKEY_CTX_free(ctx)
            self.lib.ERR_clear_error()


@lru_cache(maxsize=1)
def native_sm2_backend():
    candidates = []
    if os.name=='nt':
        executable = shutil.which('openssl')
        if executable:
            candidates = [Path(executable).parent/name for name in ['libcrypto-3-x64.dll','libcrypto-3.dll']]
    else:
        library = find_library('crypto')
        if library: candidates = [library]
    for path in candidates:
        try:
            backend = NativeSM2(path)
            # Confirm SM2 support before selecting this optional acceleration.
            private = '0'*63+'1'
            key = backend._key(private)
            ctx = backend.lib.EVP_PKEY_CTX_new(key.pointer,None)
            if not ctx: continue
            try:
                if backend.lib.EVP_PKEY_decrypt_init(ctx)==1: return backend
            finally: backend.lib.EVP_PKEY_CTX_free(ctx)
        except (OSError,AttributeError,ValueError,RuntimeError):
            continue
    return None
