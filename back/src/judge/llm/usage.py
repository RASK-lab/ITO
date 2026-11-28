"""1日あたりの Claude 呼び出し回数の上限（使いすぎ防止）。プロセス内で数える簡易版。"""

from __future__ import annotations

import threading
from datetime import date

from ..settings import settings

_lock = threading.Lock()
_day = date.today()
_count = 0


def allow() -> bool:
    global _day, _count
    with _lock:
        if date.today() != _day:
            _day, _count = date.today(), 0
        return _count < settings.llm_daily_limit


def record() -> None:
    global _count
    with _lock:
        _count += 1


def count() -> int:
    return _count
