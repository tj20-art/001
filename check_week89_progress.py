"""Read the durable progress of the independent test runner without changing it."""
import csv
import json
from pathlib import Path
from performance.run_supplied_plans import ROOT

def main():
    folder=max((ROOT/'performance/results').glob('现有系统持续测试-*'),key=lambda p:p.name)
    state=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
    result={'directory':str(folder),'status':state['status'],'progress':state['progress'],'completed_formal_runs':len(state['runs'])}
    checkpoints=list(folder.rglob('monitor-checkpoint.json'))
    if checkpoints:
        latest=max(checkpoints,key=lambda p:p.stat().st_mtime)
        monitor=json.loads(latest.read_text(encoding='utf-8'))
        result['active_folder']=str(latest.parent.relative_to(folder))
        result['active_elapsed_seconds']=round(monitor[-1]['elapsed_seconds'])
        raw=latest.parent/'raw.jtl'
        if raw.exists():
            with raw.open(encoding='utf-8-sig',newline='') as f:
                rows=[r for r in csv.DictReader(f) if r.get('success') in ['true','false']]
            result['current_samples']=len(rows)
            result['current_failures']=sum(r['success']=='false' for r in rows)
            result['current_threads']=len({r['threadName'] for r in rows})
        result['last_resource_sample']={k:v for k,v in monitor[-1].items() if k in ['backend_cpu_percent_one_core','backend_private_mb','system_cpu_percent','system_memory_percent','db_lock_waits']}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
