"""Extract a fixed measurement window from JMeter CSV JTL without hiding failures."""
import argparse
import csv
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--label', required=True, help='Exact HTTP sampler name')
    parser.add_argument('--skip-seconds', type=float, default=70)
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.seconds <= 0 or args.skip_seconds < 0:
        parser.error('seconds must be positive; skip-seconds must be nonnegative')
    if args.input.resolve() == args.output.resolve():
        parser.error('output must differ from the original JTL')
    if args.output.exists() or args.output.with_suffix('.summary.json').exists():
        parser.error('output already exists; choose a new path to preserve previous evidence')
    with args.input.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        required = {'timeStamp', 'elapsed', 'label', 'success', 'threadName'}
        if not fields or not required.issubset(fields):
            parser.error('expected JMeter CSV JTL with timestamp in epoch milliseconds')
        rows = list(reader)
    if not rows:
        parser.error('input contains no samples')
    run_start = min(int(row['timeStamp']) for row in rows)
    begin = run_start + round(args.skip_seconds * 1000)
    end = begin + round(args.seconds * 1000)
    selected = [row for row in rows if row['label'] == args.label
                and begin <= int(row['timeStamp']) < end]
    if not selected:
        parser.error('no matching samples in the requested window')
    ordered = sorted(int(row['elapsed']) for row in selected)
    failures = sum(row['success'].lower() != 'true' for row in selected)
    warnings = []
    label_rows = [row for row in rows if row['label'] == args.label]
    last_completion = max(int(row['timeStamp']) + int(row['elapsed']) for row in label_rows)
    if last_completion < end:
        warnings.append('This sampler did not cover the window end; inspect early thread exits or missing load.')
    summary = {
        'label': args.label, 'window_start_epoch_ms': begin,
        'window_end_epoch_ms': end, 'window_seconds': args.seconds,
        'selection': 'request start timestamp in [window_start, window_end)',
        'samples': len(selected), 'failures': failures,
        'error_rate_percent': failures / len(selected) * 100,
        'http_429_count': sum(row.get('responseCode') == '429' for row in selected),
        'throughput_requests_per_second': len(selected) / args.seconds,
        'p95_ms': ordered[math.ceil(0.95 * len(ordered)) - 1],
        'p95_method': 'nearest-rank; includes successful and failed HTTP samples',
        'observed_thread_names': len({row['threadName'] for row in selected}),
        'warnings': warnings,
        'note': 'Observed thread count does not prove stable concurrency; inspect JTL thread columns and active thread graph.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    args.output.with_suffix('.summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
