"""Package all repeated real runs into a Chinese report with traceable evidence."""
import argparse
import csv
from datetime import datetime, timezone, timedelta
import html
import json
from pathlib import Path
import shutil
import statistics
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('rounds', nargs=3, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    out = root/'results'/('完整测试结果-'+stamp)
    out.mkdir()
    data = []
    for n, directory in enumerate(args.rounds, 1):
        shutil.copytree(directory, out/f'round{n}')
        summary = json.loads((directory/'execution-summary.json').read_text(encoding='utf-8'))
        assert len(summary['runs']) == 3
        data.append(summary)
    # Original files are snapshots; results do not include passwords or CSV credentials.
    tables = []
    summaries = {}
    for key, title in [('login','登录'),('query','商品查询'),('order','下单')]:
        runs = [next(r for r in s['runs'] if r['scenario']==key) for s in data]
        assert all(r['source_unchanged'] for r in runs)
        assert len({r['source_sha256'] for r in runs}) == 1
        summaries[key] = {
            'title': title, 'samples': sum(r['measured']['samples'] for r in runs),
            'failures': sum(r['measured']['failures'] for r in runs),
            'median_round_p95_ms': statistics.median(r['measured']['p95_ms'] for r in runs),
            'p95_range_ms': [min(r['measured']['p95_ms'] for r in runs),max(r['measured']['p95_ms'] for r in runs)],
            'rounds': [r['measured'] for r in runs],
        }
        for i,r in enumerate(runs,1):
            s = r['measured']
            tables.append([title, str(i), '9', str(s['samples']), f"{s['average_ms']:.2f}",
                           str(s['p95_ms']), str(s['p99_ms']), f"{s['error_percent']:.2f}%",
                           f"{s['observed_throughput_rps']:.2f}", f"{s['observation_seconds']:.3f}",
                           str(s['peak_group_threads_at_samples'])])
    total = sum(r['all_samples']['samples'] for s in data for r in s['runs'])
    errors = sum(r['all_samples']['failures'] for s in data for r in s['runs'])
    html_ok = all(r.get('html_report_generated') for s in data for r in s['runs'])
    database_file = root/'results'/'final-database-verification.json'
    db = json.loads(database_file.read_text(encoding='utf-8')) if database_file.exists() else {}
    if database_file.exists(): shutil.copyfile(database_file,out/'database-verification.json')
    if (args.rounds[0]/'environment.json').exists():
        shutil.copyfile(args.rounds[0]/'environment.json',out/'environment.json')
    all_summary = {'p95_method':'nearest-rank, per label, including failed samples',
                   'all_http_samples':total,'all_http_failures':errors,
                   'all_html_reports_generated':html_ok,'scenarios':summaries,'database':db}
    (out/'summary.json').write_text(json.dumps(all_summary,ensure_ascii=False,indent=2),encoding='utf-8')
    headers = ['接口','轮次','配置线程数','业务样本数','平均ms','p95 ms','p99 ms','错误率','短时吞吐req/s','业务观测秒数','业务样本处峰值活动线程']
    with (out/'results-summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(headers);writer.writerows(tables)
    report = [
        '# 安全电子商务系统三项测试结果', '',
        '已对用户提供的登录、商品查询、下单三份JMX各执行三轮真实项目测试。请求均发送到本机HTTPS后端及其MySQL数据库，不是模拟测试。', '',
        f'共记录{total}个HTTP样本，失败{errors}个，全部请求错误率为{errors/total*100:.2f}%；9份JMeter HTML报告均已生成：{html_ok}。', '',
        '**结论：三类接口在本次短时、按次数测试中均通过业务断言。当前文件没有持续300秒的业务采样，不能据此宣布容量上限、长期稳定性或已完成第8/9周的优化验收。**', '',
        '## 执行范围与配置', '',
        '- 每轮使用9个不同普通用户；CSV中的证书和密码仅在本机读取，没有复制到结果包。',
        '- 登录场景：9线程、9秒升压，每用户登录1次，含密码、证书、Token和普通用户角色校验。',
        '- 商品查询场景：9线程、1秒升压，每用户先登录1次，再查询商品列表100次；未带商品ID过滤条件，查询当前在售商品列表。',
        '- 下单场景：9线程、9秒升压，每用户登录、取公钥、检查空购物车各1次，再加商品3一件并创建1个订单；不包含支付。',
        '- 登录与下单配置的390秒是最长上限，内部循环为1，实际完成后提前退出。商品查询计划里另有一个空Loop Controller，不产生请求。',
        '- 保留原JMX的请求、断言、定时器、循环、线程数和CSV；只在执行副本中禁用可视化监听器，使用CLI -l记录全部样本。原文件哈希三轮一致。',
        '- 每份计划分别启动Java21/JMeter进程。使用同机127.0.0.1回环HTTPS；结果包含连接、TLS及服务端处理开销。客户端加密前处理和响应解密后处理不计入HTTP Sampler耗时。',
        '- 后端使用现有Flask启动方式；没有在本次测试中修改业务代码、数据库索引、缓存或性能参数。连续登录和查询均未出现429。', '',
        '## 各轮被测接口结果', '',
        '以下只取各场景的实际被测接口行，不混用TOTAL。商品查询场景中的初始化登录、下单场景中的准备请求在原始数据与HTML中另行保留。', '',
        '| '+' | '.join(headers)+' |', '|'+ '|'.join(['---']*len(headers))+'|']
    report.extend('| '+' | '.join(row)+' |' for row in tables)
    report += ['', '## 三轮汇总', '', '| 接口 | 三轮业务样本总数 | 业务失败数 | 三轮p95中位数ms | 各轮p95范围ms |', '|---|---:|---:|---:|---|']
    for s in summaries.values():
        report.append(f"| {s['title']} | {s['samples']} | {s['failures']} | {s['median_round_p95_ms']} | {s['p95_range_ms'][0]}～{s['p95_range_ms'][1]} |")
    report += ['', '这里的p95中位数是三轮各自p95的中位数，不是把三轮样本合并后重新计算的p95。', '',
        '## 连接耗时和解释限制', '',
        '首轮独立登录场景最慢样本为8479毫秒，其中Connect为8226毫秒，连接阶段占约97%。这是实测连接建立开销，不能把全部耗时归因于密码/证书认证代码。原始Connect、Latency、elapsed均保留在JTL中。',
        '吞吐量按同一请求标签的首个请求开始到最后一个请求结束计算，包含该标签中的升压或空闲间隔。下单只有9次短时请求，观测窗口很短，瞬时吞吐值不代表可持续容量。',
        '配置线程数为9不保证整个窗口始终有9个活动线程；应结合表内采样时峰值和HTML线程曲线。当前每用户次数很少，线程完成后立即退出。', '',
        '三轮之间未恢复数据库快照，订单累计增加、库存随实际下单减少；三轮用于重复执行观察，不标称为严格相同数据初态下的性能基线。', '',
        '## 数据库核对与真实影响', '']
    if db:
        report += [f"- 测试前订单数{db['before']['order_count']}，测试后订单数{db['after']['order_totals']['order_count']}。",
                   f"- 新增订单{len(db['after']['new_orders'])}个，ID范围{db['after']['new_orders'][0]['id']}～{db['after']['new_orders'][-1]['id']}。",
                   f"- 商品3库存从{db['before']['product_3_stock']}变为{db['after']['product']['stock']}，减少{db['before']['product_3_stock']-db['after']['product']['stock']}件。",
                   '- 订单商品、数量与金额已按数据库明细核对；测试后9个账号购物车均为空。',
                   '- 订单状态为pending，未支付。没有删除测试订单、回补库存或清空用户原有购物车；具体订单记录见database-verification.json。']
    report += ['', '## 原始证据位置', '',
        '每轮round1～round3下分别有login、query、order目录：', '',
        '- source-original.jmx：用户原文件快照。',
        '- plan-executed.jmx：实际执行副本。',
        '- raw.jtl：所有原始请求，含状态码、成功标记、断言信息、耗时、连接时间、活动线程计数。',
        '- summary.json：该场景各请求标签统计及实际命令、哈希。',
        '- failures.csv：失败请求清单；本次为空表。',
        '- jmeter.log、console.txt：执行日志。',
        '- html/index.html：JMeter完整报告。', '',
        '## 对第8和第9周任务的覆盖', '',
        '| 要求 | 本次覆盖情况 |', '|---|---|',
        '| 三个接口可复现脚本和原始证据 | 已提供，三类场景各三轮 |',
        '| 并发数、吞吐量、p95、错误率 | 已记录当前短时配置下的观测值 |',
        '| 环境说明 | 已记录版本、同机部署方式、配置和代码快照哈希 |',
        '| 持续负载、固定300秒窗口 | 未执行；本次尊重用户保存的按次数配置 |',
        '| 连续CPU、内存和数据库等待监控 | 未完整采集，不以单个进程快照代替监控曲线 |',
        '| 瓶颈优化、前后同条件对比 | 未执行，不能声称p95下降20% |',
        '| 已有指标稳定达标的保持证明 | 本次没有课程认可的目标值与持续负载证据，不能单凭0%错误率认定 |', '',
        '后续应冻结场景、数据及节奏，执行充分预热和300秒持续测量并采集服务端监控，然后实施有证据的优化，以同条件复测计算p95降幅。', '',
        '## 统计方法', '',
        'p95采用nearest-rank：排序后取ceil(0.95×样本数)位置。失败样本也保留；错误率为失败样本数/总样本数。JMeter HTML可能使用不同百分位估计，前后比较统一以summary.json中的方法为准。',
        '全量HTTP样本包含准备请求，因此总量大于表中三个业务接口样本之和。JTL、报告和汇总中都没有伪造或补齐样本。', '']
    (out/'完整测试报告.md').write_text('\n'.join(report),encoding='utf-8')
    links=[]
    for i in range(1,4):
        for key,title in [('login','登录'),('query','商品查询'),('order','下单')]:
            links.append(f'<li><a href="round{i}/{key}/html/index.html">第{i}轮 {title} HTML报告</a></li>')
    head=['接口','轮次','配置线程','样本','平均ms','p95 ms','p99 ms','错误率','短时吞吐req/s','观测秒数','采样峰值线程']
    html_table='<tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in head)+'</tr>'
    html_table+=''.join('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in row)+'</tr>' for row in tables)
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>三项测试结果</title>
<style>body{{font:16px/1.7 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#172033}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #cbd2dc;padding:8px;text-align:right}}th{{background:#eef2f7}}td:first-child{{text-align:left}}a{{color:#155fc4}}</style>
<h1>三项测试结果</h1><p>真实后端，每场景三轮。总HTTP样本{total}，失败{errors}。短时按次数测试，不能据此认定持续容量或优化验收完成。</p>
<table>{html_table}</table><p>详细解释、数据库影响及验收覆盖见<a href="完整测试报告.md">完整测试报告</a>；机器可读数据见<a href="summary.json">summary.json</a>。</p><h2>各轮完整报告</h2><ul>{''.join(links)}</ul></html>'''
    (out/'index.html').write_text(page,encoding='utf-8')
    print(out)


if __name__=='__main__': main()
