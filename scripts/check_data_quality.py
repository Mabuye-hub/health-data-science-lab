
import csv
from collections import Counter
from pathlib import Path

# Chemin du fichier CSV, relatif à la racine du projet
DATA_FILE = Path("data/synthetic/health_facilities.csv")


def check_data_quality():
    """Detect basic data quality issues in the synthetic health dataset."""

    if not DATA_FILE.exists():
        print(f"ERROR: Dataset not found: {DATA_FILE}")
        print("Run this script from the repository root.")
        return

    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    print("=" * 55)
    print("HEALTH DATA QUALITY REPORT")
    print("=" * 55)
    print(f"Total records: {len(rows)}")

    # DQ01: Missing facility identifiers
    missing_ids = [
        i for i, row in enumerate(rows, start=2)
        if not row.get("FOSA_ID", "").strip()
    ]
    print(f"\nDQ01 - Missing FOSA_ID: {len(missing_ids)}")

    # DQ02: Duplicate facility identifiers
    ids = [
        row["FOSA_ID"].strip()
        for row in rows
        if row.get("FOSA_ID", "").strip()
    ]
    duplicate_ids = sorted(
        identifier
        for identifier, count in Counter(ids).items()
        if count > 1
    )
    print(f"DQ02 - Duplicate FOSA_ID values: {duplicate_ids}")

    # DQ03: Negative stock on hand
    negative_stock = [
        (row.get("FOSA_ID", ""), row.get("SOH", ""))
        for row in rows
        if row.get("SOH", "").strip()
        and float(row["SOH"]) < 0
    ]
    print(f"DQ03 - Negative SOH records: {negative_stock}")

    # DQ04: Missing reporting status
    missing_reporting = [
        row.get("FOSA_ID", "")
        for row in rows
        if not row.get("Reporting", "").strip()
    ]
    print(f"DQ04 - Missing reporting status: {missing_reporting}")

    # DQ05: Missing SOH
    missing_soh = [
        row.get("FOSA_ID", "")
        for row in rows
        if not row.get("SOH", "").strip()
    ]
    print(f"DQ05 - Missing SOH: {missing_soh}")

    # DQ06: FU must be 0 or 1 in this exercise
    invalid_fu = [
        (row.get("FOSA_ID", ""), row.get("FU", ""))
        for row in rows
        if row.get("FU", "").strip() not in {"0", "1"}
    ]
    print(f"DQ06 - Invalid FU values: {invalid_fu}")

    print("\nNote: The original dataset has not been modified.")


if __name__ == "__main__":
    check_data_quality()
