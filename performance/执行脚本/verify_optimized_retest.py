import csv
import json
import socket
from pathlib import Path
from performance import run_week89_existing as base
from performance.run_optimization_comparison import fingerprint

def main():
    latest=json.loads((base.ROOT/'performance/results/latest-optimized-retest.json').read_text(encoding='utf-8'))
    target=Path(latest['destination'])
    assert target.parent.resolve()==base.SOURCE.resolve()
    state=json.loads((target/'summary.json').read_text(encoding='utf-8'))
    manifest=json.loads((target/'sha256-manifest.json').read_text(encoding='utf-8'))
    assert all((target/name).is_file() and base.sha(target/name)==value for name,value in manifest.items())
    assert state['status']=='complete' and len(state['runs'])==3
    assert state['source_frozen'] and state['original_database_unchanged']
    assert state['temporary_databases_removed'] and state['test_port_released']
    assert json.loads((target/'source-manifest.json').read_text(encoding='utf-8'))==base.code_manifest()
    for run in state['runs']:
        d=target/run['scenario']
        rows=list(csv.DictReader((d/'measurement.jtl').open(encoding='utf-8-sig',newline='')))
        calculated=base.stats(rows)
        assert len(rows)==run['measurement']['samples']
        assert calculated['p95_ms']==run['measurement']['p95_ms']
        assert all(r['label']==base.LABELS[run['scenario']] and run['window_start_ms']<=int(r['timeStamp'])<run['window_end_ms'] for r in rows)
        assert run['valid_fixed_load']
        assert (d/'measurement-html/index.html').is_file()
        assert base.sha(Path(run['settings']['source']))==run['settings']['source_sha256']
        if run['scenario']=='order': assert run['order_accounting_matches']
    with base.connect() as c:
        original=c.db.decode() if isinstance(c.db,bytes) else c.db
        with c.cursor() as cursor:
            cursor.execute('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN (%s,%s)',state['owned_test_databases'])
            assert not cursor.fetchall()
    assert fingerprint(original)==state['original_data_sha256_before']
    with socket.socket() as sock:
        sock.settimeout(1);assert sock.connect_ex(('127.0.0.1',state['test_port']))!=0
    with (base.ROOT/'performance/data/users-local.csv').open(encoding='utf-8-sig',newline='') as f:
        password=next(csv.reader(f))[1].encode('utf-8')
    assert all(password not in p.read_bytes() for p in target.rglob('*') if p.is_file())
    output={'directory':str(target),'verified_files':len(manifest),'formal_business_samples':sum(r['measurement']['samples'] for r in state['runs']),
            'all_requests_successful':state['all_requests_successful'],'source_unchanged':True,'original_database_unchanged':True,
            'temporary_databases_removed':True,'test_server_stopped':True,'password_in_results':False,'metrics':state['metrics']}
    base.write_json(base.ROOT/'performance/results/optimized-retest-verification.json',output)
    print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
