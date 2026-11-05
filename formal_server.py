"""Run the existing app against an explicitly named isolated test database."""
import argparse
import json
import os
from pathlib import Path
import re

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--database', required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--ready', type=Path, required=True)
    a = p.parse_args()
    if not re.fullmatch(r'adb_perf_run_\d{14}', a.database):
        raise ValueError('Only a dedicated performance database is accepted')
    os.environ['PERF_TEST_MODE'] = '1'
    from api_service4.config.dev_config import DevConfig
    cfg = dict(DevConfig.MYSQL_CONFIG)
    cfg['db'] = a.database
    cfg.pop('database', None)
    DevConfig.MYSQL_CONFIG = cfg
    # Override configuration in this child only, before importing service singletons.
    from api_service4.run import app
    from api_service4.app.middleware.rate_limit import get_rate_limit_settings
    a.ready.write_text(json.dumps({'pid': os.getpid(), 'database': a.database,
                                  'port': a.port, 'limits': get_rate_limit_settings()}), encoding='utf-8')
    app.run(host='127.0.0.1', port=a.port, ssl_context='adhoc',
            debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__': main()
