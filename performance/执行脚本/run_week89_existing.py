"""Checkpointed tests of existing code, with isolated MySQL data and repeatable load."""
from collections import Counter
from copy import deepcopy
import argparse
import csv
from datetime import datetime
import hashlib
import html
import json
import math
import os
import platform
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as E
import zipfile

import pymysql
from api_service4.config.init import get_config
from performance.build_performance_plans import prop, add, timer
from performance.run_supplied_plans import stats, JAVA, JMETER, SOURCE, ROOT
from performance.windows_metrics import Monitor

LABELS = {'login': '01_普通用户登录', 'query': '02_商品查询', 'order': '03_创建订单'}
TITLES = {'login': '登录性能测试', 'query': '商品查询性能测试', 'order': '下单性能测试'}
STAMP = datetime.now().strftime('%Y%m%d%H%M%S')
PORT = 24433
USERS = ['user0010','user0011','user0012','user0013','user015','user016','user017','user018','user019']

def write_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def code_manifest():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT/'api_service4').rglob('*.py'))}

def machine_info():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            cpu=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    except OSError:
        cpu=platform.processor()
    return {'os':platform.platform(),'cpu':cpu,'logical_processors':os.cpu_count()}

def connect(db=None):
    cfg = dict(get_config().MYSQL_CONFIG)
    cfg.pop('database', None)
    if db is not None: cfg['db'] = db
    cfg['autocommit'] = True
    cfg['connect_timeout'] = 5
    cfg['read_timeout'] = 20
    return pymysql.connect(**cfg)

def quoted(name):
    if not re.fullmatch(r'[A-Za-z0-9_]+', name): raise ValueError('Invalid SQL identifier')
    return '`'+name+'`'

def source_capture():
    """Read original rows in one consistent transaction; never write to original DB."""
    with connect() as c:
        db = c.db.decode() if isinstance(c.db, bytes) else c.db
        with c.cursor() as s:
            s.execute('SHOW FULL TABLES WHERE Table_type = "BASE TABLE"')
            tables = [r[0] for r in s.fetchall()]
            definitions = {}
            for t in tables:
                s.execute('SHOW CREATE TABLE '+quoted(t))
                definitions[t] = s.fetchone()[1]
            s.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            s.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
            data = {}
            for t in tables:
                s.execute('SELECT * FROM '+quoted(t))
                data[t] = s.fetchall()
            c.commit()
            s.execute('SELECT VERSION()')
            version = s.fetchone()[0]
    return db, definitions, data, version

def create_database(name, definitions, data):
    if not re.fullmatch(r'adb_perf_(?:seed|run)_\d{14}', name): raise ValueError('Unsafe test DB')
    with connect() as c:
        with c.cursor() as s:
            s.execute('CREATE DATABASE '+quoted(name)+' CHARACTER SET utf8mb4')
            c.select_db(name)
            s.execute('SET FOREIGN_KEY_CHECKS=0')
            for ddl in definitions.values(): s.execute(ddl)
            for t, rows in data.items():
                if rows:
                    placeholders = ','.join(['%s']*len(rows[0]))
                    s.executemany('INSERT INTO '+quoted(t)+' VALUES ('+placeholders+')', rows)
            s.execute('SET FOREIGN_KEY_CHECKS=1')

def drop_owned(name):
    if name not in OWNED or not re.fullmatch(r'adb_perf_(?:seed|run)_\d{14}', name):
        raise ValueError('Refusing to drop unowned DB')
    with connect() as c:
        with c.cursor() as s: s.execute('DROP DATABASE IF EXISTS '+quoted(name))

def clone_seed(seed, target, definitions):
    drop_owned(target)
    with connect() as c:
        with c.cursor() as s:
            s.execute('CREATE DATABASE '+quoted(target)+' CHARACTER SET utf8mb4')
            c.select_db(target)
            s.execute('SET FOREIGN_KEY_CHECKS=0')
            for ddl in definitions.values(): s.execute(ddl)
            for t in definitions:
                s.execute('INSERT INTO '+quoted(target)+'.'+quoted(t)+' SELECT * FROM '+quoted(seed)+'.'+quoted(t))
            s.execute('SET FOREIGN_KEY_CHECKS=1')

