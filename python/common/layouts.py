"""File layouts of the (simulated) core-banking extracts.

Single source of truth shared by the generator (writer) and the ETL (loader).
Every file is pipe-delimited UTF-8 with a header row and a trailer row:
    TRL|<record_count>|<business_date YYYYMMDD>
"""

LAYOUTS: dict[str, list[str]] = {
    "BRANCH": ["branch_code", "branch_name", "branch_level", "parent_branch_code", "province_code",
               "district", "open_date", "status", "effective_date"],
    "CUSTOMER": ["cif", "customer_type", "full_name", "gender", "date_of_birth", "id_number", "tax_code",
                 "phone", "province_code", "home_branch_code", "segment", "occupation", "industry",
                 "open_date", "close_date", "status", "record_action", "effective_date"],
    "CASA_ACCOUNT": ["account_no", "cif", "product_code", "branch_code", "open_date", "close_date", "status"],
    "CASA_BALANCE": ["snapshot_date", "account_no", "balance", "accrued_interest", "status"],
    "TXN": ["txn_id", "account_no", "txn_datetime", "business_date", "txn_type", "dr_cr", "amount",
            "channel_code", "branch_code", "atm_id", "counterparty_bank", "description", "is_reversal"],
    "TERM_DEPOSIT": ["td_id", "cif", "product_code", "branch_code", "open_date", "maturity_date", "term_months",
                     "interest_rate", "principal", "rollover_of", "close_date", "close_reason"],
    "TD_BALANCE": ["snapshot_date", "td_id", "principal", "accrued_interest", "status"],
    "LOAN": ["loan_id", "cif", "product_code", "branch_code", "disbursement_date", "maturity_date",
             "term_months", "approved_amount", "interest_rate", "repayment_method", "collateral_type",
             "collateral_value", "close_date", "close_reason"],
    "LOAN_BALANCE": ["snapshot_date", "loan_id", "outstanding_principal", "overdue_principal", "dpd",
                     "loan_group", "cic_group", "accrued_interest", "status"],
    "CARD": ["card_id", "masked_pan", "cif", "product_code", "account_ref", "branch_code", "issue_date",
             "activation_date", "expiry_date", "credit_limit", "status", "close_date"],
    "CARD_TXN": ["card_txn_id", "card_id", "txn_datetime", "business_date", "mcc", "merchant_name", "amount",
                 "is_ecommerce", "is_international", "auth_status"],
    "ATM_DAILY": ["business_date", "atm_id", "branch_code", "onus_wd_count", "onus_wd_amount", "offus_wd_count",
                  "offus_wd_amount", "uptime_minutes", "incident_count", "cash_out_flag"],
    "BRANCH_OPS": ["business_date", "branch_code", "tellers", "counter_txn_count", "service_request_count",
                   "avg_wait_minutes", "avg_service_minutes", "pct_wait_under_15m"],
    "COMPLAINT": ["complaint_id", "cif", "branch_code", "received_datetime", "channel", "complaint_type",
                  "sla_days", "resolved_datetime", "status", "is_valid"],
    "GL_BALANCE": ["snapshot_date", "branch_code", "gl_account", "balance"],
}

# Snapshot (month-end) entities vs event (delta) entities
SNAPSHOT_ENTITIES = {"CASA_BALANCE", "TD_BALANCE", "LOAN_BALANCE", "GL_BALANCE"}


def file_name(bank_code: str, entity: str, business_date: str, revision: int = 0) -> str:
    suffix = f"_R{revision}" if revision else ""
    return f"{bank_code}_{entity}_{business_date}{suffix}.csv"
