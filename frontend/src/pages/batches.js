import { api } from '../api/workspace.js';
import { select } from '../components/common/form.js';
import { heading } from '../components/common/heading.js';
import { empty, panel } from '../components/common/panel.js';
import { status } from '../components/common/status.js';
import { table } from '../components/common/table.js';
import { BASIS, BATCH_STATUS, BRANCH } from '../constants/domain.js';
import { bindForm } from '../hooks/forms.js';
import { poll } from '../hooks/poll.js';
import { go } from '../router/routes.js';
import { state } from '../stores/workspace.js';
import { batchCode, localTime, number, runCode, signed } from '../utils/format.js';
import { esc } from '../utils/html.js';

const SAMPLE = '编号,网点,日期,换骨,布损,机构,分钟,备注\nNQ-W46-33,south,2026-11-14,2,1,0,27,雨后复检\nBE-W46-33,north,2026-11-14,1,0,1,19,';
const ACTIVE = ['queued', 'running'];

function console_(plans) {
  return `<section class="intake-console"><form class="intake-form">
    <div class="field-grow">${select('按方案版本纳入日期窗', 'plan_id', plans.map(plan =>
      `<option value="${plan.id}"${plan.id === state.planId ? ' selected' : ''}>${esc(plan.plan_key)} · v${plan.version} · ${esc(plan.label)}</option>`).join(''))}
      <p id="selected-plan"></p></div>
    <label>补录内容（CSV，每行一张工票）<textarea name="source" rows="7" required
      placeholder="${esc(SAMPLE)}"></textarea></label>
    <p class="field-note">列顺序：编号, 网点(north/south 或 BE/NQ), 日期(YYYY-MM-DD), 换骨, 布损, 机构(0/1), 分钟, 备注。首行表头可省，单批最多 500 行。</p>
    <div class="row-actions"><button class="btn primary" type="submit">提交补录批次 ↗</button>
      <p role="alert" class="form-error" data-form-error></p></div></form>
    <div class="intake-side"><b>批次即队列</b><p>有效票写入台账并纳入一次差额运行；同编号重复补录保留一次，修订票按版本更新；缺字段或越过日期窗的票留在待处理清单。中断后重试从上次进度继续，已完成批次不被后续补票改写。</p></div></section>`;
}

function written(batch) {
  const total = batch.inserted + batch.revised;
  return `<b class="mono">${total}</b>${batch.revised ? `<span class="subline">含修订 ${batch.revised}</span>` : ''}`;
}

function batchRow(batch) {
  const busy = ACTIVE.includes(batch.status);
  return [`<b class="mono">${batchCode(batch.id)}</b>`,
    `<b>${esc(batch.plan_key)} · v${batch.version}</b><span class="subline">${esc(batch.label)}</span>`,
    esc(localTime(batch.created_at)),
    `${status(batch.status, BATCH_STATUS)}${busy ? `<span class="subline">已处理 ${batch.total - batch.pending}/${batch.total}</span>` : ''}${batch.failure ? `<span class="subline failure">${esc(batch.failure)}</span>` : ''}`,
    written(batch), `<span class="mono">${batch.skipped}</span>`, `<span class="mono">${batch.rejected}</span>`,
    batch.run_id ? `<a class="text-btn" href="#/results/${batch.run_id}">${runCode(batch.run_id)} ↗</a>${batch.run_status ? `<span class="subline">${status(batch.run_status)}</span>` : ''}` : '—',
    `<a class="text-btn" href="#/batches/${batch.id}">打开批次 ↗</a>`];
}

function batchTable(items) {
  return table(['批次', '方案版本', '提交时间', '状态', '写入', '跳过', '拒绝', '差额运行', '查看'],
    items.map(batchRow), '暂无补录批次。分析员可在上方提交雨后补录。', 'batch-table');
}

