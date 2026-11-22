import { DRAFT_STATUS, ITEM_STATUS, RUN_STATUS } from '../../constants/domain.js';
import { esc } from '../../utils/html.js';

const LABELS = { ...RUN_STATUS, ...DRAFT_STATUS, ...ITEM_STATUS };

export function status(value, labels = LABELS) {
  return `<span class="status ${esc(value)}"><i></i>${esc(labels[value] || LABELS[value] || '待复核')}</span>`;
}
