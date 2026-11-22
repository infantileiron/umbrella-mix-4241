CREATE TABLE intake_batches (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT UNSIGNED NOT NULL,
    run_id BIGINT UNSIGNED,
    status ENUM('queued','running','completed','failed') NOT NULL DEFAULT 'queued',
    total SMALLINT UNSIGNED NOT NULL,
    inserted SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    revised SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    skipped SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    rejected SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    failure VARCHAR(240),
    claim_token CHAR(32),
    claimed_at DATETIME(6),
    created_by VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    finished_at DATETIME(6),
    INDEX intake_queue (status, id),
    FOREIGN KEY (plan_id) REFERENCES comparison_plans (id),
    FOREIGN KEY (run_id) REFERENCES analysis_runs (id),
    FOREIGN KEY (created_by) REFERENCES users (username)
) CHARACTER SET utf8mb4;

CREATE TABLE intake_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT UNSIGNED NOT NULL,
    seq SMALLINT UNSIGNED NOT NULL,
    code VARCHAR(32),
    payload JSON NOT NULL,
    status ENUM('pending','inserted','revised','skipped','rejected') NOT NULL DEFAULT 'pending',
    reason VARCHAR(240),
    revision INT UNSIGNED,
    UNIQUE KEY intake_order (batch_id, seq),
    INDEX intake_status (batch_id, status),
    INDEX intake_code (batch_id, code, seq),
    FOREIGN KEY (batch_id) REFERENCES intake_batches (id)
) CHARACTER SET utf8mb4;
