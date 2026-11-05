"""Retest the current optimized application without changing business code."""
import csv
from datetime import datetime, timezone, timedelta
import html
import importlib.metadata
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from performance import run_week89_existing as base
from performance.run_optimization_comparison import fingerprint

STAMP=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
OUT=base.ROOT/'performance/results'/('优化后复测结果-'+STAMP)
PREVIOUS=base.ROOT/'performance/optimization-20261105/comparison-20261105094026'

def publish(folder):
    target=base.SOURCE/folder.name
    staging=base.SOURCE/(folder.name+'-写入中')
    assert target.parent.resolve()==base.SOURCE.resolve() and not target.exists() and not staging.exists()
    shutil.copytree(folder,staging)
    for p in folder.rglob('*'):
        if p.is_file(): assert base.sha(p)==base.sha(staging/p.relative_to(folder))
    staging.rename(target)
    return target

def make_report(state,previous):
    rows=[]
    for run in state['runs']:
        m=run['measurement']
        old=next(r for r in previous['runs'] if r['version']=='after' and r['scenario']==run['scenario'])['measurement']
        rows.append({'场景':run['title'],'样本数':m['samples'],'平均ms':m.get('average_ms'),
            'P95ms':m.get('p95_ms'),'P99ms':m.get('p99_ms'),'错误率百分比':m.get('error_percent'),
            '请求每秒':m.get('throughput_rps_fixed_window'),'上次优化版P95ms':old['p95_ms'],
            'P95变化百分比':(m['p95_ms']/old['p95_ms']-1)*100 if m.get('p95_ms') is not None else None})
    state['metrics']=rows
    lines=['# 优化后代码独立复测报告','',f'测试批次：{STAMP}，Asia/Shanghai。',
        '','本轮仅测试当前优化版，未修改业务代码。三个场景顺序执行，每场景9个独立账号、9秒升压、运行390秒；以首个HTTP样本为锚点跳过70秒，统计随后300秒内开始的业务请求，原始数据完整保留。',
        '','登录等待1000ms，商品查询500ms，加购物车及下单各500ms；与上次测试保持相同口径。服务器和JMeter同机，使用Cheroot HTTPS及OpenSSL EVP优化路径，PERF_TEST_MODE=1限流配置与上次一致。每30秒检查9线程持续参与，失败不筛除。',
        '','## 本轮正式300秒结果','','| 场景 | 样本数 | 平均ms | P95 ms | P99 ms | 错误率 | 请求/秒 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['场景']} | {r['样本数']} | {r['平均ms'] or 0:.2f} | {r['P95ms']} | {r['P99ms']} | {r['错误率百分比'] or 0:.3f}% | {r['请求每秒'] or 0:.2f} |")
    lines+=['','## 与上次优化版对照','','| 场景 | 上次优化P95 ms | 本轮P95 ms | 变化 |','|---|---:|---:|---:|']
    for r in rows:
        change=f"{r['P95变化百分比']:+.2f}%" if r['P95变化百分比'] is not None else '无有效样本'
        lines.append(f"| {r['场景']} | {r['上次优化版P95ms']} | {r['P95ms']} | {change} |")
    lines+=['','变化为（本轮−上次优化版）/上次优化版，正数表示变慢、负数表示变快。本轮没有重新运行未优化版，因此这是重复性复测，不把自然波动算作新的优化收益。历史优化前后报告独立保留。',
        '',f"与上次优化源码一致：{state['same_as_previous_optimized_source']}；初始数据库全表数据指纹与上次一致：{state['same_as_previous_seed']}。",
        '','## 有效性与数据核对','']
    for r in state['runs']:
        lines.append(f"- {r['title']}：全程HTTP失败{r['all_failures']}次，固定9线程覆盖有效={r['valid_fixed_load']}，进程退出码={r['settings'].get('exit_code')}。")
        if r['scenario']=='order':
            lines.append(f"- 全程成功订单/数据库新增订单/库存扣减一致={r['order_accounting_matches']}，创建订单{r['db_orders_created']}笔，消耗库存{r['db_stock_consumed']}件；只影响一次性测试库，未执行支付。")
    lines+=['',f"回归测试通过：{state['regression_passed']}；测试期间业务源码与依赖文件未变：{state['source_frozen']}；原数据库全表数据未变：{state['original_database_unchanged']}。",
        f"临时数据库清理成功：{state['temporary_databases_removed']}；测试端口已释放：{state['test_port_released']}。",
        '','## 交付文件与范围','','每场景目录保存实际执行JMX、settings.json命令参数、raw.jtl、measurement.jtl、failures.csv、JMeter图表、每2秒资源监控monitor.csv、SQL摘要及数据库前后核对。regression-tests.txt保留本轮回归输出，source-manifest.json记录业务源文件SHA256。',
        '','本次测试使用数据库副本，每个场景从同一初态恢复。测试账号购物车仅在副本中清空。原始证书及密码CSV不复制到结果目录。',
        '','虚拟用户包含等待时间，当前观测速率不代表最大容量；本结果仅适用于当前数据规模与负载。服务器配置、整机背景负载、数据变化等会影响与历史记录的差异；资源监控可供核对。']
    text='\n'.join(lines)+'\n'
    (OUT/'完整复测报告.md').write_text(text,encoding='utf-8')
    with (OUT/'核心指标.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    table='<table><tr><th>场景</th><th>样本</th><th>P95 ms</th><th>错误率</th><th>请求/秒</th></tr>'
    for r in rows: table+=f"<tr><td>{r['场景']}</td><td>{r['样本数']}</td><td>{r['P95ms']}</td><td>{r['错误率百分比'] or 0:.3f}%</td><td>{r['请求每秒'] or 0:.2f}</td></tr>"
    links=''.join(f'<li><a href="{r["scenario"]}/measurement-html/index.html">{r["title"]} JMeter图表</a></li>' for r in state['runs'])
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>优化后独立复测</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:36px auto;padding:0 24px}table{width:100%;border-collapse:collapse}td,th{padding:12px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;background:#f5f7fa;padding:20px}summary{cursor:pointer}</style><h1>优化后代码独立复测</h1>'+table+'</table><ul>'+links+'</ul><p><a href="完整复测报告.md">完整报告</a> · <a href="核心指标.csv">指标CSV</a></p><details><summary>完整说明</summary><pre>'+html.escape(text)+'</pre></details>',encoding='utf-8')
    base.write_json(OUT/'summary.json',state)

def main():
    OUT.mkdir()
    state={'stamp':STAMP,'status':'running','directory':str(OUT),'runs':[]}
    def checkpoint(message):
        state['progress']=message;base.write_json(OUT/'progress.json',state)
        print(datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')+' '+message,flush=True)
    code=base.code_manifest();req=base.sha(base.ROOT/'requirements.txt')
    base.write_json(OUT/'source-manifest.json',code)
    previous=json.loads((PREVIOUS/'summary.json').read_text(encoding='utf-8'))
    prior_code=json.loads((PREVIOUS/'optimized-source-manifest.json').read_text(encoding='utf-8'))
    state['same_as_previous_optimized_source']=code==prior_code
    state['environment']={'machine':base.machine_info(),'python':sys.version,
        'packages':{n:importlib.metadata.version(n) for n in ['Flask','Werkzeug','cheroot','cryptography','gmssl','PyMySQL']},
        'requirements_sha256':req,'java':'JBR21.0.7','jmeter':'5.6.3','formal_window_seconds':300}
    original_db=base.connect()
    original_name=original_db.db.decode() if isinstance(original_db.db,bytes) else original_db.db
    original_db.close()
    original_hash=fingerprint(original_name)
    base.write_json(OUT/'original-database-before.json',base.database_state(original_name))
    state['original_data_sha256_before']=original_hash
    checkpoint('Running regression tests against the unchanged optimized source')
    with (OUT/'regression-tests.txt').open('w',encoding='utf-8') as f:
        test=subprocess.run([sys.executable,'-X','utf8','-m','pytest','api_service4/tests','-q'],cwd=base.ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
    state['regression_passed']=test.returncode==0
    if test.returncode:
        state['status']='failed';checkpoint('Regression failure; inspect regression-tests.txt');return
    for port in range(24433,24440):
        with socket.socket() as sock:
            try: sock.bind(('127.0.0.1',port))
            except OSError: continue
            base.PORT=port;break
    else: raise RuntimeError('No available isolated test port')
    base.TEST_SOURCE_ROOT=base.ROOT
    state['test_port']=base.PORT
    seed='adb_perf_seed_'+base.STAMP;work='adb_perf_run_'+base.STAMP
    base.OWNED.update([seed,work]);state['owned_test_databases']=[seed,work]
    _,definitions,data,mysql=base.source_capture();state['environment']['mysql']=mysql
    base.create_database(seed,definitions,data);del data
    try:
        with base.connect(seed) as c:
            with c.cursor() as s:
                s.execute('DELETE FROM cart_items WHERE user_id IN (SELECT id FROM users WHERE username IN ('+','.join(['%s']*9)+'))',base.USERS)
                s.execute('SELECT stock FROM products WHERE id=3')
                if s.fetchone()[0]<5000:
                    s.execute('UPDATE products SET stock=5000 WHERE id=3')
                    state['fixture_adjustment']='Test-copy stock raised to 5000 to cover sustained orders; original stock unchanged'
        state['seed_sha256']=fingerprint(seed)
        state['same_as_previous_seed']=state['seed_sha256']==previous['seed_sha256']
        for key in ['query','order','login']:
            base.clone_seed(seed,work,definitions)
            assert fingerprint(work)==state['seed_sha256']
            checkpoint(f'START {key}: 9 users, 390 seconds, formal window 300 seconds')
            run=base.run_one(key,OUT/key,work,390,9)
            state['runs'].append(run)
            checkpoint(f'COMPLETE {key}: '+json.dumps(run['measurement'],ensure_ascii=False))
            directory=OUT/key
            if run['measurement']['samples']:
                with (directory/'report-console.txt').open('w',encoding='utf-8') as f:
                    result=subprocess.run([str(base.JAVA),'-Xmx1g','-jar',str(base.JMETER),'-g',str(directory/'measurement.jtl'),'-o',str(directory/'measurement-html'),'-j',str(directory/'report-jmeter.log')],cwd=base.ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
                assert result.returncode==0
        state['source_frozen']=code==base.code_manifest() and req==base.sha(base.ROOT/'requirements.txt')
        state['original_database_unchanged']=original_hash==fingerprint(original_name)
        state['valid_all_runs']=all(r['valid_fixed_load'] and r['settings'].get('exit_code')==0 for r in state['runs'])
        state['all_requests_successful']=all(r['all_failures']==0 for r in state['runs'])
        state['status']='complete'
    except Exception as exc:
        state['status']='failed';state['error']=repr(exc);checkpoint('FAILED '+repr(exc));raise
    finally:
        for name in [work,seed]: base.drop_owned(name)
        with base.connect() as c:
            with c.cursor() as s:
                s.execute('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN (%s,%s)',(seed,work))
                state['temporary_databases_removed']=not s.fetchall()
        with socket.socket() as sock:
            sock.settimeout(1);state['test_port_released']=sock.connect_ex(('127.0.0.1',base.PORT))!=0
        base.write_json(OUT/'progress.json',state)
    assert state['source_frozen'] and state['original_database_unchanged']
    base.write_json(OUT/'original-database-after.json',base.database_state(original_name))
    make_report(state,previous)
    with (base.ROOT/'performance/data/users-local.csv').open(encoding='utf-8-sig',newline='') as f:
        password=next(csv.reader(f))[1].encode('utf-8')
    assert all(password not in p.read_bytes() for p in OUT.rglob('*') if p.is_file())
    checkpoint('COMPLETE: reports and database verification finished')
    manifest={p.relative_to(OUT).as_posix():base.sha(p) for p in OUT.rglob('*') if p.is_file()}
    base.write_json(OUT/'sha256-manifest.json',manifest)
    dest=publish(OUT)
    base.write_json(base.ROOT/'performance/results/latest-optimized-retest.json',{'source':str(OUT),'destination':str(dest),'metrics':state['metrics'],'status':state['status']})
    print('PUBLISHED '+str(dest),flush=True)

if __name__=='__main__':main()
