"""Add evidence-based findings and verify the complete report package."""
import argparse
import csv
from pathlib import Path
import hashlib
import html
import json
import importlib.metadata
import math
import shutil
from performance.run_week89_existing import ROOT, report, publish, write_json, sha

def percentile(values,p=.95):
    a=sorted(values)
    return a[math.ceil(len(a)*p)-1] if a else 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    folder=args.folder.resolve()
    if folder.parent != (ROOT/'performance/results').resolve(): raise ValueError('Unexpected report root')
    state=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    if state['status']!='complete' or len(state['runs'])!=6: raise ValueError('All six formal runs must finish first')
    state['environment']['python_dependencies']={name:importlib.metadata.version(name) for name in ['Flask','Werkzeug','cryptography','gmssl','PyMySQL']}
    state['environment']['bouncycastle_jar_sha256']=sha(Path('D:/Downloads/JMeter/apache-jmeter-5.6.3/lib/bcprov-jdk18on-1.86.jar'))
    rows=[]
    appendix=['','## 实测诊断与验收核对','','下表仅统计正式300秒窗口；连接P95用于区分HTTP耗时和建连耗时。SQL为本轮执行的累计摘要，包含初始化以及监控之外的数据库核验，不等同于逐请求链路追踪。',
        '','| 轮次/场景 | HTTP P95 ms | Connect P95 ms | 后端私有内存末段-首段MB | SQL累计耗时最高项 | SQL均值ms |',
        '|---|---:|---:|---:|---|---:|']
    for run in state['runs']:
        directory=folder/f'round{run["round"]}'/run['scenario']
        data=list(csv.DictReader((directory/'measurement.jtl').open(encoding='utf-8-sig',newline='')))
        assert len(data)==run['measurement']['samples']
        assert sum(r['success']!='true' for r in data)==run['measurement']['failures']
        assert run['valid_fixed_load'] and run['all_failures']==0
        if run['scenario']=='order': assert run['order_accounting_matches']
        monitor=list(csv.DictReader((directory/'monitor.csv').open(encoding='utf-8-sig',newline='')))
        begin,end=run['window_start_ms'],run['window_end_ms']
        first=[float(r['backend_private_mb']) for r in monitor if begin<=int(r['epoch_ms'])<begin+30000 and r.get('backend_private_mb')]
        last=[float(r['backend_private_mb']) for r in monitor if end-30000<=int(r['epoch_ms'])<end and r.get('backend_private_mb')]
        growth=sum(last)/len(last)-sum(first)/len(first)
        digest=json.loads((directory/'sql-digest.json').read_text(encoding='utf-8'))
        top=digest[0] if digest else {'sql_normalized':'无摘要','mean_ms':0}
        connect95=percentile([int(r.get('Connect') or 0) for r in data])
        sql=top['sql_normalized'].replace('|','/').replace('`','')[:140]
        appendix.append(f"| {run['round']}/{run['scenario']} | {run['measurement']['p95_ms']} | {connect95} | {growth:+.2f} | {sql} | {top['mean_ms']:.3f} |")
        rows.append({'轮次':run['round'],'场景':run['title'],'虚拟用户':9,'采样秒数':300,
                     '样本数':len(data),'平均毫秒':run['measurement']['average_ms'],
                     'P95毫秒':run['measurement']['p95_ms'],'P99毫秒':run['measurement']['p99_ms'],
                     '错误率百分比':run['measurement']['error_percent'],'每秒业务请求':len(data)/300,
                     '连接P95毫秒':connect95,'后端私有内存变化MB':growth})
        assert (directory/'measurement-html/index.html').is_file()
        # Log-level errors are retained even when HTTP assertions pass.
        log=(directory/'jmeter.log').read_text(encoding='utf-8',errors='replace')
        if ' ERROR ' in log:
            raise ValueError('Inspect JMeter ERROR log before publishing: '+str(directory))
    assert state['business_source_unchanged']
    assert state['original_database_unchanged']
    appendix += ['','结论与边界：',
        '','- 六个正式窗口的错误率均为0%，低于课件1%上限；每个30秒段均有9个线程采样且grpThreads保持9，数据可作为本负载下的现有系统基线与重复性证据。',
        '- 登录包含证书链/有效期/账号绑定校验、密码校验和令牌签发。代码路径使用OpenSSL子进程验证证书（gm_crypto.py的verify_certificate_with_root及_verify_certificate_with_openssl）。若登录HTTP耗时明显高于连接耗时和单条SQL耗时，可将证书校验/子进程开销列为后续分析候选；本次未做函数级剖析，不宣称已定量确认该热点。后端CPU采样只覆盖Python进程，不包含短命OpenSSL子进程；整机CPU覆盖所有进程。',
        '- 商品查询是当前少量商品数据上的列表查询；数据库只有现有规模的数据。低P95和未采到锁等待支持当前负载运行平稳，不能证明大数据量、高并发或生产部署下仍有相同表现。',
        '- 下单涉及购物车与订单事务、库存扣减、审计和国密隧道。成功订单数、库存扣减与数据库新增订单数一致，响应中的商品、数量和金额通过断言；未测支付。按时长停止可能在末尾留下已加购但未下单的测试购物车数据，这些位于一次性副本中，下一轮会恢复快照。',
        '- MySQL的SQL摘要没有提供Python应用锁等待时间，也没有逐函数CPU占比；不能仅凭SQL时间推断应用层锁没有竞争。本次没有测到容量上限，也没有修改索引、连接池、缓存或国密实现。',
        '- 两轮均为同一业务代码；P95变化按自然波动记录，不能填写成“优化改善比例”。没有事先认可的绝对P95/吞吐目标，因此本报告不能单独证明“已达标保持”；需要教师认可目标，或另行授权优化后才能补齐课程中的优化验收部分。',
        '','交付核对：JMX、环境与参数、并发数/吞吐/P95/错误率、连续监控、SQL摘要、瓶颈候选分析、同条件复测和原始数据已保存。业务源文件SHA256一致，原库关键数据一致。按用户限制，本次不提交业务优化改动。',
        '','复现前提：保留本地9行账号CSV及对应证书，不把含密码的CSV提交公共仓库。`复现脚本/`保存本次测试专用脚本与加密处理器副本，项目内的`performance`模块及业务源码是实际运行依赖。测试库已清理，复现时由脚本重新建立。']
    report(folder,state)
    md=folder/'完整测试报告.md'
    text=md.read_text(encoding='utf-8')+'\n'.join(appendix)+'\n'
    md.write_text(text,encoding='utf-8')
    index=folder/'index.html'
    original=index.read_text(encoding='utf-8')
    table='<style>table{border-collapse:collapse;width:100%;font-size:15px}th,td{border-bottom:1px solid #d8e0e8;padding:10px;text-align:right}th:nth-child(2),td:nth-child(2){text-align:left}th{background:#edf3f9}details{margin:24px 0}summary{cursor:pointer}</style><h2>正式300秒核心指标</h2><table><thead><tr><th>轮次</th><th>场景</th><th>样本数</th><th>P95 ms</th><th>P99 ms</th><th>错误率</th><th>请求/秒</th></tr></thead><tbody>'
    for row in rows:
        table+=f'<tr><td>{row["轮次"]}</td><td>{row["场景"]}</td><td>{row["样本数"]:,}</td><td>{row["P95毫秒"]}</td><td>{row["P99毫秒"]}</td><td>{row["错误率百分比"]:.2f}%</td><td>{row["每秒业务请求"]:.2f}</td></tr>'
    table+='</tbody></table><p>每场景9个独立账号，两轮同代码、同快照复测。错误率0%只证明当前受测负载运行成功，不代表已完成课程的优化改善或教师认可的达标保持证明。</p>'
    original=original[:original.index('<pre>')]+table+'<details><summary>展开完整报告与限制说明</summary><pre>'+html.escape(text)+'</pre></details></html>'
    index.write_text(original,encoding='utf-8')
    with (folder/'核心指标汇总.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    scripts=folder/'复现脚本'
    scripts.mkdir(exist_ok=True)
    for name in ['run_week89_existing.py','formal_server.py','windows_metrics.py','build_performance_plans.py','run_supplied_plans.py','finalize_week89_report.py']:
        shutil.copyfile(ROOT/'performance'/name,scripts/name)
    for name in ['seal-request.groovy','open-response.groovy']:
        shutil.copyfile(ROOT/'performance/jmeter'/name,scripts/name)
    manifest={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file() and p.name!='sha256-manifest.json'}
    write_json(folder/'sha256-manifest.json',manifest)
    if args.publish: print('PUBLISHED '+publish(folder))
    print(json.dumps({'validated_runs':len(rows),'all_formal_samples':sum(r['样本数'] for r in rows),'rows':rows},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