def database_state(db):
    with connect(db) as c:
        with c.cursor(pymysql.cursors.DictCursor) as s:
            result = {}
            for t in ['users','products','cart_items','orders','order_items','audit_logs','refresh_tokens']:
                s.execute('SELECT COUNT(*) n FROM '+quoted(t))
                result[t+'_count'] = s.fetchone()['n']
            s.execute('SELECT id,status,stock,price_cents FROM products WHERE id=3')
            result['test_product'] = s.fetchone()
            placeholders = ','.join(['%s']*len(USERS))
            s.execute('SELECT id,username FROM users WHERE username IN ('+placeholders+') ORDER BY id', USERS)
            result['accounts'] = s.fetchall()
            ids = [a['id'] for a in result['accounts']]
            s.execute('SELECT COUNT(*) n FROM cart_items WHERE user_id IN ('+','.join(['%s']*len(ids))+')', ids)
            result['test_cart_rows'] = s.fetchone()['n']
            s.execute('SELECT COUNT(*) n FROM orders WHERE user_id IN ('+','.join(['%s']*len(ids))+')', ids)
            result['test_orders'] = s.fetchone()['n']
            return result

def sql_digest(db):
    with connect() as c:
        with c.cursor(pymysql.cursors.DictCursor) as s:
            s.execute('SELECT DIGEST,DIGEST_TEXT,COUNT_STAR,SUM_TIMER_WAIT,SUM_LOCK_TIME,SUM_ERRORS,SUM_ROWS_EXAMINED FROM performance_schema.events_statements_summary_by_digest WHERE SCHEMA_NAME=%s', (db,))
            return {r['DIGEST']: r for r in s.fetchall()}

def digest_delta(before, after):
    rows = []
    for k,r in after.items():
        old = before.get(k, {})
        d = {'digest': k, 'sql_normalized': r['DIGEST_TEXT']}
        for key in ['COUNT_STAR','SUM_TIMER_WAIT','SUM_LOCK_TIME','SUM_ERRORS','SUM_ROWS_EXAMINED']:
            d[key] = int(r[key] or 0)-int(old.get(key) or 0)
        if d['COUNT_STAR'] <= 0: continue
        d['total_ms'] = d['SUM_TIMER_WAIT']/1e9
        d['mean_ms'] = d['total_ms']/d['COUNT_STAR']
        d['lock_ms'] = d['SUM_LOCK_TIME']/1e9
        rows.append(d)
    return sorted(rows,key=lambda r:r['total_ms'],reverse=True)

