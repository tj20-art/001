"""Short realistic probes before committing to the unchanged formal load."""
from pathlib import Path
import json
import ssl
import urllib.request
import urllib.error
import csv
from performance import run_week89_existing as base

def auth_regression(db,folder):
    folder.mkdir()
    proc,log,ready=base.start_server(db,folder)
    try:
        with (base.ROOT/'performance/data/users-local.csv').open(encoding='utf-8-sig',newline='') as f:
            cert,password,_=next(csv.reader(f))
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session=requests.Session()
        with open(cert,'rb') as file:
            response=session.post(f'https://127.0.0.1:{base.PORT}/api/v1/auth/login',files={'certificate':file},data={'password':password},verify=False,timeout=15)
        assert response.status_code==200
        assert response.raw.version==11
        assert response.headers.get('Strict-Transport-Security')
        payload=response.json()['data']
        user=payload['user_info']['user_id']
        headers={'Authorization':'Bearer '+payload['access_token']}
        def status():
            return session.get(f'https://127.0.0.1:{base.PORT}/api/v1/cart/items',headers=headers,verify=False,timeout=10).status_code
        assert status()==200
        with base.connect(db) as c:
            with c.cursor() as s:
                s.execute('UPDATE users SET auth_version=auth_version+1 WHERE id=%s',(user,))
        assert status()==401, 'Old token must be invalidated immediately after reset'
        with base.connect(db) as c:
            with c.cursor() as s:
                s.execute('UPDATE users SET auth_version=auth_version-1,is_active=0 WHERE id=%s',(user,))
        assert status()==401, 'Disabled account must be rejected without stale cache'
        session.close()
        base.write_json(folder/'checks.json',{'valid_token':200,'after_security_reset':401,'after_disable':401,'http11':True,'https_hsts':True})
    finally: base.stop_server(proc,log,ready['pid'])

def main():
    folder=base.ROOT/'performance/optimization-20261105'/('probe-'+base.STAMP)
    folder.mkdir()
    seed='adb_perf_seed_'+base.STAMP; work='adb_perf_run_'+base.STAMP
    base.OWNED.update([seed,work])
    _,definitions,data,_=base.source_capture()
    base.create_database(seed,definitions,data)
    with base.connect(seed) as c:
        with c.cursor() as s:
            s.execute('DELETE FROM cart_items WHERE user_id IN (SELECT id FROM users WHERE username IN ('+','.join(['%s']*9)+'))',base.USERS)
    results=[]
    try:
        base.clone_seed(seed,work,definitions)
        auth_regression(work,folder/'auth-regression')
        print('Immediate token invalidation and disabled-account checks passed',flush=True)
        for key in ['query','order','login']:
            base.clone_seed(seed,work,definitions)
            print('START '+key,flush=True)
            result=base.run_one(key,folder/key,work,45,9,True)
            results.append(result)
            assert result['all_failures']==0
            if key=='order': assert result['order_accounting_matches']
            print(key,json.dumps(result['measurement'],ensure_ascii=False),flush=True)
        base.write_json(folder/'summary.json',results)
    finally:
        base.drop_owned(work);base.drop_owned(seed)

if __name__=='__main__':main()
