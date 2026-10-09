# Data Quality Rulebook — Health Data Science Lab

## 1. Purpose

This document defines the initial data quality rules for the synthetic health facility dataset used in this learning project.

## 2. Dataset

- **File:** `data/synthetic/health_facilities.csv`
- **Data type:** Synthetic training data
- **Unit of analysis:** Health facility record
- **Purpose:** Practice data validation and quality assessment.

## 3. Data Quality Rules

| Rule ID | Field | Rule | Expected result |
|---|---|---|---|
| DQ01 | FOSA_ID | Facility identifier must not be missing | Zero missing identifiers |
| DQ02 | FOSA_ID | Facility identifier should be unique | Zero duplicate identifiers |
| DQ03 | SOH | Negative stock must be flagged for investigation | All negative values flagged |
| DQ04 | Reporting | Reporting status must be recorded | Zero missing statuses |
| DQ05 | SOH | Stock on Hand must be recorded | Zero missing SOH values |
| DQ06 | FU | Frequency of Use must be either 0 or 1 in this exercise | No invalid values |
| DQ07 | Province | Province must be recorded | Zero missing provinces |
| DQ08 | District | District must be recorded | Zero missing districts |

## 4. Interpretation Rules

- A zero stock balance is not the same as missing stock data.
- A negative stock balance must be investigated, not automatically corrected.
- Missing values must be investigated before any imputation.
- Duplicate records must be investigated before removing any row.
- A reporting status of `No` is not automatically a data entry error; it may indicate non-reporting.

## 5. Validation Workflow

1. Preserve the original dataset.
2. Detect and document anomalies.
3. Investigate the cause of each anomaly.
4. Agree on corrective actions.
5. Validate the corrected dataset.
6. Document changes through Git commits.

## 6. Data Protection

This project uses synthetic data only. No confidential operational data, patient information, credentials or restricted Medexis exports should be uploaded to this public repository.

## 7. Status

Initial version — rules for training and demonstration purposes.