async function batchList({ view, active, refresh }) {
  const canWrite = state.user.role === 'analyst';
  const [plans, items] = await Promise.all([canWrite ? api.plans() : [], api.batches()]);
  if (!active()) return;
  const setup = canWrite
    ? (plans.length ? console_(plans)
      : empty('先设置对照组', '保存一个比较方案版本后，补录批次才能按日期窗纳入。', '<a class="btn" href="#/plans">打开对照组设置</a>'))
    : '';
  view.innerHTML = heading('跨网点工票批录', '雨后补录', '按补录批次写入有效票并纳入一次差额拆解运行，留待处理的票不会混入台账。',
    '<button class="btn" data-reload>刷新批次</button>') + setup +
    panel('批次记录', '', '<p class="inline-alert" data-poll-error></p><div id="batch-items">' + batchTable(items) + '</div>');
  const busy = entries => entries.some(batch => ACTIVE.includes(batch.status) || ACTIVE.includes(batch.run_status));
  const watch = () => poll(async () => {
    const entries = await api.batches();
    if (active()) view.querySelector('#batch-items').innerHTML = batchTable(entries);
    return busy(entries);
  }, active);
  if (busy(items)) watch();
  view.querySelector('[data-reload]').onclick = refresh;
  const form = view.querySelector('form');
  if (form) {
    const display = () => {
      const plan = plans.find(item => item.id === Number(form.elements.plan_id.value));
      state.planId = plan.id;
      view.querySelector('#selected-plan').textContent =
        `${BRANCH[plan.focus_branch]} − ${BRANCH[plan.control_branch]} · ${BASIS[plan.coefficient_ref]} · 日期窗 ${plan.date_from} 至 ${plan.date_to}`;
    };
    form.elements.plan_id.onchange = display;
    display();
    bindForm(form, async fields => {
      const batch = await api.createBatch({ plan_id: Number(fields.plan_id), source: fields.source });
      state.notice = `批次 ${batchCode(batch.id)} 已提交，共 ${batch.total} 行。`;
      go('batches', batch.id);
    });
  }
}

function summaryStrip(counts) {
  const metrics = [
    ['写入台账', counts.inserted + counts.revised, `新票 ${counts.inserted} · 修订 ${counts.revised}`],
    ['跳过', counts.skipped, '批内重复或与台账一致'],
    ['拒绝', counts.rejected, '缺字段或越过日期窗'],
    ['待处理', counts.pending, counts.pending ? '队列处理中' : '本批已处理完'],
  ];
  return `<section class="intake-summary" aria-label="写入、跳过、拒绝与待处理">${metrics.map(([label, value, note]) =>
    `<article class="intake-metric"><h2>${label}</h2><strong class="mono">${value}</strong><p>${note}</p></article>`).join('')}</section>`;
}

function reconcile(run) {
  if (!run) return panel('两点差额对账', '', '<p class="review-body">批次处理完成后，会基于台账快照生成一次差额拆解运行。</p>');
  if (run.status !== 'completed') {
    return panel('两点差额对账', runCode(run.id), `<div class="review-body">${status(run.status)}
      ${run.status === 'failed'
        ? `<p class="inline-alert">${esc(run.failure || '差额计算待补正。')}</p><p class="field-note">可在运行工票页按方案版本重新提交。</p>`
        : '<p class="field-note">差额计算进行中，页面会自动刷新。</p>'}</div>`);
  }
  const { result } = run;
  const a = result.focus, b = result.control;
  return panel('两点差额对账', `${runCode(run.id)} · 守恒已核对`, `<div class="review-body">
    <p class="reconcile-line">${BRANCH[a.branch]} <b class="mono">${number(a.mean_minutes)}</b> − ${BRANCH[b.branch]}
      <b class="mono">${number(b.mean_minutes)}</b> ＝ 实际差 <b class="mono warm">${signed(result.gap)}</b> 分钟/票</p>
    <p class="reconcile-line">构成差 <b class="mono warm">${signed(result.composition)}</b> ＋ 系数差
      <b class="mono cool">${signed(result.coefficient)}</b> ＝ <b class="mono">${signed(result.composition + result.coefficient)}</b> 分钟/票，
      与实际差一致<small class="mono">（残差 ${result.remainder.toExponential(2)}）</small></p>
    <a class="text-btn" href="#/results/${run.id}">查看完整拆解 ↗</a></div>`);
}

