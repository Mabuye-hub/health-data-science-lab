import csv
import argparse
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / 'data' / 'synthetic' / 'health_facilities.csv'
REQUIRED = ['FOSA_ID', 'Province', 'District', 'FOSA', 'Reporting', 'SOH', 'FU']


def check_data_quality(data_file=DEFAULT_DATA, reports_dir=ROOT / 'reports'):
    findings = []
    def add(line, fid, rule, severity, field, value, message, action):
        findings.append({'row_number': line, 'FOSA_ID': fid, 'rule_id': rule,
                         'severity': severity, 'field': field, 'observed_value': value,
                         'message': message, 'recommended_action': action})

    if not data_file.exists():
        raise FileNotFoundError(f'Dataset not found: {data_file}')

    with data_file.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        missing_columns = [c for c in REQUIRED if c not in columns]
        if missing_columns:
            for col in missing_columns:
                add('', '', 'DQ00', 'CRITICAL', col, '', f'Required column {col} is missing.',
                    'Restore the expected column or update the data dictionary.')
            rows = []
        else:
            rows = list(reader)

    ids = defaultdict(list)
    for line, row in enumerate(rows, start=2):
        fid = (row.get('FOSA_ID') or '').strip()
        reporting = (row.get('Reporting') or '').strip().upper()
        soh_raw = (row.get('SOH') or '').strip()
        fu_raw = (row.get('FU') or '').strip()
        for field in ('Province', 'District', 'FOSA'):
            if not (row.get(field) or '').strip():
                add(line, fid, 'DQ07', 'WARNING', field, '', f'{field} is blank.',
                    f'Complete {field} from the validated facility reference list.')
        if not fid:
            add(line, fid, 'DQ01', 'ERROR', 'FOSA_ID', '', 'Facility ID is missing.',
                'Verify the facility against the official master list.')
        else:
            ids[fid].append(line)
        if reporting not in {'YES', 'NO'}:
            add(line, fid, 'DQ04', 'ERROR', 'Reporting', reporting,
                'Reporting must be Yes or No.', 'Verify and standardize the source value.')
        soh = None
        if not soh_raw:
            add(line, fid, 'DQ05', 'WARNING', 'SOH', '', 'SOH is missing.',
                'Verify the stock record; do not confuse missing data with zero.')
        else:
            try:
                soh = float(soh_raw)
                if soh < 0:
                    add(line, fid, 'DQ03', 'ERROR', 'SOH', soh_raw, 'Negative SOH detected.',
                        'Investigate stock movements, adjustments and units.')
            except ValueError:
                add(line, fid, 'DQ08', 'ERROR', 'SOH', soh_raw, 'SOH is not numeric.',
                    'Verify and correct from the source record.')
        fu = None
        if not fu_raw:
            add(line, fid, 'DQ06', 'ERROR', 'FU', '', 'FU is missing.',
                'Recalculate FU according to the approved indicator definition.')
        else:
            try:
                fu = int(fu_raw)
                if fu not in (0, 1):
                    raise ValueError
            except ValueError:
                fu = None
                add(line, fid, 'DQ06', 'ERROR', 'FU', fu_raw, 'FU must be 0 or 1.',
                    'Verify the extraction and approved FU definition.')
        if reporting == 'NO' and fu == 1:
            add(line, fid, 'DQ09', 'WARNING', 'Reporting/FU', f'{reporting}/{fu}',
                'Reporting is No while FU equals 1.', 'Reconcile definitions and reporting period.')
        if reporting == 'YES' and fu == 0:
            add(line, fid, 'DQ10', 'INFO', 'Reporting/FU', f'{reporting}/{fu}',
                'Reporting is Yes while FU equals 0.', 'Verify whether reported activity qualifies as system use.')

    for fid, lines in ids.items():
        if len(lines) > 1:
            for line in lines:
                add(line, fid, 'DQ02', 'ERROR', 'FOSA_ID', fid,
                    f'Duplicate ID occurs {len(lines)} times on CSV lines {lines}.',
                    'Investigate against the master list; do not automatically delete records.')

    reports_dir.mkdir(parents=True, exist_ok=True)
    fields = ['row_number', 'FOSA_ID', 'rule_id', 'severity', 'field', 'observed_value', 'message', 'recommended_action']
    with (reports_dir / 'quality_report.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(findings)

    counts = Counter(x['severity'] for x in findings)
    summary = ['# Health Data Quality Report — Version 2', '',
               f'- Records analysed: **{len(rows)}**', f'- Total findings: **{len(findings)}**',
               f'- Critical: **{counts["CRITICAL"]}**', f'- Errors: **{counts["ERROR"]}**',
               f'- Warnings: **{counts["WARNING"]}**', f'- Informational: **{counts["INFO"]}**', '',
               '## Findings by rule', '', '| Rule | Findings |', '|---|---:|']
    rule_counts = Counter(x['rule_id'] for x in findings)
    summary += [f'| {rule} | {count} |' for rule, count in sorted(rule_counts.items())] or ['| None | 0 |']
    summary += ['', 'The source dataset was not modified.',
                'Missing SOH is different from zero. Investigate negative stock and duplicates before correction.',
                'See `quality_report.csv` for row-level findings and recommended actions.']
    (reports_dir / 'quality_summary.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    return findings, len(rows), counts


def main():
    parser = argparse.ArgumentParser(description='Health Data Science Lab quality checks V2')
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--reports-dir', type=Path, default=ROOT / 'reports')
    parser.add_argument('--strict', action='store_true', help='Exit 1 if critical errors or errors are found')
    args = parser.parse_args()
    findings, total, counts = check_data_quality(args.data, args.reports_dir)
    print('=' * 50)
    print('HEALTH DATA QUALITY REPORT — VERSION 2')
    print(f'Records analysed: {total}')
    print(f'Total findings: {len(findings)}')
    for level in ('CRITICAL', 'ERROR', 'WARNING', 'INFO'):
        print(f'{level}: {counts[level]}')
    print(f'Reports saved in: {args.reports_dir}')
    print('Source dataset was not modified.')
    if args.strict and (counts['CRITICAL'] or counts['ERROR']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
