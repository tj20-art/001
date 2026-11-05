import csv
import json
import math
from performance.run_week89_existing import ROOT

def main():
    folder=max((ROOT/'performance/optimization-20261105').glob('comparison-*'),key=lambda p:p.name)
    state=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
    out={k:state.get(k) for k in ['status','progress','error']}
    out['folder']=str(folder)
    out['completed_runs']=len(state['runs'])
    for p in sorted(folder.rglob('monitor-checkpoint.json'),key=lambda p:p.stat().st_mtime)[-1:]:
        data=json.loads(p.read_text(encoding='utf-8'))
        out['active']=str(p.parent.relative_to(folder));out['elapsed_seconds']=round(data[-1]['elapsed_seconds'])
        rows=list(csv.DictReader((p.parent/'raw.jtl').open(encoding='utf-8-sig',newline='')))
        rows=[r for r in rows if r.get('success') in ['true','false']]
        out['http_samples']=len(rows);out['failures']=sum(r['success']=='false' for r in rows)
        out['threads_seen']=len({r['threadName'] for r in rows})
        if rows:
            key=p.parent.name
            label={'query':'02_商品查询','order':'03_创建订单','login':'01_普通用户登录'}[key]
            begin=min(int(r['timeStamp']) for r in rows)+70000
            values=sorted(int(r['elapsed']) for r in rows if r['label']==label and begin<=int(r['timeStamp'])<begin+300000)
            if values: out['partial_formal_p95_ms']=values[math.ceil(len(values)*.95)-1]
        out['last_resources']={k:data[-1][k] for k in ['backend_private_mb','system_cpu_percent','db_lock_waits'] if k in data[-1]}
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
