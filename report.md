# 📦 Upgrade Impact Analysis Report

**Total Dependencies Analyzed:** 5

## 📊 Summary

| Package | Current | Target | Risk Score | Severity | Issues |
|---------|---------|--------|------------|----------|--------|
| **packaging** | 24.0 | 25.0 | 72.0/100 | 🟠 high | 1 |
| **griffe** | 0.42.0 | 1.15.0 | 64.0/100 | 🟠 high | 1 |
| **httpx** | 0.27.0 | 0.28.1 | 53.5/100 | 🟡 medium | 1 |
| **rich** | 13.7.0 | 14.2.0 | 30.0/100 | 🟡 medium | 0 |
| **typer** | 0.12.0 | 0.21.1 | 20.6/100 | 🟢 low | 0 |

## 🟠 High Risk Upgrades

### packaging: `24.0` → `25.0`

**Risk Score:** 72.0/100 (🟠 high)

**Risk Factors:**

- **SemVer Distance**: `████████████████░░░░` 80.0/100 (weight: 30%)
  - Version jump from 24.0 to 25.0
- **Usage Impact**: `████████████████░░░░` 80.0/100 (weight: 50%)
  - 1 API changes affecting 8 usage points
- **Changelog Severity**: `████████░░░░░░░░░░░░` 40.0/100 (weight: 20%)
  - Based on 3 changelog entries

**⚠️  Breaking Changes Detected:** 1

1. **`packaging.specifiers.SpecifierSet`** - Signature changed for 'packaging.specifiers.SpecifierSet'
   - Affects 0 usage(s) across 1 file(s)
   - Affected files: `requirements.py`

**💡 Recommendation:**

- High risk detected. Recommend incremental upgrade to minimize compatibility issues.
- **Estimated Effort:** High
- **Suggested Upgrade Path:** `24.1` → `24.2` → `25.0`

**Usage Summary:**

- Files using this package: 4
- Unique symbols imported: 5
- Total function calls: 16

---

### griffe: `0.42.0` → `1.15.0`

**Risk Score:** 64.0/100 (🟠 high)

**Risk Factors:**

- **SemVer Distance**: `████████████████░░░░` 80.0/100 (weight: 30%)
  - Version jump from 0.42.0 to 1.15.0
- **Usage Impact**: `████████████████░░░░` 80.0/100 (weight: 50%)
  - 1 API changes affecting 1 usage points
- **Changelog Severity**: `░░░░░░░░░░░░░░░░░░░░` 0.0/100 (weight: 20%)
  - Based on 1 changelog entries

**⚠️  Breaking Changes Detected:** 1

1. **`griffe`** - Signature changed for 'griffe'
   - Affects 0 usage(s) across 1 file(s)
   - Affected files: `api_differ.py`

**💡 Recommendation:**

- High risk detected. Recommend incremental upgrade to minimize compatibility issues.
- **Estimated Effort:** High
- **Suggested Upgrade Path:** `1.0.0` → `1.15.0`

**Usage Summary:**

- Files using this package: 1
- Unique symbols imported: 1
- Total function calls: 0

---

## 🟡 Medium Risk Upgrades

### httpx: `0.27.0` → `0.28.1`

**Risk Score:** 53.5/100 (🟡 medium)

**Risk Factors:**

- **SemVer Distance**: `█████████░░░░░░░░░░░` 45.0/100 (weight: 30%)
  - Version jump from 0.27.0 to 0.28.1
- **Usage Impact**: `████████████████░░░░` 80.0/100 (weight: 50%)
  - 1 API changes affecting 6 usage points
- **Changelog Severity**: `░░░░░░░░░░░░░░░░░░░░` 0.0/100 (weight: 20%)
  - Based on 1 changelog entries

**⚠️  Breaking Changes Detected:** 1

1. **`httpx`** - Signature changed for 'httpx'
   - Affects 0 usage(s) across 6 file(s)
   - Affected files: `resolver.py`, `api_differ.py`, `notifications.py`

**💡 Recommendation:**

- Medium risk. Recommend testing at milestone versions to catch issues early.
- **Estimated Effort:** Medium
- **Suggested Upgrade Path:** `0.27.1` → `0.28.0` → `0.28.1`

**Usage Summary:**

- Files using this package: 6
- Unique symbols imported: 1
- Total function calls: 0

---

### rich: `13.7.0` → `14.2.0`

**Risk Score:** 30.0/100 (🟡 medium)

**Risk Factors:**

- **SemVer Distance**: `████████████████░░░░` 80.0/100 (weight: 30%)
  - Version jump from 13.7.0 to 14.2.0
- **Usage Impact**: `░░░░░░░░░░░░░░░░░░░░` 0.0/100 (weight: 50%)
  - 0 API changes affecting 10 usage points
- **Changelog Severity**: `██████░░░░░░░░░░░░░░` 30.2/100 (weight: 20%)
  - Based on 11 changelog entries

**💡 Recommendation:**

- Medium risk. Recommend testing at milestone versions to catch issues early.
- **Estimated Effort:** Medium
- **Suggested Upgrade Path:** `14.0.0` → `14.2.0`

**Usage Summary:**

- Files using this package: 2
- Unique symbols imported: 9
- Total function calls: 32

---

## 🟢 Low Risk Upgrades

### typer: `0.12.0` → `0.21.1`

**Risk Score:** 20.6/100 (🟢 low)

**Risk Factors:**

- **SemVer Distance**: `████████████░░░░░░░░` 60.0/100 (weight: 30%)
  - Version jump from 0.12.0 to 0.21.1
- **Usage Impact**: `░░░░░░░░░░░░░░░░░░░░` 0.0/100 (weight: 50%)
  - 0 API changes affecting 1 usage points
- **Changelog Severity**: `██░░░░░░░░░░░░░░░░░░` 13.2/100 (weight: 20%)
  - Based on 29 changelog entries

**💡 Recommendation:**

- Low risk detected. Direct upgrade recommended.
- **Estimated Effort:** Low

**Usage Summary:**

- Files using this package: 1
- Unique symbols imported: 1
- Total function calls: 0

---
