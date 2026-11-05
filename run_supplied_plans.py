"""Run the three explicitly supplied real-project plans and retain full evidence."""
from collections import Counter
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path('D:/学习/综设3/89周-JMeter')
JAVA = Path('D:/PyCharm Community Edition 2023.3.1/jbr/bin/java.exe')
JMETER = Path('D:/Downloads/JMeter/apache-jmeter-5.6.3/bin/ApacheJMeter.jar')
STAMP = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
DEST = ROOT / 'performance/results' / ('项目测试结果-' + STAMP)
SCENARIOS = [('login', '登录性能测试', '01_普通用户登录'),
             ('query', '商品查询性能测试', '02_商品查询'),
             ('order', '下单性能测试', '03_创建订单')]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(rows):
    values = sorted(int(r['elapsed']) for r in rows)
    if not values:
        return {'samples': 0}
    failures = sum(r['success'].lower() != 'true' for r in rows)
    start = min(int(r['timeStamp']) for r in rows)
    end = max(int(r['timeStamp']) + int(r['elapsed']) for r in rows)
    seconds = (end - start) / 1000
    return {
        'samples': len(rows), 'failures': failures, 'error_percent': failures / len(rows) * 100,
        'response_codes': dict(Counter(r['responseCode'] for r in rows)),
        'average_ms': sum(values) / len(values), 'p50_ms': values[math.ceil(.5 * len(values))-1],
        'p95_ms': values[math.ceil(.95 * len(values))-1],
        'p99_ms': values[math.ceil(.99 * len(values))-1], 'min_ms': values[0], 'max_ms': values[-1],
        'observation_seconds': seconds, 'observed_throughput_rps': len(rows) / seconds if seconds else None,
        'observed_thread_names': len({r['threadName'] for r in rows}),
        'peak_group_threads_at_samples': max(int(r.get('grpThreads') or 0) for r in rows),
        'start_epoch_ms': start, 'end_epoch_ms': end,
    }


def run():
    DEST.mkdir(parents=True, exist_ok=False)
    summary = {'created_at_asia_shanghai': STAMP, 'directory': str(DEST), 'runs': [],
               'mode': 'saved plans, original request counts and pacing; no silent load changes',
               'p95_method': 'nearest-rank over all samples of the same request label, including failures',
               'report_scope': 'one execution per saved plan; no optimization comparison or 300-second window claimed'}
    (DEST/'execution-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    for key, title, measured in SCENARIOS:
        folder = DEST/key
        folder.mkdir()
        original = SOURCE/(title+'.jmx')
        source_copy = folder/'source-original.jmx'
        source_copy.write_bytes(original.read_bytes())
        xml = ET.parse(original)
        for listener in xml.findall('.//ResultCollector'):
            listener.set('enabled', 'false')
        snapshot = folder/'plan-executed.jmx'
        xml.write(snapshot, encoding='UTF-8', xml_declaration=True)
        run_log = folder/'jmeter.log'
        jtl = folder/'raw.jtl'
        command = [str(JAVA), '-Xms512m', '-Xmx1g', '-jar', str(JMETER),
                   '-n', '-t', str(snapshot), '-l', str(jtl), '-j', str(run_log),
                   '-Jjmeter.save.saveservice.output_format=csv',
                   '-Jjmeter.save.saveservice.timestamp_format=ms',
                   '-Jjmeter.save.saveservice.print_field_names=true',
                   '-Jjmeter.save.saveservice.response_data=false',
                   '-Jjmeter.save.saveservice.samplerData=false',
                   '-Jjmeter.save.saveservice.requestHeaders=false',
                   '-Jjmeter.save.saveservice.responseHeaders=false']
        record = {'scenario': key, 'title': title, 'measured_label': measured,
                  'source': str(original), 'source_sha256': digest(original),
                  'command': command, 'changes': ['disabled GUI listeners in executed copy only; CLI -l records all samples'],
                  'start_asia_shanghai': datetime.now(timezone(timedelta(hours=8))).isoformat()}
        print('START '+title, flush=True)
        began = time.monotonic()
        with (folder/'console.txt').open('w', encoding='utf-8') as console:
            process = subprocess.run(command, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
                                     timeout=480)
        record['process_exit_code'] = process.returncode
        record['process_wall_seconds'] = time.monotonic()-began
        record['source_unchanged'] = digest(original) == record['source_sha256']
        rows = []
        if jtl.exists():
            with jtl.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
        labels = list(dict.fromkeys(r['label'] for r in rows))
        record['by_label'] = {label: stats([r for r in rows if r['label'] == label]) for label in labels}
        record['all_samples'] = stats(rows)
        record['measured'] = record['by_label'].get(measured, {'samples': 0})
        with (folder/'failures.csv').open('w', encoding='utf-8-sig', newline='') as f:
            fields = ['timeStamp','label','threadName','responseCode','responseMessage','failureMessage']
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(r for r in rows if r['success'].lower() != 'true')
        if rows:
            with (folder/'report-console.txt').open('w', encoding='utf-8') as console:
                report = subprocess.run([str(JAVA), '-Xmx1g', '-jar', str(JMETER), '-g', str(jtl),
                                         '-o', str(folder/'html'), '-j', str(folder/'report.log')],
                                        cwd=ROOT, stdout=console, stderr=subprocess.STDOUT, timeout=120)
            record['html_report_generated'] = report.returncode == 0 and (folder/'html/index.html').is_file()
        summary['runs'].append(record)
        (folder/'summary.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        (DEST/'execution-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print('DONE '+title+' '+json.dumps(record['measured'], ensure_ascii=False), flush=True)
    print('RESULT_DIRECTORY '+str(DEST), flush=True)


if __name__ == '__main__':
    run()
