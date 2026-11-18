"""UI-independent project model. Field IDs come from the supplied mapping."""
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta, date
from uuid import uuid4

JST = timezone(timedelta(hours=9))

def now():
    return datetime.now(JST).isoformat(timespec='seconds')

def today():
    return datetime.now(JST).date().isoformat()

@dataclass
class Project:
    schema_version: int = 1
    project_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    template_id: str = 'blank'
    fields: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=lambda: {'status': '下書き'})
    settings: dict = field(default_factory=lambda: {'reviewed_fields': {}, 'empty_policy': {}, 'consent_confirmed': {}})
    master_selections: list = field(default_factory=list)
    monitoring: list = field(default_factory=list)
    history: list = field(default_factory=list)
    attachments: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.get('schema_version') != 1:
            raise ValueError('未対応のプロジェクト形式です')
        if set(value) != set(cls().to_dict()):
            raise ValueError('プロジェクト項目が不足、または未対応です')
        for name in ('fields', 'metadata', 'settings'):
            if not isinstance(value[name], dict):
                raise ValueError(f'{name} の型が不正です')
        for name in ('master_selections', 'monitoring', 'history', 'attachments'):
            if not isinstance(value[name], list) or not all(isinstance(x, dict) for x in value[name]):
                raise ValueError(f'{name} の型が不正です')
        for name in ('project_id', 'created_at', 'updated_at', 'template_id'):
            if not isinstance(value[name], str):
                raise ValueError(f'{name} の型が不正です')
        for name in ('reviewed_fields', 'empty_policy', 'consent_confirmed'):
            if not isinstance(value['settings'].get(name), dict):
                raise ValueError('設定の型が不正です')
        return cls(**deepcopy(value))

    def snapshot(self):
        return deepcopy({k: v for k, v in self.to_dict().items() if k not in ('history', 'updated_at')})

    def record_change(self, before, reason, effective_on, detail=''):
        if reason not in ('定期', 'サビ管変更', '加算変更', 'その他'):
            raise ValueError('変更理由を選択してください')
        date.fromisoformat(effective_on)
        changes = diff(before, self.snapshot())
        if changes:
            self.history.append({'recorded_at': now(), 'reason': reason, 'effective_on': effective_on,
                                 'detail': detail, 'changes': changes})
            self.updated_at = now()

    def duplicate(self):
        result = Project.from_dict(self.to_dict())
        result.project_id = str(uuid4())
        result.created_at = result.updated_at = now()
        result.metadata.update(status='下書き', previous_project_id=self.project_id)
        result.metadata.pop('status_evidence', None)
        result.metadata.pop('status_date', None)
        result.settings['consent_confirmed'] = {}
        for key in list(result.fields):
            if key.endswith('.consent_date'):
                del result.fields[key]
        return result

    def start_monitoring(self, plan='final'):
        goals = [{ 'number': n, 'target': self.fields.get(f'{plan}.goals.{n}.target', ''),
                   'support': deepcopy(self.fields.get(f'{plan}.goals.{n}.support', '')),
                   'actual': '', 'achievement': '未評価', 'response': ''}
                 for n in range(1, 5) if self.fields.get(f'{plan}.goals.{n}.target')]
        if not goals:
            raise ValueError('引き継ぐ目標を先に入力してください')
        self.monitoring.append({'id': str(uuid4()), 'source_project_id': self.project_id,
            'source_updated_at': self.updated_at, 'source_plan': plan, 'recorded_on': today(),
            'recorded_by': '', 'next_review_on': '', 'goals': goals})

def diff(old, new, prefix=''):
    if isinstance(old, dict) and isinstance(new, dict):
        result = []
        for key in sorted(old.keys() | new.keys()):
            result.extend(diff(old.get(key), new.get(key), f'{prefix}.{key}'.strip('.')))
        return result
    return [] if old == new else [{'field': prefix, 'old': deepcopy(old), 'new': deepcopy(new)}]
