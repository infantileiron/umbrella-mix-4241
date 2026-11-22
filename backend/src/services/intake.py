import json

from fastapi import HTTPException

from src.constants.domain import INTAKE_MAX_ROWS, ItemStatus, RunStatus
from src.models.db import transaction
from src.models.queries import BATCH_COLUMNS, ITEM_COLUMNS, PLAN_COLUMNS, TICKET_COLUMNS
from src.services.audit import record
from src.services.runs import snapshot_for_plan
from src.utils.intake_rows import parse_rows, row_code, same_ticket, validate_row
from src.utils.queue import wake_worker
from src.utils.serialization import canonical, checksum


def submit_batch(payload, actor):
    rows = parse_rows(payload.source)
    if not rows:
        raise HTTPException(400, '没有可补录的工票行，请检查文本')
    if len(rows) > INTAKE_MAX_ROWS:
        raise HTTPException(400, f'单批最多 {INTAKE_MAX_ROWS} 行，请分批提交')
    with transaction() as cursor:
        cursor.execute('SELECT 1 FROM comparison_plans WHERE id=%s', (payload.plan_id,))
        if not cursor.fetchone():
            raise HTTPException(404, '未找到方案版本')
        cursor.execute('INSERT INTO intake_batches (plan_id, total, created_by) VALUES (%s,%s,%s)',
                       (payload.plan_id, len(rows), actor))
        batch_id = cursor.lastrowid
        cursor.executemany('INSERT INTO intake_items (batch_id, seq, payload, code) VALUES (%s,%s,%s,%s)',
                           [(batch_id, seq, canonical(row), row_code(row))
                            for seq, row in enumerate(rows, 1)])
        record(cursor, actor, 'intake.submit', batch_id)
    wake_worker()
    return dict(id=batch_id, status=RunStatus.QUEUED, total=len(rows))


def list_batches():
    columns = ', '.join(f'b.{column}' for column in BATCH_COLUMNS.split(', '))
    with transaction() as cursor:
        cursor.execute(f'SELECT {columns}, p.plan_key, p.version, p.label, r.status AS run_status '
                       'FROM intake_batches b JOIN comparison_plans p ON p.id=b.plan_id '
                       'LEFT JOIN analysis_runs r ON r.id=b.run_id ORDER BY b.id DESC')
        batches = cursor.fetchall()
        cursor.execute('SELECT batch_id, status, COUNT(*) AS items FROM intake_items GROUP BY batch_id, status')
        progress = {}
        for row in cursor.fetchall():
            progress.setdefault(row['batch_id'], {})[row['status']] = row['items']
    for batch in batches:
        counts = progress.get(batch['id'], {})
        for key in ('inserted', 'revised', 'skipped', 'rejected', 'pending'):
            batch[key] = counts.get(key, 0)
    return batches


def get_batch(batch_id):
    with transaction() as cursor:
        cursor.execute(f'SELECT {BATCH_COLUMNS} FROM intake_batches WHERE id=%s', (batch_id,))
        batch = cursor.fetchone()
        if not batch:
            raise HTTPException(404, '未找到补录批次')
        cursor.execute(f'SELECT {PLAN_COLUMNS} FROM comparison_plans WHERE id=%s', (batch['plan_id'],))
        batch['plan'] = cursor.fetchone()
        cursor.execute(f'SELECT {ITEM_COLUMNS} FROM intake_items WHERE batch_id=%s ORDER BY seq', (batch_id,))
        batch['items'] = cursor.fetchall()
        for item in batch['items']:
            item['payload'] = json.loads(item['payload'])
        batch['run'] = None
        if batch['run_id']:
            cursor.execute('SELECT id, status, failure, result, created_at, finished_at '
                           'FROM analysis_runs WHERE id=%s', (batch['run_id'],))
            run = cursor.fetchone()
            run['result'] = json.loads(run['result']) if run['result'] is not None else None
            batch['run'] = run
    return batch


def retry_batch(batch_id, actor):
    with transaction() as cursor:
        cursor.execute("UPDATE intake_batches SET status='queued', attempts=0, claim_token=NULL, claimed_at=NULL, "
                       "failure=NULL WHERE id=%s AND status='failed'", (batch_id,))
        if not cursor.rowcount:
            cursor.execute('SELECT 1 FROM intake_batches WHERE id=%s', (batch_id,))
            if not cursor.fetchone():
                raise HTTPException(404, '未找到补录批次')
            raise HTTPException(409, '仅处理失败的批次需要重试，已完成批次保持只读')
        record(cursor, actor, 'intake.retry', batch_id)
    wake_worker()
    return dict(id=batch_id, status=RunStatus.QUEUED)


