-- =====================================================================================
-- Batch orchestration: called by the Python ETL after the staging tables are loaded
-- =====================================================================================
CREATE OR REPLACE PROCEDURE ctl.sp_process_batch(p_batch int, p_refresh_marts boolean DEFAULT true)
LANGUAGE plpgsql AS $$
DECLARE v_bdate date;
BEGIN
    SELECT business_date INTO v_bdate FROM ctl.batch WHERE batch_id = p_batch;
    CALL dwh.sp_load_branch(p_batch);
    CALL dwh.sp_load_customer(p_batch);
    CALL dwh.sp_load_contracts(p_batch);
    CALL dwh.sp_load_casa_txn(p_batch);
    CALL dwh.sp_load_snapshots(p_batch);
    CALL dwh.sp_load_cards_ops(p_batch);
    CALL dq.sp_run_checks(p_batch);
    IF p_refresh_marts THEN
        -- previous month is refreshed too: weekend transactions of the last days of a month are posted next month
        CALL mart.sp_refresh((date_trunc('month', v_bdate) - interval '1 month')::date, v_bdate);
    END IF;
    UPDATE ctl.batch SET status = 'SUCCESS', finished_at = now() WHERE batch_id = p_batch;
END $$;
