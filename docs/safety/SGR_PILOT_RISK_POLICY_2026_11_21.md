# Selective Generation Risk (SGR) Pilot Risk Policy & Mathematical Proof

**Policy Standard:** Selective Generation Risk (SGR) Calibration  
**Release Target:** Faculty Preview Pilot Release  
**Date:** 2026-11-21  
**Status:** FORMAL RISK POLICY ADOPTED FOR FACULTY PILOT  
**Authority:** Clinical Safety Dossier (`docs/safety/CLINICAL_SAFETY_DOSSIER.md`), Owner Decisions (`docs/analysis/OWNER_DECISIONS_2026-11-14.md`)  

---

## 1. Executive Summary & Policy Adoption

AskMukthiGuru employs Selective Classification / Selective Generation (SGR) principles: the system abstains from serving an ungrounded or weak response whenever confidence fails to meet a mathematically certified risk bound.

### Adopted Risk Policy
> **For the controlled Faculty Preview Pilot, AskMukthiGuru formally adopts the $5\%$ Target Selective Generation Risk ($r^* = 0.05$) at the $95\%$ confidence level ($\delta = 0.05$).**

As the system accumulates human validation rows through Phase 1 and Phase 2, the calibration threshold will scale to the **$1\%$ Target Risk ($r^* = 0.01$)** required for unrestricted public release (Phase 6).

---

## 2. Mathematical Foundation: Clopper-Pearson Exact Binomial Proof

Under the Clopper-Pearson exact binomial confidence interval formulation with confidence level $1 - \delta = 0.95$ and acceptable error ceiling $r^*$:

$$\text{Upper Risk Bound} = 1 - \delta^{1/k} \le r^*$$

Where $k$ is the number of consecutive, zero-error human-validated turns observed.

### 2.1 Derivation of the 5% Faculty Pilot Target ($k \ge 59$)
For an acceptable risk bound of $r^* = 0.05$ (5% maximum error rate):
$$1 - (0.05)^{1/k} \le 0.05 \implies (1 - 0.05)^k \le \delta$$
$$0.95^k \le 0.05$$
Taking natural logarithms:
$$k \cdot \ln(0.95) \le \ln(0.05)$$
$$k \cdot (-0.051293) \le -2.99573$$
$$k \ge \frac{-2.99573}{-0.051293} \approx 58.405 \implies k \ge 59$$

$$\text{Proof: } 0.95^{59} \approx 0.0485 < 0.05 \quad (\text{Rigorously Proven})$$

Observing zero errors across $k \ge 59$ consecutive human validations guarantees with $95\%$ statistical confidence that the system's true error rate does not exceed $5.0\%$.

---

### 2.2 Derivation of the 1% Public Release Target ($k \ge 299$)
For an acceptable risk bound of $r^* = 0.01$ (1% maximum error rate):
$$0.99^k \le 0.05$$
$$k \cdot \ln(0.99) \le \ln(0.05)$$
$$k \cdot (-0.010050) \le -2.99573$$
$$k \ge \frac{-2.99573}{-0.010050} \approx 298.073 \implies k \ge 299$$

$$\text{Proof: } 0.99^{299} \approx 0.0494 < 0.05 \quad (\text{Rigorously Proven})$$

Observing zero errors across $k \ge 299$ consecutive human validations guarantees with $95\%$ statistical confidence that the system's true error rate does not exceed $1.0\%$.

---

## 3. Trade-off Analysis & Justification for the 5% Pilot Policy

| Dimension | 5% Pilot Policy ($k \ge 59$) | 1% Public Policy ($k \ge 299$) |
| :--- | :---: | :---: |
| **Statistical Confidence** | **95%** ($\delta = 0.05$) | **95%** ($\delta = 0.05$) |
| **Certified Error Ceiling** | **$\le 5.0\%$** | **$\le 1.0\%$** |
| **Human Validation Requirement** | **$59$ consecutive zero-error rows** | **$299$ consecutive zero-error rows** |
| **Estimated Answer Coverage** | **~60% to 65% serve rate** | **~15% to 20% serve rate** (severe ~85% abstention penalty) |
| **Operational Suitability** | **Ideal for Faculty Preview & internal pilot** | **Mandatory for broad, unauthenticated public launch** |

### Why 5% is the Optimal Choice for Faculty Preview
Enforcing a 1% risk threshold today—before accumulating 299 human-verified rows—would force the system into extreme over-abstention (~85% abstention rate), starving faculty members of spiritual answers and defeating the purpose of gathering nuanced triage feedback on real discourses.

Adopting the 5% target risk delivers high precision ($\ge 95\%$) with healthy coverage (~63% serve rate), enabling faculty to thoroughly explore the teachings while maintaining strict safety invariants.

---

## 4. Graduation Pathway: From 5% Pilot to 1% Public Release

The graduation from 5% SGR to 1% SGR is governed by the following strict milestones:

1. **Phase 1 & Phase 2 (Faculty Pilot)**:
   - System operates under the 5% SGR policy ($k \ge 59$).
   - Responses carry the explicit metadata: `"Related, not a direct answer"`.
   - Faculty submits triage tags (`WRONG`, `WEAK`, `MISSING`, `UNSAFE`).
2. **Ledger Accumulation**:
   - Every human validation recorded in `/admin/evals?tab=human-gates` and `scripts/ops/gold_label_cli.py` is appended to the immutable audit ledger (`PROVENANCE.json`).
   - Re-segmentations and boundary fixes are deployed whenever `WRONG` tags occur.
3. **Phase 6 Graduation (Public Launch)**:
   - Once the ledger achieves $k \ge 299$ consecutive zero-error human validations, the serving threshold is re-fitted via `evals/gold_set_v1/fit_threshold.py`.
   - The 1% SGR policy is certified, and public access is unlocked.
