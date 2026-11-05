import csv
import json
import math
from performance.run_week89_existing import ROOT,LABELS

def main():
    folder=max((ROOT/'performance/results').glob('优化后复测结果-*'),key=lambda p:p.name)
    state=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
    result={'folder':str(folder),'status':state['status'],'progress':state['progress'],'completed_runs':len(state['runs'])}
    checkpoints=list(folder.rglob('monitor-checkpoint.json'))
    if checkpoints:
        p=max(checkpoints,key=lambda p:p.stat().st_mtime)
        monitoring=json.loads(p.read_text(encoding='utf-8'))
        result['active']=p.parent.name
        result['elapsed_seconds']=round(monitoring[-1]['elapsed_seconds'])
        rows=[r for r in csv.DictReader((p.parent/'raw.jtl').open(encoding='utf-8-sig',newline='')) if r.get('success') in ['true','false']]
        result['http_samples']=len(rows)
        result['failures']=sum(r['success']=='false' for r in rows)
        result['threads_seen']=len({r['threadName'] for r in rows})
        if rows:
            begin=min(int(r['timeStamp']) for r in rows)+70000
            values=sorted(int(r['elapsed']) for r in rows if r['label']==LABELS[p.parent.name] and begin<=int(r['timeStamp'])<begin+300000)
            if values: result['partial_formal_p95_ms']=values[math.ceil(len(values)*.95)-1]
        result['last_resources']={k:monitoring[-1][k] for k in ['backend_private_mb','system_cpu_percent','db_lock_waits'] if k in monitoring[-1]}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
