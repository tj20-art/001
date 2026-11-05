"""Add diagnosis/provenance, then independently verify the final delivery."""
import argparse
import csv
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from performance import run_week89_existing as base

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wait',action='store_true')
    a=parser.parse_args()
    root=base.ROOT/'performance/optimization-20261105'
    folder=root/'comparison-20261105094026'
    if a.wait:
        deadline=time.monotonic()+3600
        while time.monotonic()<deadline:
            state=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
            if state['status']=='failed': raise RuntimeError(state.get('error'))
            if 'PUBLISHED ' in (root/'formal-v2-console.txt').read_text(encoding='utf-8',errors='replace'): break
            time.sleep(5)
        else: raise TimeoutError('Report publication timeout')
    state=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    assert state['all_targets_met'] and len(state['runs'])==6
    historical=base.ROOT/'performance/results/现有系统持续测试-20261105021111'
    (folder/'历史基线').mkdir(exist_ok=True)
    for name in ['summary.json','完整测试报告.md','核心指标汇总.csv']:
        shutil.copyfile(historical/name,folder/'历史基线'/name)
    lines=['','## 建连与SQL开销核对','','下表的连接P95来自正式300秒窗口。COMMIT次数及SQL耗时为完整运行的摘要增量，含初始化，不等于单次HTTP耗时，不能直接相减归因。',
        '','| 版本/场景 | HTTP P95 ms | Connect P95 ms | 全程COMMIT次数 | 全程COMMIT累计ms |','|---|---:|---:|---:|---:|']
    for run in state['runs']:
        d=folder/run['version']/run['scenario']
        rows=list(csv.DictReader((d/'measurement.jtl').open(encoding='utf-8-sig',newline='')))
        connect=sorted(int(r.get('Connect') or 0) for r in rows)
        p95=connect[math.ceil(len(connect)*.95)-1]
        digest=json.loads((d/'sql-digest.json').read_text(encoding='utf-8'))
        commit=next((r for r in digest if r['sql_normalized']=='COMMIT'),{'COUNT_STAR':0,'total_ms':0})
        lines.append(f"| {run['version']}/{run['scenario']} | {run['measurement']['p95_ms']} | {p95} | {commit['COUNT_STAR']} | {commit['total_ms']:.2f} |")
    lines += ['','版本与比较口径：',
        '','- 基线业务源码逐文件与此前测量版本的SHA256一致；优化版源文件在本轮期间保持不变。旧版解密函数仍为gmssl实现。早期server-ready.json里的sm2探测记录表示库可用性，未替换旧版payment_crypto.sm2_decrypt函数；后续记录增加了实际函数源路径与SHA256。源码与变更补丁可独立核对。',
        '- 凌晨原有两轮数据保留在“历史基线”目录供参考。课程达标计算使用本次预先固定的同快照基线，不能把凌晨结果和新结果随意混合挑选。尤其历史查询P95为8ms，新查询P95应同时对照历史值和本次配对基线理解。',
        '- 首轮仅业务代码优化的查询改善未达到20%，过程原始数据未删除。最终结果包含HTTP服务器/连接复用配置优化，因此降低比例代表整组优化的端到端效果，不单独归因于某一个算法或SQL。',
        '- 当前2333端口若仍运行原来的进程，需要在PyCharm停止并重新运行api_service4/run.py才能加载新代码和Cheroot。默认非调试运行启用新服务器；FLASK_DEBUG=true仍使用原调试服务器。',
        '','交付核验：所有正式窗口9线程持续参与、HTTP与业务断言无错误；订单数/库存扣减一致；原JMX未改；临时测试库与测试进程已清理；报告不包含CSV密码。']
    report=folder/'完整测试报告.md'
    text=report.read_text(encoding='utf-8').replace('本轮实际实现及DLL校验值见settings.json的server.sm2','优化版实现及DLL校验值见settings.json的server.sm2')
    text=text.split('\n## 建连与SQL开销核对')[0]
    start=text.index('| 版本/场景 | 正式样本')
    end=text.index('\n原库关键数据未改动',start)
    resources=['| 版本/场景 | 正式样本 | 失败数 | 后端单核CPU均值/峰值 | 私有内存峰值MB | SQL锁等待采样峰值 |','|---|---:|---:|---:|---:|---:|']
    accounting=[]
    for run in state['runs']:
        m=run['measurement'];r=run['resources'];cpu=r.get('backend_cpu_percent_one_core',{})
        resources.append(f"| {run['version']}/{run['scenario']} | {m['samples']} | {m['failures']} | {cpu.get('mean',0):.1f}% / {cpu.get('max',0):.1f}% | {r.get('backend_private_mb',{}).get('max',0):.1f} | {r.get('db_lock_waits',{}).get('max',0):.0f} |")
        if run['scenario']=='order':
            accounting.append(f"- {run['version']}：新增订单{run['db_orders_created']}笔，成功订单数/新增订单数/库存扣减一致：{run['order_accounting_matches']}。")
    text=text[:start]+'\n'.join(resources)+'\n\n'+'\n'.join(accounting)+'\n'+text[end:]
    text+='\n'.join(lines)+'\n'
    report.write_text(text,encoding='utf-8')
    index=folder/'index.html'
    page=index.read_text(encoding='utf-8')
    page=page[:page.index('<pre>')]+'<pre>'+html.escape(text)+'</pre></details>'
    index.write_text(page,encoding='utf-8')
    base.write_json(folder/'sha256-manifest.json',{p.relative_to(folder).as_posix():base.sha(p) for p in folder.rglob('*') if p.is_file() and p.name!='sha256-manifest.json'})
    print('FINAL PUBLISHED '+base.publish(folder),flush=True)
    result=subprocess.run([sys.executable,'-X','utf8','-m','performance.verify_optimization_results'],cwd=base.ROOT)
    if result.returncode: raise RuntimeError('Independent final verification failed')
    (root/'finalization-complete.json').write_text(json.dumps({'verified':True,'directory':str(folder)},ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':main()
