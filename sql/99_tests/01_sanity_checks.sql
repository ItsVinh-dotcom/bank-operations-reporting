-- =====================================================================================
-- Sanity checks after a full load. Every query should return 0 rows (or the documented exceptions).
--   psql -d dlb_dwh -f sql/99_tests/01_sanity_checks.sql
-- =====================================================================================

\echo '1. Batches not successful (expect 0 rows)'
SELECT batch_id, business_date, batch_type, status, message FROM ctl.batch WHERE status <> 'SUCCESS';

\echo '2. Exactly one current version per branch / customer (expect 0 rows)'
SELECT 'branch' AS dim, branch_code AS k FROM dwh.dim_branch GROUP BY branch_code HAVING count(*) FILTER (WHERE is_current) <> 1
UNION ALL
SELECT 'customer', cif FROM dwh.dim_customer GROUP BY cif HAVING count(*) FILTER (WHERE is_current) <> 1;

\echo '3. SCD2 versions must not overlap (expect 0 rows)'
SELECT a.cif FROM dwh.dim_customer a JOIN dwh.dim_customer b
  ON a.cif = b.cif AND a.customer_sk < b.customer_sk AND a.valid_from <= b.valid_to AND b.valid_from <= a.valid_to;

\echo '4. Mart deposits = sum of snapshots (expect 0 rows)'
SELECT k.month_end FROM mart.kpi_branch_month k
GROUP BY k.month_end
HAVING sum(k.casa_balance) <> (SELECT COALESCE(sum(balance), 0) FROM dwh.fact_casa_balance WHERE snapshot_date = k.month_end);

\echo '5. NPL ratio per month (should stay roughly within 1% - 3%)'
SELECT month_end, npl_ratio, casa_ratio, ldr FROM mart.v_kpi_bank_month WHERE npl_ratio NOT BETWEEN 0.01 AND 0.03;

\echo '6. GL reconciliation items (expect exactly the 4 documented items)'
SELECT r.business_date, i.record_key, i.detail FROM dq.issue i JOIN dq.result r USING (batch_id, rule_code)
WHERE i.rule_code = 'GL_RECON' ORDER BY 1, 2;

\echo '7. Rejected files (expect 1 row: DLB_TXN_20260819.csv)'
SELECT batch_id, file_name, message FROM ctl.file_log WHERE status = 'REJECTED';