def _mark(cursor, item_id, status, reason=None, revision=None):
    cursor.execute('UPDATE intake_items SET status=%s, reason=%s, revision=%s WHERE id=%s',
                   (status, reason, revision, item_id))


def apply_next_item(batch_id, plan):
    """处理一张待处理工票并立即落库。返回 False 表示本批已无待处理行。"""
    with transaction() as cursor:
        cursor.execute("SELECT id, seq, code, payload FROM intake_items "
                       "WHERE batch_id=%s AND status='pending' ORDER BY seq LIMIT 1 FOR UPDATE", (batch_id,))
        item = cursor.fetchone()
        if not item:
            return False
        clean, reason = validate_row(json.loads(item['payload']), plan['date_from'], plan['date_to'])
        if reason:
            _mark(cursor, item['id'], ItemStatus.REJECTED, reason)
            return True
        cursor.execute("SELECT 1 FROM intake_items WHERE batch_id=%s AND code=%s AND seq<%s "
                       "AND status IN ('inserted','revised') LIMIT 1", (batch_id, clean['code'], item['seq']))
        if cursor.fetchone():
            _mark(cursor, item['id'], ItemStatus.SKIPPED, '同批次重复补录，仅保留首次记录')
            return True
        cursor.execute(f'SELECT {TICKET_COLUMNS} FROM tickets WHERE code=%s FOR UPDATE', (clean['code'],))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute(f'INSERT INTO tickets ({TICKET_COLUMNS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)',
                           (clean['code'], clean['branch'], clean['worked_on'], clean['ribs'], clean['fabric'],
                            clean['mechanism'], clean['minutes'], clean['note']))
            _mark(cursor, item['id'], ItemStatus.INSERTED, revision=1)
        elif same_ticket(existing, clean):
            _mark(cursor, item['id'], ItemStatus.SKIPPED, '与台账记录一致，无需重复写入', existing['revision'])
        else:
            cursor.execute('UPDATE tickets SET branch=%s, worked_on=%s, ribs=%s, fabric=%s, mechanism=%s, '
                           'minutes=%s, note=%s, revision=revision+1 WHERE code=%s',
                           (clean['branch'], clean['worked_on'], clean['ribs'], clean['fabric'],
                            clean['mechanism'], clean['minutes'], clean['note'], clean['code']))
            _mark(cursor, item['id'], ItemStatus.REVISED, revision=existing['revision'] + 1)
        return True


def finalize_batch(batch_id, token):
    """封存计数、按台账快照生成一次差额运行，并把批次置为已完成。令牌不符时不写入。"""
    with transaction() as cursor:
        cursor.execute("SELECT plan_id, created_by FROM intake_batches "
                       "WHERE id=%s AND claim_token=%s AND status='running' FOR UPDATE", (batch_id, token))
        batch = cursor.fetchone()
        if not batch:
            return False
        cursor.execute('SELECT status, COUNT(*) AS items FROM intake_items WHERE batch_id=%s GROUP BY status',
                       (batch_id,))
        counts = {row['status']: row['items'] for row in cursor.fetchall()}
        cursor.execute(f'SELECT {PLAN_COLUMNS} FROM comparison_plans WHERE id=%s', (batch['plan_id'],))
        plan = cursor.fetchone()
        snapshot = snapshot_for_plan(cursor, plan)
        cursor.execute('INSERT INTO analysis_runs (plan_id, snapshot, snapshot_sha, created_by) '
                       'VALUES (%s,%s,%s,%s)', (batch['plan_id'], snapshot, checksum(snapshot), batch['created_by']))
        run_id = cursor.lastrowid
        cursor.execute("UPDATE intake_batches SET status='completed', inserted=%s, revised=%s, skipped=%s, "
                       'rejected=%s, run_id=%s, finished_at=UTC_TIMESTAMP(6) WHERE id=%s',
                       (counts.get('inserted', 0), counts.get('revised', 0), counts.get('skipped', 0),
                        counts.get('rejected', 0), run_id, batch_id))
        record(cursor, 'worker', 'intake.completed', batch_id)
        record(cursor, batch['created_by'], 'run.submit', run_id)
    wake_worker()
    return True
