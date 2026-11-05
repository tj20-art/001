"""Finish validation/publication even if the interactive chat is interrupted."""
import json
from pathlib import Path
import subprocess
import sys
import time
from performance.run_supplied_plans import ROOT

def main():
    folder=ROOT/'performance/results/现有系统持续测试-20261105021111'
    console=ROOT/'performance/results/formal-run-console.txt'
    status=ROOT/'performance/results/formal-finalization-status.json'
    deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        progress=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
        if progress['status']=='failed': raise RuntimeError(progress.get('error','formal test failed'))
        if 'PUBLISHED ' in console.read_text(encoding='utf-8',errors='replace'):
            result=subprocess.run([sys.executable,'-X','utf8','-m','performance.finalize_week89_report',str(folder),'--publish'],cwd=ROOT)
            status.write_text(json.dumps({'exit_code':result.returncode,'source':str(folder),'completed_epoch':time.time()},ensure_ascii=False,indent=2),encoding='utf-8')
            if result.returncode: raise RuntimeError('Final package verification failed')
            return
        time.sleep(5)
    raise TimeoutError('Bounded finalization wait exceeded one hour')

if __name__=='__main__':main()
