"""Run the existing app against an explicitly named isolated test database."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import hashlib
import inspect

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--database', required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--ready', type=Path, required=True)
    p.add_argument('--source-root', type=Path)
    a = p.parse_args()
    if not re.fullmatch(r'adb_perf_run_\d{14}', a.database):
        raise ValueError('Only a dedicated performance database is accepted')
    os.environ['PERF_TEST_MODE'] = '1'
    if a.source_root:
        project = Path(__file__).resolve().parent.parent
        sys.path.insert(0,str(a.source_root.resolve()))
        os.environ['CERTIFICATES_DIR'] = str(project/'api_service4/certificates')
        os.environ['ROOT_CERT_PATH'] = str(project/'api_service4/certificates/root_certificate.pem')
        os.environ['ROOT_PRIVATE_KEY_PATH'] = str(project/'api_service4/certificates/root_private_key.pem')
        os.environ['TUNNEL_KEYS_DIR'] = str(project/'api_service4/security_keys')
    from api_service4.config.dev_config import DevConfig
    cfg = dict(DevConfig.MYSQL_CONFIG)
    cfg['db'] = a.database
    cfg.pop('database', None)
    DevConfig.MYSQL_CONFIG = cfg
    # Override configuration in this child only, before importing service singletons.
    from api_service4.run import app
    import api_service4.run as application_module
    from api_service4.app.middleware.rate_limit import get_rate_limit_settings
    from api_service4.app.services import payment_crypto
    crypto = {'implementation':'gmssl'}
    try:
        if 'native_sm2_backend' not in payment_crypto.sm2_decrypt.__globals__:
            raise ImportError('Measured baseline uses its original gmssl decrypt function')
        from api_service4.app.services.native_sm2 import native_sm2_backend
        native = native_sm2_backend()
        if native is not None:
            crypto = {'implementation':'OpenSSL EVP','library':native.path,
                      'library_sha256':hashlib.sha256(Path(native.path).read_bytes()).hexdigest()}
    except ImportError:
        pass
    a.ready.write_text(json.dumps({'pid': os.getpid(), 'database': a.database,
                                  'sm2':crypto,
                                  'sm2_decrypt_source':inspect.getsourcefile(payment_crypto.sm2_decrypt),
                                  'sm2_decrypt_function_sha256':hashlib.sha256(inspect.getsource(payment_crypto.sm2_decrypt).encode()).hexdigest(),
                                  'source_root':str(a.source_root) if a.source_root else str(Path(__file__).resolve().parent.parent),
                                  'transport':'Cheroot 11.1.2 HTTP/1.1, 16 workers, keep-alive' if hasattr(application_module,'serve_application') else 'Werkzeug 1.0.1 development server HTTP/1.0',
                                  'port': a.port, 'limits': get_rate_limit_settings()}), encoding='utf-8')
    if hasattr(application_module,'serve_application'):
        application_module.serve_application(host='127.0.0.1',port=a.port,ssl_context='adhoc')
    else:
        app.run(host='127.0.0.1', port=a.port, ssl_context='adhoc',
                debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__': main()
