"""Paired baseline/optimized runs from one immutable data snapshot."""
import csv
import difflib
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime
from performance import run_week89_existing as base

OPT=base.ROOT/'performance/optimization-20261105'
OUTPUT=OPT/('comparison-'+base.STAMP)

def fingerprint(db):
    digest=hashlib.sha256()
    with base.connect(db) as c:
        with c.cursor() as s:
            s.execute('SHOW TABLES')
            for t in sorted(row[0] for row in s.fetchall()):
                s.execute('SELECT * FROM '+base.quoted(t))
                values=sorted(json.dumps(r,default=str,ensure_ascii=False) for r in s.fetchall())
                digest.update(json.dumps([t,values],ensure_ascii=False).encode('utf-8'))
    return digest.hexdigest()

def source_changes(folder):
    old=json.loads((OPT/'baseline-source-manifest.json').read_text(encoding='utf-8'))
    current=base.code_manifest()
    changed=[name for name in current if current[name]!=old.get(name)]
    changed.append('requirements.txt')
    code=folder/'代码变更'
    code.mkdir()
    patch=[]
    for name in changed:
        source=base.ROOT/name
        after=code/'after'/name
        after.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,after)
        prior=OPT/'before'/Path(name).name
        if name in old or name=='requirements.txt':
            assert prior.is_file(),name
            if name in old: assert base.sha(prior)==old[name],name
            before=code/'before'/name
            before.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(prior,before)
            previous=prior.read_text(encoding='utf-8').splitlines(keepends=True)
        else: previous=[]
        patch.extend(difflib.unified_diff(previous,source.read_text(encoding='utf-8').splitlines(keepends=True),fromfile='before/'+name,tofile='after/'+name))
    (code/'performance-optimization.patch').write_text(''.join(patch),encoding='utf-8')
    return changed

