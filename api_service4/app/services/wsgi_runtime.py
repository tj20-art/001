"""Bounded HTTP/1.1 WSGI runtime with the existing TLS configuration."""
from contextlib import contextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from cheroot import wsgi
from cheroot.ssl.builtin import BuiltinSSLAdapter
from cryptography.hazmat.primitives import serialization
from werkzeug.serving import generate_adhoc_ssl_pair


@contextmanager
def configured_server(application, *, host, port, ssl_context=None, threads=16):
    if not 1 <= threads <= 128:
        raise ValueError('WSGI_THREADS must be between 1 and 128')
    server = wsgi.Server((host,port),application,numthreads=threads,max=threads,
                         request_queue_size=128,accepted_queue_size=128,timeout=10)
    server.keep_alive_conn_limit = 64
    with TemporaryDirectory(prefix='mall-https-') as temporary:
        if ssl_context == 'adhoc':
            cert,key = generate_adhoc_ssl_pair()
            cert_path,key_path = Path(temporary)/'server.crt',Path(temporary)/'server.key'
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()))
            ssl_context = str(cert_path),str(key_path)
        if ssl_context is not None:
            cert_path,key_path = ssl_context
            server.ssl_adapter = BuiltinSSLAdapter(cert_path,key_path)
        try:
            yield server
        finally:
            server.stop()


def serve(application, *, host, port, ssl_context=None):
    threads = int(os.getenv('WSGI_THREADS','16'))
    with configured_server(application,host=host,port=port,ssl_context=ssl_context,threads=threads) as server:
        print(f"Running Cheroot HTTP/1.1 on {'https' if ssl_context else 'http'}://{host}:{port}/; workers={threads}",flush=True)
        try:
            server.start()
        except KeyboardInterrupt:
            pass
