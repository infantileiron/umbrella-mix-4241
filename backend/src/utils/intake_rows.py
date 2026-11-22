"""雨后补录批次的文本解析与逐行校验。

只依赖标准库：提交时把 CSV 文本拆成原始 payload，worker 再逐行校验并给出
写入所需的类型化数值或拒绝原因。缺字段、格式错误或越过日期窗的行不进入台账。
"""
import csv
import re
from datetime import date
from io import StringIO

FIELDS = ('code', 'branch', 'worked_on', 'ribs', 'fabric', 'mechanism', 'minutes', 'note')
REQUIRED = tuple(field for field in FIELDS if field != 'note')
HEADER_MARKERS = {'code', '编号', '工票编号'}
CODE_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9-]{2,31}$')
BRANCH_ALIASES = {
    'north': 'north', 'be': 'north', '北埠': 'north',
    'south': 'south', 'nq': 'south', '南桥': 'south',
}
FIELD_LABELS = {
    'code': '工票编号', 'branch': '网点', 'worked_on': '返修日期', 'ribs': '换骨根数',
    'fabric': '布损处数', 'mechanism': '开合机构', 'minutes': '有效分钟', 'note': '备注',
}
RANGES = (('ribs', 0, 12), ('fabric', 0, 12), ('mechanism', 0, 1), ('minutes', 1, 480))


def parse_rows(source):
    """把补录文本拆成逐行 payload。首行表头可省，空行忽略，缺列记为缺字段。"""
    rows = []
    for cells in csv.reader(StringIO(source.strip())):
        cells = [cell.strip() for cell in cells]
        if any(cells):
            rows.append(cells)
    if rows and rows[0][0].lower() in HEADER_MARKERS:
        rows.pop(0)
    payloads = []
    for cells in rows:
        payload = {field: (cells[index] or None) if index < len(cells) else None
                   for index, field in enumerate(FIELDS)}
        if len(cells) > len(FIELDS):
            payload['extra'] = [cell for cell in cells[len(FIELDS):] if cell]
        payloads.append(payload)
    return payloads


def row_code(payload):
    """批次内去重和台账比对的归一化编号；缺失时返回 None。超长编号截断留待校验拒绝。"""
    code = (payload.get('code') or '').upper()
    return code[:32] or None


def validate_row(payload, date_from, date_to):
    """校验一行 payload。返回 (clean, reason)：reason 为 None 时 clean 可直接写入台账。"""
    if payload.get('extra'):
        return None, '列数超出模板，请检查是否多了逗号'
    missing = [FIELD_LABELS[field] for field in REQUIRED if not payload.get(field)]
    if missing:
        return None, '缺少字段：' + '、'.join(missing)
    code = payload['code'].upper()
    if not CODE_PATTERN.match(code):
        return None, '工票编号格式不正确（字母、数字与连字符，3–32 位）'
    branch = BRANCH_ALIASES.get(payload['branch'].lower())
    if not branch:
        return None, '网点应为 north/south（或 BE/NQ）'
    try:
        worked_on = date.fromisoformat(payload['worked_on'])
    except ValueError:
        return None, '返修日期格式应为 YYYY-MM-DD'
    numbers = {}
    for field, low, high in RANGES:
        try:
            value = int(payload[field])
        except ValueError:
            return None, f'{FIELD_LABELS[field]}应为整数'
        if not low <= value <= high:
            return None, f'{FIELD_LABELS[field]}应在 {low}–{high} 之间'
        numbers[field] = value
    note = payload.get('note') or ''
    if len(note) > 180:
        return None, '备注超过 180 字'
    if not date_from <= worked_on <= date_to:
        return None, f'越过日期窗（{date_from.isoformat()} 至 {date_to.isoformat()}），留在待处理清单'
    return dict(code=code, branch=branch, worked_on=worked_on, **numbers, note=note), None


def same_ticket(existing, clean):
    """台账记录与补录内容完全一致时，重试不再重复写入。"""
    return all(existing[key] == clean[key]
               for key in ('branch', 'worked_on', 'ribs', 'fabric', 'mechanism', 'minutes', 'note'))