def prepare_plan(key, folder, duration, users, smoke=False):
    source = SOURCE/(TITLES[key]+'.jmx')
    root = E.parse(source)
    for node in root.findall('.//ResultCollector'): node.set('enabled','false')
    group = root.find('.//ThreadGroup')
    prop(group, 'ThreadGroup.num_threads', users)
    prop(group, 'ThreadGroup.ramp_time', 1 if smoke else 9)
    prop(group, 'ThreadGroup.scheduler', True, 'boolProp')
    prop(group, 'ThreadGroup.duration', duration)
    prop(group, 'ThreadGroup.delay', 0)
    prop(group, 'ThreadGroup.on_sample_error','stopthread')
    outer = group.find("elementProp[@name='ThreadGroup.main_controller']")
    prop(outer,'LoopController.loops',1)
    prop(outer,'LoopController.continue_forever',False,'boolProp')
    for n in root.findall('.//ConfigTestElement'):
        prop(n,'HTTPSampler.domain','127.0.0.1')
        prop(n,'HTTPSampler.protocol','https')
        prop(n,'HTTPSampler.port',PORT)
        prop(n,'HTTPSampler.connect_timeout',10000)
        prop(n,'HTTPSampler.response_timeout',15000)
    for n in root.findall('.//HTTPSamplerProxy'):
        for k,v in [('HTTPSampler.domain',''),('HTTPSampler.port',''),('HTTPSampler.protocol','')]: prop(n,k,v)
    for n in root.findall('.//CSVDataSet'):
        prop(n,'filename',(ROOT/'performance/data/users-local.csv').as_posix())
        for k,v in [('recycle',False),('stopThread',True),('ignoreFirstLine',False)]: prop(n,k,v,'boolProp')
    # Only one meaningful business loop; discard the empty historical loop.
    for tree in root.iter('hashTree'):
        nodes = list(tree)
        for i in range(0,len(nodes),2):
            n,sub = nodes[i:i+2]
            if n.tag != 'LoopController': continue
            if not list(sub):
                tree.remove(n); tree.remove(sub)
            else:
                prop(n,'LoopController.loops', '-1')
                prop(n,'LoopController.continue_forever',False,'boolProp')
    for tree in root.iter('hashTree'):
        nodes=list(tree)
        for i in range(0,len(nodes),2):
            n,sub = nodes[i:i+2]
            if n.tag != 'HTTPSamplerProxy': continue
            path=n.find("*[@name='HTTPSampler.path']").text
            if (key=='login' and path.endswith('/auth/login')) or (key=='query' and path=='/api/v1/products') or (key=='order' and path in ['/api/v1/cart/items','/api/v1/orders'] and n.find("*[@name='HTTPSampler.method']").text=='POST'):
                existing=sub.find('ConstantTimer')
                if existing is None: add(sub,timer(1000 if key=='login' else 500))
                else: prop(existing,'ConstantTimer.delay',1000 if key=='login' else 500)
    snapshot=folder/'plan-executed.jmx'
    root.write(snapshot,encoding='utf-8',xml_declaration=True)
    return snapshot, {'source':str(source),'source_sha256':sha(source),'executed_sha256':sha(snapshot),
        'users':users,'ramp_seconds':1 if smoke else 9,'duration_seconds':duration,'outer_loops':1,
        'business_loop':'infinite until duration','delay_ms_per_business_request':1000 if key=='login' else 500,
        'changes':['CLI listeners disabled','test-only port/database','fixed account per thread','infinite business loop and fixed pacing','removed empty historical loop']}

