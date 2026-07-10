# SoluqisBI - Version Note v1.1.0
## Reworked Operational Dashboard: Staff & Product Focus

### Overview
This release restructures the **SoluqisBI** analytics module from a generic IT log dashboard into a highly focused, single-page, tabbed **Operations Control Center**. All generic metrics (e.g., total registered users, recent user logins, access logs, and page visits) have been removed. The system now exclusively analyzes **Staff Productivity & Calibration** and **Product Quality & Traceability**.

---

### Key Dashboard Tabs

#### 1. Product Quality & Traceability Tab
Focuses on batch output, yield tracking, and component quality diagnostics:
* **SKU Quality Leaderboard:** Details total tests completed, average pass rate %, First Pass Yield (FPY) %, and post-sales service cases per SKU model.
* **Production Batch Profiler:** Monitors manufacturing batches for test coverage (QA completion meter), FPY %, and warranty returns.

#### 2. Staff Calibration Tab
Focuses on auditing operators to ensure inspection rigor and service response efficiency:
* **QA Tester Output & Calibration:** Details total tests run, passed vs. failed checks, and the tester's Approve Rate %. Used to identify tester leniency/strictness bias or misaligned test rigs.
* **Technician Service Performance:** Monitors service technicians, total cases assigned, completed repairs, and overall resolution rates.

#### 3. Alerts & Charts Tab
Provides graphical diagnostics and high-risk warning flags:
* **QA Testing Velocity Chart:** Plots daily tests passed vs. failed to audit line throughput trends.
* **Top Defect Pareto Chart:** Renders a Pareto analysis identifying the root-cause failures recorded by QA staff.
* **Operational Warnings & Risk Alerts:** Displays critical warning lists for:
  1. *Unfinished Batches:* Batches with <50% test coverage.
  2. *High Defect SKUs:* Product lines with >10% failure rates.
  3. *Stale Draft Tests:* Checklist drafts left open for >24 hours.
  4. *SLA Warranty Breaches:* Open service tickets pending for >7 days.

---

### Verification Instructions
1. Open the Soluqis dashboard at `http://127.0.0.1:8000/bi/`.
2. Verify the 4 global scorecards at the top (Overall FPY, Production Output, QA Pass Rate, Field Return Rate).
3. Toggle between the **Product Quality**, **Staff Calibration**, and **Alerts & Charts** tabs to confirm layout responsiveness and zero vertical scrolling.
4. Apply different date range presets (Today, 7 Days, 30 Days) to verify filter accuracy.