def finish(folder,state):
    rows=[]
    for key in base.LABELS:
        before=next(r for r in state['runs'] if r['scenario']==key and r['version']=='before')
        after=next(r for r in state['runs'] if r['scenario']==key and r['version']=='after')
        a,b=before['measurement'],after['measurement']
        improvement=(a['p95_ms']-b['p95_ms'])/a['p95_ms']*100
        rows.append({'场景':base.TITLES[key],'优化前P95毫秒':a['p95_ms'],'优化后P95毫秒':b['p95_ms'],
                     'P95改善百分比':improvement,'优化前每秒请求':a['throughput_rps_fixed_window'],
                     '优化后每秒请求':b['throughput_rps_fixed_window'],'优化前错误率百分比':a['error_percent'],
                     '优化后错误率百分比':b['error_percent'],
                     '满足20%改善及错误率要求':improvement>=20 and a['error_percent']<=1 and b['error_percent']<=1})
    state['comparison']=rows
    state['all_targets_met']=all(r['满足20%改善及错误率要求'] for r in rows)
    state['changed_files']=source_changes(folder)
    lines=['# 第8、9周性能优化与同条件复测报告','',f"执行批次：{base.STAMP}（Asia/Shanghai）。",
        '','本次使用与已有基线SHA256完全一致的优化前业务代码副本，和工作区中的优化后代码，在相同机器、MySQL实例、Python、TLS证书参数及JMeter负载下比较。优化包含服务器配置变化：Werkzeug 1.0.1 HTTP/1.0开发服务器改为Cheroot 11.1.2 HTTP/1.1、16个工作线程及持久连接。该部署变化是明确列出的优化项，不宣称两版HTTP服务器实现相同。六个正式窗口均从同一不可变种子快照恢复，逐轮对全表数据计算SHA256验证初态一致。未向原业务库创建测试订单。',
        '','负载：9个独立账号；9秒升压；每个场景每版运行390秒，以首个HTTP样本时间为锚点跳过70秒，统计随后300秒内开始的业务请求。登录间隔1000ms，查询500ms，加购物车和下单各500ms。失败保留；每30秒验证9个线程持续参与且grpThreads=9。',
        '','## 优化前后核心结果','','| 场景 | 前P95 ms | 后P95 ms | 降低比例 | 前请求/秒 | 后请求/秒 | 后错误率 | 达标 |','|---|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r['场景']} | {r['优化前P95毫秒']} | {r['优化后P95毫秒']} | {r['P95改善百分比']:.2f}% | {r['优化前每秒请求']:.2f} | {r['优化后每秒请求']:.2f} | {r['优化后错误率百分比']:.3f}% | {'是' if r['满足20%改善及错误率要求'] else '否'} |")
    lines += ['','降低比例=(优化前P95−优化后P95)/优化前P95×100%。采用nearest-rank，按同一业务请求标签计算，包含失败请求。下单不把加购物车或初始化请求混入统计；吞吐量=正式业务样本/300秒。虚拟用户包含等待，观测速率不是系统最大容量。',
        '','查询优化分两步验证：第一版仅优化业务读路径，正式P95由9ms降至8ms（11.11%），未达20%，未发布为达标。随后加入HTTPS持久连接的服务器配置优化。查询基线沿用本次预先固定的原始基线窗口，并核对新的完整种子数据SHA256与该窗口初态完全相同；未改选更慢样本或调整统计窗口。中间阶段的原始记录保存在优化过程记录目录。',
        '','## 代码优化与安全语义','',
        '- 登录证书验证：每次仍调用OpenSSL验证链及签名；有效期、签发者、用户名绑定和数据库公钥绑定仍检查。用解析后的X.509对象读取已存在的元数据，将额外公钥和算法描述读取合并，热路径由7次子进程降为2次，不缓存认证成功结果。',
        '- 国密解密：将gmssl C1C2C3格式转换为OpenSSL EVP所需的DER编码，使用现有本机libcrypto执行进程内SM2解密并验证C3。缓存最多16个不可变密钥对象，每次请求独立EVP上下文；SM4会话密钥、Nonce和request_id仍每次随机，原GCM校验、防重放和审计保留。不可用平台回退原gmssl实现；优化版实现及DLL校验值见settings.json的server.sm2。',
        '- 数据库读取：每个服务使用最多2个只读连接的有界池，autocommit单次SELECT避免额外只读COMMIT；订单详情的多次SELECT仍在一致性事务中读取。写事务、FOR UPDATE、库存条件扣减及审计持久化保持不变。',
        '- 鉴权状态每次仍查数据库：只读取id、用户名、角色、安全版本和MFA状态，避免鉴权时解密无关手机号。账号禁用和安全版本号变更立即生效，未缓存权限或库存。',
        '- HTTPS服务器：使用有界工作线程和受限持久连接数量的Cheroot代替逐请求建连的开发服务器。保留TLS和应用层加密；客户端请求间隔、KeepAlive设置和业务内容不变。新服务器负责正确处理未读取的请求体，已测试401提前返回后同一连接的下一请求仍正确。',
        '','## 正确性、监控和证据','','回归测试输出保存在regression-tests.txt；集成检查证明有效Token可访问，安全版本更新和禁用账号后均立即返回401。SM2兼容、并发和C1/C2/C3篡改拒绝已测试。',
        '','每轮保留完整raw.jtl、正式measurement.jtl、每2秒CPU/内存/连接/锁等待monitor.csv、SQL摘要增量、数据库前后核对及JMeter图表。写请求均为应用层加密；实际支付不在本次范围。',
        '','| 版本/场景 | 正式样本 | 失败数 | 后端单核CPU均值/峰值 | 私有内存峰值MB | SQL锁等待采样峰值 |','|---|---:|---:|---:|---:|---:|']
    for run in state['runs']:
        m=run['measurement'];r=run['resources'];cpu=r.get('backend_cpu_percent_one_core',{})
        lines.append(f"| {run['version']}/{run['scenario']} | {m['samples']} | {m['failures']} | {cpu.get('mean',0):.1f}% / {cpu.get('max',0):.1f}% | {r.get('backend_private_mb',{}).get('max',0):.1f} | {r.get('db_lock_waits',{}).get('max',0):.0f} |")
        if run['scenario']=='order':
            lines.append(f"\n{run['version']}全程成功订单/数据库新增订单/库存扣减一致：{run['order_accounting_matches']}，新增订单{run['db_orders_created']}笔。\n")
    lines += ['',f"原库关键数据未改动：{state['original_database_unchanged']}。优化版测试期间源文件未变动：{state['optimized_source_frozen']}。",
        '','CPU按进程与整机分别记录；Python进程CPU不包含短命OpenSSL子进程，比较登录总资源应结合整机CPU。SQL摘要不能度量Python锁等待，不能当成函数级性能剖析。',
        '','## 适用范围与交付说明','','这是当前数据规模、9用户和给定请求间隔下的配对比较。PERF_TEST_MODE=1的限流阈值与此前基线一致；默认安全限流未关闭或放宽。服务器与测试端共用一台机器，未宣称最大容量或生产环境性能。每版每场景一轮300秒正式窗口，原有两轮凌晨基线另作为历史材料保留，达标结论使用本次同快照配对数据。',
        '','代码变更目录提供优化前后源码及可审查补丁，没有把用户原有未提交修改混入“本次优化”。没有自动提交整个工作区。重启当前项目后端后优化代码才会对已有2333服务生效；本次测试使用隔离24433端口。',
        '','原有报告保留在此前工作区结果目录；本报告替换D盘主结果入口。运行依赖与命令保存在各轮settings.json，源代码清单、种子数据指纹、原始错误及源文件哈希均可核对。',
        '','OpenSSL接口依据：[EVP_PKEY_decrypt](https://docs.openssl.org/3.0/man3/EVP_PKEY_decrypt/) 和 [SM2](https://docs.openssl.org/3.0/man7/EVP_PKEY-SM2/)。服务器依据：[Cheroot WSGI](https://cheroot.cherrypy.dev/en/latest/pkg/cheroot.wsgi/) 与 [TLS适配器](https://cheroot.cherrypy.dev/en/latest/pkg/cheroot.ssl.builtin/)。']
    text='\n'.join(lines)+'\n'
    (folder/'完整测试报告.md').write_text(text,encoding='utf-8')
    with (folder/'优化前后核心指标.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    links=''.join(f'<li><a href="{r["version"]}/{r["scenario"]}/measurement-html/index.html">{r["version"]} {r["title"]}</a></li>' for r in state['runs'])
    table='<table><tr><th>场景</th><th>优化前P95</th><th>优化后P95</th><th>降低</th><th>错误率</th><th>达标</th></tr>'
    for r in rows: table+=f"<tr><td>{r['场景']}</td><td>{r['优化前P95毫秒']}ms</td><td>{r['优化后P95毫秒']}ms</td><td>{r['P95改善百分比']:.2f}%</td><td>{r['优化后错误率百分比']:.2f}%</td><td>{'是' if r['满足20%改善及错误率要求'] else '否'}</td></tr>"
    (folder/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>性能优化验证</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:36px auto;padding:0 20px}table{border-collapse:collapse;width:100%}th,td{padding:12px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;background:#f5f7fa;padding:20px}summary{cursor:pointer}</style><h1>第8、9周性能优化验证</h1>'+table+'</table><h2>JMeter原始图表</h2><ul>'+links+'</ul><p><a href="完整测试报告.md">完整报告</a> · <a href="优化前后核心指标.csv">指标表</a></p><details><summary>展开完整说明</summary><pre>'+html.escape(text)+'</pre></details>',encoding='utf-8')
    base.write_json(folder/'summary.json',state)
    return rows

def main():
    OUTPUT.mkdir()
    for version in ['before','after']: (OUTPUT/version).mkdir()
    state={'status':'running','directory':str(OUTPUT),'runs':[],'purpose':'authorized targeted optimization and paired verification'}
    def checkpoint(message):
        state['progress']=message;base.write_json(OUTPUT/'progress.json',state);print(datetime.now().isoformat(timespec='seconds')+' '+message,flush=True)
    frozen=base.code_manifest();base.write_json(OUTPUT/'optimized-source-manifest.json',frozen)
    requirements_sha=base.sha(base.ROOT/'requirements.txt')
    old=json.loads((OPT/'baseline-source-manifest.json').read_text(encoding='utf-8'))
    before_original=base.database_state('adb')
    base.write_json(OUTPUT/'original-database-before.json',before_original)
    seed='adb_perf_seed_'+base.STAMP; work='adb_perf_run_'+base.STAMP;base.OWNED.update([seed,work])
    state['owned_test_databases']=[seed,work]
    _,definitions,data,mysql=base.source_capture()
    state['environment']={'mysql':mysql,'machine':base.machine_info(),'python':sys.version,'java':'JBR21.0.7','jmeter':'5.6.3','baseline_server':'Werkzeug1.0.1 HTTP/1.0, threaded','optimized_server':'Cheroot11.1.2 HTTP/1.1, 16 workers, keepalive','requirements_sha256':requirements_sha,'snapshot_row_counts':{k:len(v) for k,v in data.items()}}
    base.create_database(seed,definitions,data);del data
    with base.connect(seed) as c:
        with c.cursor() as s:
            s.execute('DELETE FROM cart_items WHERE user_id IN (SELECT id FROM users WHERE username IN ('+','.join(['%s']*9)+'))',base.USERS)
    state['seed_sha256']=fingerprint(seed)
    try:
        for key in ['query','order','login']:
            for version in ['before','after']:
                if key=='query' and version=='before':
                    prior_folder=OPT/'comparison-20261105091626'
                    prior=json.loads((prior_folder/'progress.json').read_text(encoding='utf-8'))
                    candidate=next(r for r in prior['runs'] if r['scenario']=='query' and r['version']=='before')
                    if candidate['initial_data_sha256']==state['seed_sha256']:
                        run=json.loads(json.dumps(candidate))
                        source=Path(run['directory']);dest=OUTPUT/'before/query'
                        shutil.copytree(source,dest)
                        run['reused_from']=str(source);run['directory']=str(dest)
                        state['runs'].append(run)
                        checkpoint('Reused the fixed predeclared query baseline; exact seed data SHA256 matches')
                        continue
                base.TEST_SOURCE_ROOT=OPT/'baseline_source' if version=='before' else base.ROOT
                base.clone_seed(seed,work,definitions)
                assert fingerprint(work)==state['seed_sha256']
                checkpoint(f'{version} {key}: 390 seconds, 300-second formal window')
                run=base.run_one(key,OUTPUT/version/key,work,390,9)
                run['version']=version;run['initial_data_sha256']=state['seed_sha256'];state['runs'].append(run)
                checkpoint(f'Completed {version} {key}: '+json.dumps(run['measurement'],ensure_ascii=False))
                assert run['valid_fixed_load'] and not run['all_failures']
                if key=='order': assert run['order_accounting_matches']
                folder=Path(run['directory'])
                with (folder/'report-console.txt').open('w',encoding='utf-8') as f:
                    result=subprocess.run([str(base.JAVA),'-Xmx1g','-jar',str(base.JMETER),'-g',str(folder/'measurement.jtl'),'-o',str(folder/'measurement-html'),'-j',str(folder/'report-jmeter.log')],cwd=base.ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
                assert result.returncode==0
                if version=='after':
                    paired=next(r for r in state['runs'] if r['scenario']==key and r['version']=='before')
                    improvement=(paired['measurement']['p95_ms']-run['measurement']['p95_ms'])/paired['measurement']['p95_ms']*100
                    checkpoint(f'Paired {key} P95 improvement: {improvement:.2f}%')
                    if improvement<20:
                        raise RuntimeError(f'{key} P95 improvement {improvement:.2f}% is below 20%; keep evidence and tune before publishing')
        state['optimized_source_frozen']=frozen==base.code_manifest();assert state['optimized_source_frozen']
        assert requirements_sha==base.sha(base.ROOT/'requirements.txt')
        state['original_database_unchanged']=before_original==base.database_state('adb');assert state['original_database_unchanged']
        state['status']='complete'
    except Exception as exc:
        state['status']='failed';state['error']=str(exc);checkpoint('FAILED '+repr(exc));raise
    finally:
        for db in [work,seed]: base.drop_owned(db)
        base.write_json(OUTPUT/'progress.json',state)
    shutil.copyfile(OPT/'regression-tests.txt',OUTPUT/'regression-tests.txt')
    probe=max(OPT.glob('probe-*'),key=lambda p:p.name)
    shutil.copyfile(probe/'auth-regression/checks.json',OUTPUT/'auth-regression.json')
    tuning=OUTPUT/'优化过程记录'
    tuning.mkdir()
    prior=OPT/'comparison-20261105091626'
    shutil.copyfile(prior/'progress.json',tuning/'第一版状态.json')
    (tuning/'第一版查询').mkdir()
    for name in ['raw.jtl','measurement.jtl','monitor.csv','settings.json','result.json']:
        shutil.copyfile(prior/'after/query'/name,tuning/'第一版查询'/name)
    base.write_json(OUTPUT/'baseline-source-manifest.json',old)
    for name in ['run_optimization_comparison.py','run_week89_existing.py','formal_server.py','windows_metrics.py']:
        dest=OUTPUT/'复现脚本'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(base.ROOT/'performance'/name,dest)
    rows=finish(OUTPUT,state)
    base.write_json(OUTPUT/'sha256-manifest.json',{p.relative_to(OUTPUT).as_posix():base.sha(p) for p in OUTPUT.rglob('*') if p.is_file()})
    if state['all_targets_met']:
        print('PUBLISHED '+base.publish(OUTPUT),flush=True)
    else: print('TARGET NOT MET: preserve original published results; inspect comparison',flush=True)
    print(json.dumps(rows,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
