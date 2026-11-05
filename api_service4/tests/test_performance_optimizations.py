from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from api_service4.app.services import gm_crypto as gm
from api_service4.app.services.native_sm2 import native_sm2_backend
from api_service4.app.services.payment_crypto import generate_sm2_keypair, sm2_encrypt, sm2_decrypt
from api_service4.app.services.read_pool import ReadConnectionPool


@pytest.fixture
def certificates():
    now = datetime.now(timezone.utc)
    root_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Optimization test CA')])
    root = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(root_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
        .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
        .sign(root_key,hashes.SHA256()))
    user_key = ec.generate_private_key(ec.SECP256R1())
    def leaf(before,after):
        return (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'test-user')]))
            .issuer_name(name).public_key(user_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(before).not_valid_after(after).sign(root_key,hashes.SHA256()))
    public=user_key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return root,leaf(now-timedelta(minutes=1),now+timedelta(hours=1)),leaf(now-timedelta(days=2),now-timedelta(days=1)),public


def test_certificate_verification_runs_each_login_and_uses_two_processes(certificates,monkeypatch):
    root,cert,_,public=certificates
    original=gm._run_openssl
    calls=[]
    def counted(*args,**kwargs):
        calls.append(args[0][0]);return original(*args,**kwargs)
    monkeypatch.setattr(gm,'_run_openssl',counted)
    for _ in range(2):
        gm._verify_certificate_with_openssl(cert.public_bytes(serialization.Encoding.PEM),root.public_bytes(serialization.Encoding.PEM),public,'test-user')
    assert calls==['verify','x509','verify','x509']


def test_certificate_expiry_binding_and_signature_still_rejected(certificates):
    root,cert,expired,public=certificates
    root_pem=root.public_bytes(serialization.Encoding.PEM)
    cert_pem=cert.public_bytes(serialization.Encoding.PEM)
    with pytest.raises(gm.CertificateExpiredError):
        gm._verify_certificate_with_openssl(expired.public_bytes(serialization.Encoding.PEM),root_pem,public,'test-user')
    with pytest.raises(gm.CertificateUsernameMismatchError):
        gm._verify_certificate_with_openssl(cert_pem,root_pem,public,'other-user')
    other=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    with pytest.raises(gm.CertificatePublicKeyMismatchError):
        gm._verify_certificate_with_openssl(cert_pem,root_pem,other,'test-user')
    with pytest.raises(gm.CertificateAlgorithmMismatchError):
        gm._verify_certificate_with_openssl(cert_pem,root_pem,public,'test-user',enforce_gm=True)
    der=cert.public_bytes(serialization.Encoding.DER)
    with pytest.raises(gm.CertificateVerificationError):
        gm._verify_certificate_with_openssl(der[:-1]+bytes([der[-1]^1]),root_pem,public,'test-user')


def test_native_sm2_compatibility_concurrency_and_integrity():
    native=native_sm2_backend()
    if native is None: pytest.skip('Compatible OpenSSL libcrypto not installed')
    pairs=[generate_sm2_keypair() for _ in range(3)]
    messages=[b'x',bytes(range(32)),b'00112233445566778899aabbccddeeff']
    packets=[(p,m,bytes.fromhex(sm2_encrypt(p['public_key'],m))) for p,m in zip(pairs,messages)]
    with ThreadPoolExecutor(max_workers=9) as pool:
        assert all(pool.map(lambda i:sm2_decrypt(packets[i%3][0]['private_key'],packets[i%3][2].hex())==packets[i%3][1],range(90)))
    p,_,cipher=packets[0]
    for index in [0,64,len(cipher)-1]:
        bad=cipher[:index]+bytes([cipher[index]^1])+cipher[index+1:]
        with pytest.raises(ValueError): sm2_decrypt(p['private_key'],bad.hex())
    with pytest.raises(ValueError): sm2_decrypt(pairs[1]['private_key'],cipher.hex())


def test_read_pool_reuses_connections_and_discards_failed_connection(monkeypatch):
    import api_service4.app.services.read_pool as module
    factory=MagicMock()
    connection=MagicMock()
    factory.return_value=connection
    monkeypatch.setattr(module.pymysql,'connect',factory)
    cfg=dict(host='localhost',port=3306,user='test',password='unused',db='test',charset='utf8mb4')
    pool=ReadConnectionPool(cfg,size=1)
    with pool.cursor(): pass
    with pool.cursor(): pass
    assert factory.call_count==1
    assert factory.call_args.kwargs['autocommit'] is True
    assert factory.call_args.kwargs['init_command']=='SET SESSION TRANSACTION READ ONLY'
    connection.commit.assert_not_called()
    with pool.cursor(consistent=True): pass
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()
    with pytest.raises(ValueError):
        with pool.cursor(): raise ValueError('query failure')
    connection.close.assert_called_once()
    with pool.cursor(): pass
    assert factory.call_count==2
    pool.close()
    with pytest.raises(RuntimeError):
        with pool.cursor(): pass
