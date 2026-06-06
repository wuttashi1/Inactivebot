"""Ожидание привязки группы (по user_id, не по FSM — FSM привязан к chat_id)."""

_pending_user_ids: set[int] = set()


def start_bind(user_id: int) -> None:
    _pending_user_ids.add(user_id)


def cancel_bind(user_id: int) -> None:
    _pending_user_ids.discard(user_id)


def is_pending(user_id: int) -> bool:
    return user_id in _pending_user_ids


def finish_bind(user_id: int) -> None:
    _pending_user_ids.discard(user_id)
