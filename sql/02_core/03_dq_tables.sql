-- =====================================================================================
-- Data-quality framework
-- =====================================================================================
CREATE TABLE IF NOT EXISTS dq.rule (
    rule_code    text PRIMARY KEY,
    entity       text NOT NULL,
    dimension    text NOT NULL,     -- Completeness / Validity / Uniqueness / Consistency / Reconciliation / Timeliness
    severity     text NOT NULL,     -- HIGH / MEDIUM / LOW
    description  text NOT NULL,
    threshold_pct numeric(6,3) NOT NULL DEFAULT 0   -- allowed failure rate before status = FAIL
);

CREATE TABLE IF NOT EXISTS dq.result (
    batch_id      int  NOT NULL,
    business_date date NOT NULL,
    rule_code     text NOT NULL REFERENCES dq.rule(rule_code),
    checked_rows  bigint NOT NULL,
    failed_rows   bigint NOT NULL,
    failed_amount numeric(20,0),
    status        text NOT NULL,     -- PASS / WARN / FAIL
    checked_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, rule_code)
);

CREATE TABLE IF NOT EXISTS dq.issue (
    batch_id    int  NOT NULL,
    rule_code   text NOT NULL,
    record_key  text NOT NULL,
    detail      text,
    PRIMARY KEY (batch_id, rule_code, record_key)
);

INSERT INTO dq.rule VALUES
 ('CUS_DUP_CIF',     'CUSTOMER',     'Uniqueness',     'MEDIUM', 'CIF xuất hiện nhiều lần trong cùng một file', 0),
 ('CUS_MISS_DOB',    'CUSTOMER',     'Completeness',   'MEDIUM', 'Khách hàng cá nhân thiếu ngày sinh', 0.5),
 ('CUS_MISS_ID',     'CUSTOMER',     'Completeness',   'HIGH',   'Khách hàng cá nhân thiếu số CCCD', 0),
 ('CUS_BAD_PHONE',   'CUSTOMER',     'Validity',       'LOW',    'Số điện thoại không đủ 10 chữ số', 0.5),
 ('TXN_DUP_ID',      'TXN',          'Uniqueness',     'HIGH',   'Mã giao dịch bị trùng', 0),
 ('TXN_BAD_BRANCH',  'TXN',          'Validity',       'HIGH',   'Mã chi nhánh không tồn tại trong danh mục', 0),
 ('TXN_NEG_AMOUNT',  'TXN',          'Validity',       'HIGH',   'Số tiền âm nhưng không phải giao dịch hoàn trả', 0),
 ('TXN_LATE_POST',   'TXN',          'Timeliness',     'MEDIUM', 'Hạch toán trễ hơn 1 ngày làm việc so với ngày giao dịch', 0.1),
 ('TXN_ORPHAN_ACC',  'TXN',          'Consistency',    'HIGH',   'Giao dịch của tài khoản không có trong danh mục tài khoản', 0),
 ('LN_MISS_COLL',    'LOAN',         'Completeness',   'HIGH',   'Khoản vay có TSĐB nhưng thiếu giá trị tài sản', 0),
 ('LN_GROUP_DIFF',   'LOAN_BALANCE', 'Consistency',    'HIGH',   'Nhóm nợ core khác nhóm nợ DWH tính lại (DPD + CIC)', 0),
 ('CASA_ROLLFWD',    'CASA_BALANCE', 'Reconciliation', 'HIGH',   'Số dư đầu kỳ + phát sinh ≠ số dư cuối kỳ (tài khoản thanh toán)', 0),
 ('GL_RECON',        'GL_BALANCE',   'Reconciliation', 'HIGH',   'Số dư chi tiết khác số dư sổ cái (theo chi nhánh, tài khoản GL)', 0),
 ('FILE_TRAILER',    'ALL',          'Completeness',   'HIGH',   'Số bản ghi thực tế khác số bản ghi ở dòng trailer', 0),
 ('TD_MATURITY',     'TERM_DEPOSIT', 'Consistency',    'MEDIUM', 'Ngày đáo hạn không khớp ngày mở + kỳ hạn', 0)
ON CONFLICT (rule_code) DO UPDATE SET description = EXCLUDED.description, severity = EXCLUDED.severity,
    dimension = EXCLUDED.dimension, threshold_pct = EXCLUDED.threshold_pct;
