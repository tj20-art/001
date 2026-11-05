"""Verify the published optimization proof against raw results and live files."""
import csv
import json
import socket
from pathlib import Path
from performance.run_optimization_comparison import fingerprint
from performance.run_week89_existing import ROOT,SOURCE,sha,connect,code_manifest,write_json

def main():
    folder=SOURCE/'完整测试结果-20261105-013809'
    state=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    assert state['status']=='complete' and state['all_targets_met'] and len(state['runs'])==6
    manifest=json.loads((folder/'sha256-manifest.json').read_text(encoding='utf-8'))
    assert all((folder/name).is_file() and sha(folder/name)==value for name,value in manifest.items())
    assert json.loads((folder/'optimized-source-manifest.json').read_text(encoding='utf-8'))==code_manifest()
    assert sha(ROOT/'requirements.txt')==state['environment']['requirements_sha256']
    for run in state['runs']:
        assert run['valid_fixed_load'] and run['all_failures']==0
        assert run['initial_data_sha256']==state['seed_sha256']
        assert sha(Path(run['settings']['source']))==run['settings']['source_sha256']
        directory=folder/run['version']/run['scenario']
        rows=list(csv.DictReader((directory/'measurement.jtl').open(encoding='utf-8-sig',newline='')))
        assert len(rows)==run['measurement']['samples']
        assert all(r['success']=='true' for r in rows)
        assert (directory/'measurement-html/index.html').is_file()
        if run['scenario']=='order': assert run['order_accounting_matches']
    assert all(r['满足20%改善及错误率要求'] for r in state['comparison'])
    assert state['optimized_source_frozen'] and state['original_database_unchanged']
    with connect() as c:
        with c.cursor() as s:
            s.execute('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN (%s,%s)',state['owned_test_databases'])
            assert not s.fetchall()
    with socket.socket() as s:
        s.settimeout(1)
        assert s.connect_ex(('127.0.0.1',24433))!=0
    with (ROOT/'performance/data/users-local.csv').open(encoding='utf-8-sig',newline='') as f:
        password=next(csv.reader(f))[1].encode('utf-8')
    assert all(password not in p.read_bytes() for p in folder.rglob('*') if p.is_file())
    result={'published_directory':str(folder),'checked_files':len(manifest),'all_targets_met':True,
            'formal_samples':sum(r['measurement']['samples'] for r in state['runs']),
            'original_database_unchanged':True,'temporary_database_removed':True,
            'test_server_stopped':True,'original_jmx_unchanged':True,'password_in_results':False,
            'comparison':state['comparison'],'changed_files':state['changed_files']}
    write_json(ROOT/'performance/optimization-20261105/delivery-verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