function itemBranch(value) {
  const key = String(value || '').toLowerCase();
  return BRANCH[key] || ({ be: BRANCH.north, nq: BRANCH.south }[key]) || esc(value || '—');
}

function itemNote(item) {
  if (item.reason) return item.reason;
  if (item.status === 'inserted') return '新票写入台账';
  if (item.status === 'revised') return `按版本修订为 v${item.revision}`;
  return '';
}

function itemsTable(items) {
  return table(['行号', '工票编号', '网点', '返修日期', '换骨', '布损', '机构', '分钟', '备注', '状态', '说明'], items.map(item => {
    const p = item.payload;
    return [`<span class="mono">${item.seq}</span>`, `<b class="mono">${esc(item.code || p.code || '—')}</b>`,
      itemBranch(p.branch), esc(p.worked_on || '—'), esc(p.ribs ?? '—'), esc(p.fabric ?? '—'), esc(p.mechanism ?? '—'),
      esc(p.minutes ?? '—'), esc(p.note || ''), status(item.status), esc(itemNote(item))];
  }), '本批没有工票行。', 'intake-items');
}

async function batchDetail({ id, view, active, refresh }) {
  const batch = await api.batch(id);
  if (!active()) return;
  const { plan, items, run } = batch;
  const counts = Object.fromEntries(['inserted', 'revised', 'skipped', 'rejected', 'pending'].map(key =>
    [key, items.filter(item => item.status === key).length]));
  const pending = items.filter(item => ['pending', 'rejected'].includes(item.status));
  const canRetry = state.user.role === 'analyst' && batch.status === 'failed';
  view.innerHTML = heading('跨网点工票批录', `批次 ${batchCode(batch.id)}`,
    `${plan.plan_key} · v${plan.version} · ${plan.label} · 日期窗 ${plan.date_from} 至 ${plan.date_to} · 经办 ${batch.created_by}`,
    `<a class="btn" href="#/batches">返回批次列表</a>${canRetry ? '<button class="btn primary" data-retry>重试本批次 ↻</button>' : ''}`) +
    summaryStrip(counts) + reconcile(run) +
    panel('待处理清单', `${pending.length} 行`, table(['行号', '工票编号', '返修日期', '状态', '原因'], pending.map(item => [
      `<span class="mono">${item.seq}</span>`, `<b class="mono">${esc(item.code || item.payload.code || '—')}</b>`,
      esc(item.payload.worked_on || '—'), status(item.status), esc(item.reason || '队列处理中')]),
      '没有待处理的工票，本批全部写入或跳过。') +
      '<p class="field-note">缺字段或越过日期窗的工票不会写入台账；修正后请新建批次提交，已完成批次保持只读。</p>') +
    panel('全部明细', `${items.length} 行`, itemsTable(items)) +
    (batch.status === 'completed' ? '<aside class="method-note"><b>批次只读</b><p>本批计数、明细与差额运行快照已冻结；后续补票请新建批次，不会改写本批记录。</p></aside>' : '') +
    '<p class="inline-alert" data-poll-error></p>';
  const signature = data => JSON.stringify([data.status, data.run?.status,
    data.items.map(item => item.status).join()]);
  if (ACTIVE.includes(batch.status) || (run && ACTIVE.includes(run.status))) {
    const current = signature(batch);
    poll(async () => {
      const latest = await api.batch(id);
      if (!active()) return false;
      if (signature(latest) !== current) {
        refresh();
        return false;
      }
      return true;
    }, active);
  }
  const retry = view.querySelector('[data-retry]');
  if (retry) retry.onclick = async () => {
    retry.disabled = true;
    try {
      await api.retryBatch(id);
      state.notice = `批次 ${batchCode(id)} 已重新排队，从上次进度继续。`;
      refresh();
    } catch (error) {
      view.querySelector('[data-poll-error]').textContent = error.message;
      retry.disabled = false;
    }
  };
}

export async function batches({ id, view, active, refresh }) {
  if (id) await batchDetail({ id, view, active, refresh });
  else await batchList({ view, active, refresh });
}
