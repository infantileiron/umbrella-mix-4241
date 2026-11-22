from enum import StrEnum


class Role(StrEnum):
    OWNER = 'owner'
    ANALYST = 'analyst'
    OBSERVER = 'observer'


class Branch(StrEnum):
    NORTH = 'north'
    SOUTH = 'south'


class Basis(StrEnum):
    FOCUS = 'focus'
    CONTROL = 'control'


class RunStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class DraftStatus(StrEnum):
    DRAFT = 'draft'
    PUBLISHED = 'published'


class ItemStatus(StrEnum):
    PENDING = 'pending'
    INSERTED = 'inserted'
    REVISED = 'revised'
    SKIPPED = 'skipped'
    REJECTED = 'rejected'


BRANCH_LABEL = {Branch.NORTH: '北埠修伞铺', Branch.SOUTH: '南桥修伞铺'}
FEATURES = ('ribs', 'fabric', 'mechanism')
TERMS = ('intercept', *FEATURES)
METHOD = 'ob-twofold-ols-v1'
INTAKE_MAX_ROWS = 500
INTAKE_MAX_ATTEMPTS = 8
