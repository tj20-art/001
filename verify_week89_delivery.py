"""Verify the delivered evidence without modifying the tested system."""
import csv
import json
import socket
from pathlib import Path
from performance.run_week89_existing import ROOT, SOURCE, connect, code_manifest, sha, write_json

def main():
    target=SOURCE/'完整测试结果-20261105-013809'
    state=json.loads((target/'summary.json').read_text(encoding='utf-8'))
    manifest=json.loads((target/'sha256-manifest.json').read_text(encoding='utf-8'))
    mismatches=[name for name,value in manifest.items() if not (target/name).is_file() or sha(target/name)!=value]
    assert not mismatches, mismatches
    before=json.loads((target/'business-source-before.json').read_text(encoding='utf-8'))
    assert before==code_manifest()
    assert state['status']=='complete' and len(state['runs'])==6
    assert state['original_database_unchanged'] and not state.get('cleanup_errors')
    assert all(r['valid_fixed_load'] and r['all_failures']==0 for r in state['runs'])
    assert all(sha(Path(r['settings']['source']))==r['settings']['source_sha256'] for r in state['runs'])
    with connect() as c:
        with c.cursor() as s:
            names=state['owned_test_databases']
            s.execute('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN (%s,%s)',names)
            remaining=s.fetchall()
    assert not remaining, 'Owned test databases remain'
    with socket.socket() as s:
        s.settimeout(1)
        assert s.connect_ex(('127.0.0.1',24433))!=0, 'Test server remains active'
    with (ROOT/'performance/data/users-local.csv').open(encoding='utf-8-sig',newline='') as f:
        password=next(csv.reader(f))[1].encode('utf-8')
    secret_files=[str(p.relative_to(target)) for p in target.rglob('*') if p.is_file() and password in p.read_bytes()]
    assert not secret_files, 'A test password was found in delivered files'
    result={'delivered_to':str(target),'checked_files':len(manifest),'checksum_mismatches':0,'formal_runs':6,
            'formal_business_samples':sum(r['measurement']['samples'] for r in state['runs']),
            'all_http_samples':sum(r['raw_http_samples'] for r in state['runs']),
            'business_source_unchanged':True,'original_database_unchanged':True,'original_jmx_unchanged':True,
            'owned_test_databases_removed':True,'test_server_stopped':True,'password_in_report':False,
            'metrics':[{'round':r['round'],'scenario':r['scenario'],'samples':r['measurement']['samples'],
                        'p95_ms':r['measurement']['p95_ms'],'error_percent':r['measurement']['error_percent'],
                        'rps':r['measurement']['throughput_rps_fixed_window']} for r in state['runs']]}
    write_json(ROOT/'performance/results/delivery-verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