def start_server(db,folder):
    ready=folder/'server-ready.json'
    log=(folder/'server.log').open('w',encoding='utf-8')
    server_command=[sys.executable,'-X','utf8','-m','performance.formal_server','--database',db,'--port',str(PORT),'--ready',str(ready)]
    source_root=globals().get('TEST_SOURCE_ROOT')
    if source_root:
        server_command.extend(['--source-root',str(source_root)])
    proc=subprocess.Popen(server_command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    for _ in range(100):
        if proc.poll() is not None: raise RuntimeError('Test server failed; inspect '+str(folder/'server.log'))
        if ready.exists():
            try:
                with urllib.request.urlopen(f'https://127.0.0.1:{PORT}/api/v1/security/public-key',context=ssl._create_unverified_context(),timeout=1) as response:
                    if response.status==200: return proc,log,json.loads(ready.read_text(encoding='utf-8'))
            except Exception: pass
        time.sleep(.2)
    proc.terminate();proc.wait(timeout=10);log.close()
    raise RuntimeError('Test server startup timeout')

def stop_server(proc,log, pid):
    # Windows venv can add a launcher parent; terminate only our recorded server child.
    if pid!=proc.pid:
        subprocess.run(['taskkill','/PID',str(pid),'/F'],capture_output=True)
    if proc.poll() is None: proc.terminate()
    proc.wait(timeout=15)
    log.close()

def command(plan,folder):
    return [str(JAVA),'-Xms512m','-Xmx1g','-jar',str(JMETER),'-n','-t',str(plan),'-l',str(folder/'raw.jtl'),'-j',str(folder/'jmeter.log'),
        '-Jjmeter.save.saveservice.output_format=csv','-Jjmeter.save.saveservice.timestamp_format=ms',
        '-Jjmeter.save.saveservice.print_field_names=true','-Jjmeter.save.saveservice.thread_counts=true',
        '-Jjmeter.save.saveservice.response_data=false','-Jjmeter.save.saveservice.samplerData=false',
        '-Jjmeter.save.saveservice.requestHeaders=false','-Jjmeter.save.saveservice.responseHeaders=false']

def run_one(key,folder,db,duration,users,smoke=False):
    folder.mkdir()
    plan,settings=prepare_plan(key,folder,duration,users,smoke)
    before=database_state(db)
    write_json(folder/'database-before.json',before)
    server,serverlog,ready=start_server(db,folder)
    monitor=Monitor()
    samples=[]
    digest_before=sql_digest(db)
    args=command(plan,folder)
    settings['command']=args
    settings['server']=ready
    settings['started_local']=datetime.now().isoformat()
    write_json(folder/'settings.json',settings)
    began=time.monotonic()
    try:
        with (folder/'console.txt').open('w',encoding='utf-8') as output,connect() as mc:
            jm=subprocess.Popen(args,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
            while jm.poll() is None:
                row={'epoch_ms':round(time.time()*1000),'elapsed_seconds':time.monotonic()-began}
                row.update(monitor.sample({'backend':ready['pid'],'jmeter':jm.pid}))
                try:
                    with mc.cursor() as cursor:
                        cursor.execute('SELECT COUNT(*),SUM(COMMAND != "Sleep") FROM information_schema.PROCESSLIST WHERE DB=%s',(db,))
                        row['db_connections'],row['db_active_connections']=cursor.fetchone()
                        cursor.execute('SELECT COUNT(*) FROM performance_schema.data_lock_waits w JOIN performance_schema.threads t ON t.THREAD_ID=w.REQUESTING_THREAD_ID WHERE t.PROCESSLIST_DB=%s',(db,))
                        row['db_lock_waits']=cursor.fetchone()[0]
                except Exception as e: row['monitor_error']=type(e).__name__
                samples.append(row)
                # Durable checkpoints survive a client disconnect or quota interruption.
                if len(samples)%5==0: write_json(folder/'monitor-checkpoint.json',samples)
                if time.monotonic()-began>duration+90:
                    jm.terminate();jm.wait(timeout=15)
                    raise TimeoutError('JMeter exceeded bounded test time')
                time.sleep(2)
            settings['exit_code']=jm.returncode
        write_json(folder/'sql-digest.json',digest_delta(digest_before,sql_digest(db)))
    finally:
        stop_server(server,serverlog,ready['pid'])
    fields=sorted({k for r in samples for k in r})
    with (folder/'monitor.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(samples)
    checkpoint=folder/'monitor-checkpoint.json'
    if checkpoint.exists(): checkpoint.unlink()
    after=database_state(db)
    write_json(folder/'database-after.json',after)
    rows=list(csv.DictReader((folder/'raw.jtl').open(encoding='utf-8-sig',newline='')))
    if not rows: raise RuntimeError('No HTTP samples')
    start=min(int(r['timeStamp']) for r in rows)
    skip=0 if smoke else 70
    seconds=max(1,duration-2) if smoke else 300
    begin=start+skip*1000;end=begin+seconds*1000
    measured=[r for r in rows if r['label']==LABELS[key] and (smoke or begin<=int(r['timeStamp'])<end)]
    main=stats(measured)
    if not smoke: main['throughput_rps_fixed_window']=len(measured)/300
    coverage=[]
    if not smoke:
        for offset in range(0,300,30):
            chunk=[r for r in measured if begin+offset*1000<=int(r['timeStamp'])<begin+(offset+30)*1000]
            coverage.append({'offset_seconds':offset,'samples':len(chunk),'distinct_threads':len({r['threadName'] for r in chunk}),
                             'min_grp_threads':min((int(r.get('grpThreads') or 0) for r in chunk),default=0)})
    allstats={l:stats([r for r in rows if r['label']==l]) for l in dict.fromkeys(r['label'] for r in rows)}
    record={'scenario':key,'title':TITLES[key],'directory':str(folder),'settings':settings,'all_by_label':allstats,
            'all_failures':sum(r['success'].lower()!='true' for r in rows),'raw_http_samples':len(rows),
            'measurement':main,'window_start_ms':begin,'window_end_ms':end,'coverage_30seconds':coverage,
            'valid_fixed_load':bool(measured) and (smoke or all(r['distinct_threads']==users and r['min_grp_threads']==users for r in coverage)),
            'db_orders_created':after['orders_count']-before['orders_count'],
            'db_stock_consumed':before['test_product']['stock']-after['test_product']['stock']}
    successful_orders=sum(r['label']==LABELS['order'] and r['success'].lower()=='true' for r in rows)
    if key=='order':
        record['order_accounting_matches']=successful_orders==record['db_orders_created']==record['db_stock_consumed']
        record['end_test_cart_rows']=after['test_cart_rows']
    formal_monitor=[r for r in samples if begin<=r['epoch_ms']<end] if not smoke else samples
    record['resources']={k:{'mean':sum(float(r[k]) for r in formal_monitor if r.get(k) is not None)/len([r for r in formal_monitor if r.get(k) is not None]),
                            'max':max(float(r[k]) for r in formal_monitor if r.get(k) is not None)}
                         for k in fields if k not in ['epoch_ms','elapsed_seconds','monitor_error'] and any(r.get(k) is not None for r in formal_monitor)}
    with (folder/'measurement.jtl').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(measured)
    with (folder/'failures.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['timeStamp','label','threadName','responseCode','responseMessage','failureMessage'],extrasaction='ignore');w.writeheader()
        w.writerows(r for r in rows if r['success'].lower()!='true')
    write_json(folder/'result.json',record)
    return record

def requirements(folder):
    snippets=[]
    ppt=Path('D:/学习/综设3/课堂文件/安全电子商务系统III第一次课.pptx')
    with zipfile.ZipFile(ppt) as z:
        for name in sorted(n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)):
            root=E.fromstring(z.read(name))
            text='\n'.join(n.text or '' for n in root.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
            if any(k in text for k in ['第9周','P95','p95','20%','性能基线','性能优化']): snippets.append({'source':ppt.name,'slide':name,'text':text})
    doc=Path('D:/学习/综设3/课堂文件/安全电子商务系统III——第4-12周学生小组实施计划.docx')
    with zipfile.ZipFile(doc) as z:
        root=E.fromstring(z.read('word/document.xml'))
        text='\n'.join(''.join(n.text or '' for n in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')) for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
        snippets.append({'source':doc.name,'text':text})
    write_json(folder/'course-requirements.json',snippets)

def publish(folder):
    target=SOURCE/'完整测试结果-20261105-013809'
    staging=SOURCE/('新测试结果-'+STAMP)
    previous=SOURCE/('旧测试结果待替换-'+STAMP)
    if target.parent.resolve()!=SOURCE.resolve() or staging.parent.resolve()!=SOURCE.resolve(): raise ValueError('Invalid publish path')
    shutil.copytree(folder,staging)
    for p in folder.rglob('*'):
        if p.is_file() and sha(p)!=sha(staging/p.relative_to(folder)): raise RuntimeError('Published file checksum mismatch')
    if target.exists(): target.rename(previous)
    staging.rename(target)
    if previous.exists():
        if previous.resolve().parent!=SOURCE.resolve() or not previous.name.startswith('旧测试结果待替换-'): raise ValueError('Unsafe previous output')
        shutil.rmtree(previous)
    return str(target)

def report(folder,state):
    lines=['# 第8、9周：现有系统性能测试报告','','本报告记录同一业务代码的性能基线及同条件复测，未修改业务代码，未开展性能优化。',
           '','测试对象：普通用户证书+密码登录、已登录商品列表查询、SM2+SM4-GCM加密加购物车后创建订单。',
           '','每场景9个独立账号，9秒升压，总时长390秒。以首个HTTP样本时间为锚点，跳过70秒，统计其后300秒内开始的业务请求，保留失败样本。固定等待：登录1000ms，查询500ms，加购物车与下单各500ms。线程代表虚拟用户，含等待时间，不等于同时处理9个HTTP请求。',
           '','相同代码以Flask原开发服务器、HTTPS、单进程多线程运行于127.0.0.1:24433；每轮恢复同一MySQL快照。测试端与服务端共用一台机器。PERF_TEST_MODE=1仅在测试子进程中启用，限流为登录10000次/300秒、普通接口6000次/60秒。原2333服务及原业务库未改动。',
           '','## 正式300秒结果','','| 轮次 | 场景 | 样本 | 平均ms | P95 ms | P99 ms | 错误率 | 请求/秒 | 固定负载有效 |',
           '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for r in state['runs']:
        m=r['measurement']
        lines.append(f"| {r['round']} | {r['title']} | {m['samples']} | {m.get('average_ms',0):.2f} | {m.get('p95_ms','-')} | {m.get('p99_ms','-')} | {m.get('error_percent',100):.3f}% | {m.get('throughput_rps_fixed_window',0):.2f} | {'是' if r['valid_fixed_load'] else '否'} |")
    lines += ['','P95/P99采用nearest-rank，按同一个请求标签分别计算。下单耗时是创建订单HTTP请求本身，包含服务端解密、业务处理、审计及响应加密，JMeter前后处理和固定等待不计入HTTP elapsed。吞吐量按业务样本数/300秒计算，不使用混合TOTAL；这是给定用户数和等待间隔下的观测速率，不是系统最大容量。',
              '','## 同代码重复性比较','','| 场景 | 初测P95 | 复测P95 | 变化 | 说明 |','|---|---:|---:|---:|---|']
    for key in LABELS:
        runs=[r for r in state['runs'] if r['scenario']==key]
        if len(runs)==2:
            a,b=[r['measurement'].get('p95_ms',0) for r in runs]
            lines.append(f"| {TITLES[key]} | {a}ms | {b}ms | {(b/a-1)*100 if a else 0:+.2f}% | 未改代码，仅描述同条件波动 |")
    lines += ['','## 资源监控与瓶颈证据','','每2秒记录后端和JMeter的进程CPU、工作集/私有内存、整机CPU/内存、测试库连接与锁等待。CPU同时提供单核100%口径和整机归一化口径。SQL摘要为performance_schema按测试库归属的每轮增量，不含SQL参数或凭据。',
              '','| 轮次/场景 | 后端CPU单核均值/峰值 | 后端私有内存峰值MB | 整机CPU均值/峰值 | DB锁等待峰值 |','|---|---:|---:|---:|---:|']
    for r in state['runs']:
        s=r['resources'];bc=s.get('backend_cpu_percent_one_core',{});sc=s.get('system_cpu_percent',{})
        lines.append(f"| {r['round']}/{r['scenario']} | {bc.get('mean',0):.1f}% / {bc.get('max',0):.1f}% | {s.get('backend_private_mb',{}).get('max',0):.1f} | {sc.get('mean',0):.1f}% / {sc.get('max',0):.1f}% | {s.get('db_lock_waits',{}).get('max',0):.0f} |")
    lines += ['','每轮sql-digest.json可定位累计耗时最高的标准化SQL；它与HTTP耗时范围不同，不能直接将二者相减归因。CPU、内存和SQL证据仅支持本负载下的分析。未达到饱和时不宣称已找到系统极限瓶颈。',
              '','## 业务正确性与数据隔离','']
    for r in state['runs']:
        if r['scenario']=='order': lines.append(f"- 第{r['round']}轮：全程创建订单{r['db_orders_created']}笔，库存减少{r['db_stock_consumed']}件，HTTP成功订单/数据库新增订单/库存扣减一致：{r.get('order_accounting_matches')}；结束时测试购物车行数{r.get('end_test_cart_rows')}。仅测试库发生这些写入，未调用支付。")
    lines += ['','- 各轮执行前恢复相同种子快照；测试账号购物车仅在种子副本中清空，原库不删除。证书密码只引用本地私密CSV，不复制到报告。',
              f"- 业务源文件测试前后SHA256一致：{state.get('business_source_unchanged')}。",f"- 原库测试前后关键计数/库存一致：{state.get('original_database_unchanged')}（如用户同时操作原系统，需要另外判断外部变更）。",
              '','## 第8、9周交付与限制','','已提供脚本、环境参数、监控、原始JTL、错误记录、数据库核验和同条件复测对比。性能测试数据部分可复现。',
              '','课程中的“优化代码/配置提交”及“P95改善≥20%或达标保持证明”不能由一次未修改代码的复测替代。按用户要求本次只测现有系统，没有产生优化提交；课程未给出本项目绝对P95/吞吐目标，报告不编造目标或承诺全部课程验收通过。错误率≤1%按各正式业务场景单独核对，最终是否满足课程的“保持证明”需要教师认可的目标。',
              '','默认安全限流仍为登录10次/300秒、普通接口60次/60秒，本报告负载使用测试模式；不能据此声称默认安全配置下有相同吞吐能力。Flask开发服务器与同机环境的结果也不能外推到生产部署。',
              '','## 复现与证据','','各round*/场景目录含plan-executed.jmx、settings.json、raw.jtl、measurement.jtl、measurement-html/index.html、monitor.csv、sql-digest.json、database-before/after.json、failures.csv和日志。settings.json记录实际命令和参数；脚本使用固定9行账号文件，原版JMX未覆盖。',
              '','首70秒及末尾余量仅从正式统计中按预设窗口排除，仍完整保存在raw.jtl。每30秒分段检查9个线程都在采样且grpThreads=9，见result.json。初测和复测同一代码、快照、资源配置和负载。',
              '','运行：在项目根目录使用venv Python执行 `-m performance.run_week89_existing`。新的执行会创建独立名称的临时测试库，不会清理原业务库。`--publish`用于经验证后替换D盘指定的旧报告目录。']
    text='\n'.join(lines)+'\n'
    (folder/'完整测试报告.md').write_text(text,encoding='utf-8')
    links=''.join(f'<li><a href="round{r["round"]}/{r["scenario"]}/measurement-html/index.html">第{r["round"]}轮 {r["title"]} JMeter报告</a></li>' for r in state['runs'])
    (folder/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>第8、9周性能测试结果</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:36px auto;padding:0 24px}pre{white-space:pre-wrap;background:#f4f6f8;padding:24px}a{color:#1765b5}</style><h1>现有系统性能测试结果</h1><ul>'+links+'</ul><p><a href="summary.json">完整JSON数据</a> · <a href="完整测试报告.md">Markdown报告</a></p><pre>'+html.escape(text)+'</pre></html>',encoding='utf-8')
    write_json(folder/'summary.json',state)

OWNED=set()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke-only',action='store_true')
    parser.add_argument('--publish',action='store_true')
    a=parser.parse_args()
    folder=ROOT/'performance/results'/('现有系统持续测试-'+STAMP)
    folder.mkdir()
    state={'stamp':STAMP,'result_directory':str(folder),'status':'preparing','runs':[],'permission':'test existing system only; no business code modifications'}
    def checkpoint(message):
        state['progress']=message;write_json(folder/'progress.json',state)
        print(datetime.now().isoformat(timespec='seconds')+' '+message,flush=True)
    before_code=code_manifest();write_json(folder/'business-source-before.json',before_code)
    requirements(folder)
    before_original=database_state(get_config().MYSQL_CONFIG['db'])
    write_json(folder/'original-database-before.json',before_original)
    seed='adb_perf_seed_'+STAMP;work='adb_perf_run_'+STAMP
    OWNED.update([seed,work])
    state['owned_test_databases']=[seed,work]
    checkpoint('Capturing existing database snapshot')
    db,definitions,data,version=source_capture()
    state['environment']={'python':sys.version,'mysql':version,'jmeter':'5.6.3','java':'JBR21.0.7','machine':machine_info(),
                          'original_database':db,'test_port':PORT,'server':'same Flask development server, one process, threaded, HTTPS',
                          'same_machine_client_server':True,'database_snapshot_rows':{k:len(v) for k,v in data.items()}}
    for name in OWNED:
        with connect() as c:
            with c.cursor() as s:
                s.execute('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s',(name,))
                if s.fetchone()[0]: raise RuntimeError('Unique test database already exists; refusing overwrite')
    create_database(seed,definitions,data)
    del data
    with connect(seed) as c:
        with c.cursor() as s:
            s.execute('DELETE FROM cart_items WHERE user_id IN (SELECT id FROM users WHERE username IN ('+','.join(['%s']*9)+'))',USERS)
    state['seed_state']=database_state(seed)
    if len(state['seed_state']['accounts'])!=9 or state['seed_state']['test_product']['stock']<5000: raise RuntimeError('Test fixtures insufficient')
    try:
        for key in ['query','order','login']:
            clone_seed(seed,work,definitions)
            checkpoint('Smoke '+key+' (1 user, 30 seconds including cold JVM/TLS initialization)')
            smoke=run_one(key,folder/('smoke-'+key),work,30,1,True)
            if smoke['all_failures'] or not smoke['measurement'].get('samples') or (key=='order' and not smoke['order_accounting_matches']):
                raise RuntimeError('Smoke failed: '+key)
        if not a.smoke_only:
            for repeat in [1,2]:
                (folder/f'round{repeat}').mkdir()
                for key in ['query','order','login']:
                    clone_seed(seed,work,definitions)
                    checkpoint(f'Round {repeat}/2 {key}: 390 seconds, 300-second formal window')
                    record=run_one(key,folder/f'round{repeat}'/key,work,390,9)
                    record['round']=repeat
                    state['runs'].append(record)
                    checkpoint(f'Completed round {repeat} {key}: '+json.dumps(record['measurement'],ensure_ascii=False))
                    if not record['valid_fixed_load']: raise RuntimeError('Load did not cover all formal windows; retain evidence')
                    if record['all_failures']: raise RuntimeError('Unexpected HTTP/business failures; retain and investigate')
                    if key=='order' and not record['order_accounting_matches']: raise RuntimeError('Order database accounting mismatch')
                    with (Path(record['directory'])/'report-console.txt').open('w',encoding='utf-8') as f:
                        out=subprocess.run([str(JAVA),'-Xmx1g','-jar',str(JMETER),'-g',str(Path(record['directory'])/'measurement.jtl'),'-o',str(Path(record['directory'])/'measurement-html'),'-j',str(Path(record['directory'])/'report-jmeter.log')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
                    if out.returncode: raise RuntimeError('HTML report generation failed')
        state['business_source_unchanged']=before_code==code_manifest()
        original_after=database_state(db)
        write_json(folder/'original-database-after.json',original_after)
        state['original_database_unchanged']=before_original==original_after
        if not state['business_source_unchanged']: raise RuntimeError('Business source changed during testing')
        state['status']='complete' if not a.smoke_only else 'smoke-complete'
    except Exception as exc:
        state['status']='failed';state['error']=str(exc)
        checkpoint('FAILED: '+str(exc))
        raise
    finally:
        for name in [work,seed]:
            try: drop_owned(name)
            except Exception as exc: state.setdefault('cleanup_errors',[]).append(type(exc).__name__)
        write_json(folder/'progress.json',state)
    checkpoint('COMPLETE '+str(folder))
    report(folder,state)
    manifest={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()}
    write_json(folder/'sha256-manifest.json',manifest)
    if a.publish and not a.smoke_only:
        destination=publish(folder)
        print('PUBLISHED '+destination,flush=True)

if __name__=='__main__':main()
