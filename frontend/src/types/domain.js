/** @typedef {{username: string, display_name: string, role: 'owner'|'analyst'|'observer'}} User */
/** @typedef {{code: string, branch: 'north'|'south', worked_on: string, ribs: number, fabric: number, mechanism: number, minutes: number, note: string, revision: number}} Ticket */
/** @typedef {{id: number, plan_key: string, version: number, label: string, focus_branch: string, control_branch: string, coefficient_ref: 'focus'|'control', date_from: string, date_to: string, min_samples: number}} Plan */
/** @typedef {{id: number, status: 'queued'|'running'|'completed'|'failed', plan: Plan, sample_count: number, snapshot_sha: string}} Run */
/** @typedef {{id: number, status: 'queued'|'running'|'completed'|'failed', total: number, inserted: number, revised: number, skipped: number, rejected: number, pending: number, run_id: number|null}} Batch */
/** @typedef {{seq: number, code: string|null, status: 'pending'|'inserted'|'revised'|'skipped'|'rejected', reason: string|null, revision: number|null, payload: object}} IntakeItem */
export {};
