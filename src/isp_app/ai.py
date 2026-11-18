from dataclasses import dataclass
from typing import Protocol

@dataclass
class Draft:
    text: str
    sources: list[str]
    reviewed: bool = False

class AssistantProvider(Protocol):
    def draft(self, context: dict, sources: list[str], *, api_key: str, consent: bool) -> Draft: ...

class OfflineAssistant:
    def draft(self, context, sources, *, api_key='', consent=False):
        raise RuntimeError('AI連携は未設定です。MVPは外部送信を行いません。出典・送信同意・担当者確認を伴う拡張が必要です。')
