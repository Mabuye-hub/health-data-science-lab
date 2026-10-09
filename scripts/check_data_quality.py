#!/usr/bin/env python3
"""Health Data Quality Checker V3.

Reads a CSV dataset, reports rule-level findings, calculates a transparent
rule-based scorecard, and creates a correction-register template.
The input dataset is never modified.
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "synthetic" / "health_facilities.csv"
REQUIRED_COLUMNS = ["FOSA_ID", "Province", "District", "FOSA", "Reporting", "SOH", "FU"]

# Rule weights are explicit and editable. Score is a weighted compliance rate,
# not a clinical or programmatic outcome measure.
RULES = {
    "DQ01": {"name": "Missing FOSA_ID", "weight": 3, "severity": "CRITICAL"},
    "DQ02": {"name": "Duplicate FOSA_ID", "weight": 3, "severity": "ERROR"},
    "DQ03": {"name": "Negative SOH", "weight": 3, "severity": "ERROR"},
    "DQ04": {"name": "Missing Reporting", "weight": 2, "severity": "ERROR"},
    "DQ05": {"name": "Missing SOH", "weight": 2, "severity": "ERROR"},
    "DQ06": {"name": "Invalid FU", "weight": 2, "severity": "ERROR"},
    "DQ07": {"name": "Missing Province/District/FOSA", "weight": 1, "severity": "WARNING"},
    "DQ09": {"name": "Reporting No while FU=1", "weight": 1, "severity": "WARNING"},
    "DQ10": {"name": "Reporting Yes while FU=0", "weight": 1, "severity": "INFO"},
}
FINDING_FIELDS = [
    "row_number", "FOSA_ID", "rule_id", "severity", "field",
    "observed_value", "message", "recommended_action"
]
SEVERITY_ORDER = ["CRITICAL", "ERROR", "WARNING", "INFO"]


def clean(value):
    return (value or "").strip()


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def check_data_quality(data_file=DEFAULT_DATA, reports_dir=ROOT / "reports"):
    if not data_file.exists():
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    with data_file.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)

    missing_columns = [col for col in REQUIRED_COLUMNS if col not in columns]
    if missing_columns:
        raise ValueError(
            "Required column(s) missing from dataset: " + ", ".join(missing_columns)
        )

    findings = []

    def add(row_number, fosa_id, rule_id, field, value, message, action):
        rule = RULES[rule_id]
        findings.append({
            "row_number": row_number,
            "FOSA_ID": fosa_id,
            "rule_id": rule_id,
            "severity": rule["severity"],
            "field": field,
            "observed_value": value,
            "message": message,
            "recommended_action": action,
        })

    # Keep line numbers aligned with the CSV: header is line 1, first record line 2.
    id_rows = defaultdict(list)
    for idx, row in enumerate(rows, start=2):
        fid = clean(row.get("FOSA_ID"))
        if not fid:
            add(idx, "", "DQ01", "FOSA_ID", fid, "FOSA_ID is missing.",
                "Check the master facility list and restore the verified identifier.")
        else:
            id_rows[fid].append(idx)

        for field in ("Province", "District", "FOSA"):
            value = clean(row.get(field))
            if not value:
                add(idx, fid, "DQ07", field, value, f"{field} is missing.",
                    "Verify the facility master data and complete the field.")

        reporting_raw = clean(row.get("Reporting"))
        reporting = reporting_raw.upper()
        if not reporting:
            add(idx, fid, "DQ04", "Reporting", reporting_raw, "Reporting status is missing.",
                "Verify the reporting register and complete the status.")
        elif reporting not in ("YES", "NO"):
            add(idx, fid, "DQ04", "Reporting", reporting_raw,
                "Reporting must be Yes or No.", "Standardize the value using the approved code list.")

        soh_raw = clean(row.get("SOH"))
        soh = None
        if not soh_raw:
            add(idx, fid, "DQ05", "SOH", soh_raw, "SOH is missing; missing is not equivalent to zero.",
                "Check the stock record or extraction. Do not replace missing with zero without evidence.")
        else:
            try:
                soh = float(soh_raw.replace(",", "."))
            except ValueError:
                add(idx, fid, "DQ05", "SOH", soh_raw, "SOH is not numeric.",
                    "Verify the source value and expected unit of measure.")
            else:
                if soh < 0:
                    add(idx, fid, "DQ03", "SOH", soh_raw, "SOH is negative.",
                        "Reconcile stock movements, adjustments, units and transaction dates.")

        fu_raw = clean(row.get("FU"))
        fu = None
        if not fu_raw:
            add(idx, fid, "DQ06", "FU", fu_raw, "FU is missing.",
                "Verify the approved Frequency of Use definition and reporting period.")
        else:
            try:
                fu_num = float(fu_raw)
                if fu_num not in (0, 1):
                    raise ValueError
                fu = int(fu_num)
            except ValueError:
                add(idx, fid, "DQ06", "FU", fu_raw, "FU must be 0 or 1.",
                    "Verify the extraction and approved FU definition.")

        if reporting in ("YES", "NO") and fu is not None:
            if reporting == "NO" and fu == 1:
                add(idx, fid, "DQ09", "Reporting/FU", f"{reporting_raw}/{fu}",
                    "Reporting is No while FU equals 1.",
                    "Reconcile the definitions and reporting period.")
            elif reporting == "YES" and fu == 0:
                add(idx, fid, "DQ10", "Reporting/FU", f"{reporting_raw}/{fu}",
                    "Reporting is Yes while FU equals 0.",
                    "Check whether the reported activity qualifies as system use.")

    # Flag each row involved in a duplicate ID group, preserving traceability.
    for fid, line_numbers in id_rows.items():
        if len(line_numbers) > 1:
            for line in line_numbers:
                add(line, fid, "DQ02", "FOSA_ID", fid,
                    f"Duplicate FOSA_ID occurs {len(line_numbers)} times on CSV lines {line_numbers}.",
                    "Compare with the master list; confirm the duplicate before correcting. Do not auto-delete.")

    # Rule scorecard: for each rule, count eligible rows and rows with a finding.
    # A row with an issue can trigger more than one finding; each rule is scored independently.
    findings_by_rule_row = defaultdict(set)
    for finding in findings:
        findings_by_rule_row[finding["rule_id"]].add(finding["row_number"])

    scorecard = []
    weighted_points = 0.0
    total_weight = 0.0
    for rule_id, rule in RULES.items():
        eligible = len(rows)
        failed_rows = len(findings_by_rule_row[rule_id])
        passed_rows = max(0, eligible - failed_rows)
        compliance = (passed_rows / eligible * 100.0) if eligible else 100.0
        weight = rule["weight"]
        weighted_points += compliance * weight
        total_weight += weight
        scorecard.append({
            "rule_id": rule_id,
            "rule_name": rule["name"],
            "severity": rule["severity"],
            "eligible_records": eligible,
            "records_with_findings": failed_rows,
            "records_without_findings": passed_rows,
            "compliance_percent": f"{compliance:.1f}",
            "weight": weight,
        })
    score = (weighted_points / total_weight) if total_weight else 100.0

    reports_dir.mkdir(parents=True, exist_ok=True)
    write_csv(reports_dir / "quality_report.csv", findings, FINDING_FIELDS)
    write_csv(reports_dir / "quality_scorecard.csv", scorecard, [
        "rule_id", "rule_name", "severity", "eligible_records",
        "records_with_findings", "records_without_findings",
        "compliance_percent", "weight"
    ])

    # A fresh template is created only if one does not already exist, to avoid
    # overwriting a user's correction tracking.
    register_path = reports_dir / "correction_register_template.csv"
    if not register_path.exists():
        template_fields = [
            "finding_id", "row_number", "FOSA_ID", "rule_id", "severity",
            "problem", "recommended_action", "responsible_person",
            "target_date", "status", "resolution_notes", "verification_date"
        ]
        template_rows = []
        for i, finding in enumerate(findings, start=1):
            template_rows.append({
                "finding_id": f"F-{i:04d}",
                "row_number": finding["row_number"],
                "FOSA_ID": finding["FOSA_ID"],
                "rule_id": finding["rule_id"],
                "severity": finding["severity"],
                "problem": finding["message"],
                "recommended_action": finding["recommended_action"],
                "responsible_person": "",
                "target_date": "",
                "status": "Open",
                "resolution_notes": "",
                "verification_date": "",
            })
        write_csv(register_path, template_rows, template_fields)

    counts = Counter(f["severity"] for f in findings)
    rule_counts = Counter(f["rule_id"] for f in findings)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = [
        "# Health Data Quality Report — Version 3",
        "",
        f"- Run timestamp: **{timestamp}**",
        f"- Dataset: `{data_file.name}`",
        f"- Records analysed: **{len(rows)}**",
        f"- Total findings (row-rule instances): **{len(findings)}**",
        f"- Weighted rule-based quality score: **{score:.1f}/100**",
        "- Score interpretation: weighted compliance across configured rules; not a measure of health-service performance.",
        "",
        "## Findings by severity",
        "",
        "| Severity | Findings |",
        "|---|---:|",
    ]
    for severity in SEVERITY_ORDER:
        summary.append(f"| {severity} | {counts[severity]} |")
    summary += ["", "## Findings by rule", "", "| Rule | Rule name | Findings |", "|---|---|---:|"]
    for rule_id, rule in RULES.items():
        summary.append(f"| {rule_id} | {rule['name']} | {rule_counts[rule_id]} |")
    summary += [
        "",
        "## Scorecard",
        "",
        "| Rule | Compliance | Weight |",
        "|---|---:|---:|",
    ]
    for item in scorecard:
        summary.append(f"| {item['rule_id']} — {item['rule_name']} | {item['compliance_percent']}% | {item['weight']} |")
    summary += [
        "",
        "## Interpretation and safeguards",
        "",
        "- The score uses the documented weights in `scripts/check_data_quality.py`; revise and approve them before operational use.",
        "- Missing SOH is not equivalent to zero.",
        "- Duplicate IDs are flagged for investigation; records are not automatically deleted.",
        "- The source dataset was not modified.",
        "- See `quality_report.csv` for row-level findings, `quality_scorecard.csv` for rule performance, and `correction_register_template.csv` for follow-up.",
        "",
    ]
    (reports_dir / "quality_summary.md").write_text("\n".join(summary), encoding="utf-8")

    return findings, len(rows), counts, score


def main():
    parser = argparse.ArgumentParser(description="Health Data Science Lab quality checks V3")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Path to input CSV")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports", help="Output directory")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if critical findings or errors are found")
    args = parser.parse_args()

    findings, total, counts, score = check_data_quality(args.data, args.reports_dir)
    print("=" * 55)
    print("HEALTH DATA QUALITY REPORT — VERSION 3")
    print(f"Records analysed: {total}")
    print(f"Total findings: {len(findings)}")
    print(f"Weighted rule-based quality score: {score:.1f}/100")
    for level in SEVERITY_ORDER:
        print(f"{level}: {counts[level]}")
    print(f"Reports saved in: {args.reports_dir}")
    print("Source dataset was not modified.")
    if args.strict and (counts["CRITICAL"] or counts["ERROR"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
