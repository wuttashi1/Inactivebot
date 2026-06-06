from aiogram.filters.callback_data import CallbackData


class MenuCb(CallbackData, prefix="m"):
    action: str
    group_id: int = 0


class CleanCb(CallbackData, prefix="cl"):
    action: str  # period | preview | confirm | cancel
    group_id: int
    days: int = 0


class ZeroCleanCb(CallbackData, prefix="zc"):
    action: str  # period | preview | confirm | cancel
    group_id: int
    days: int = 0


class WarnCb(CallbackData, prefix="wn"):
    action: str  # period | send
    group_id: int
    days: int = 0


class AutoCleanCb(CallbackData, prefix="ac"):
    action: str  # toggle | period | custom
    group_id: int
    days: int = 0
    enabled: int = -1  # 0 off, 1 on


class AdminCb(CallbackData, prefix="ad"):
    action: str  # list | add | remove
    group_id: int
    target_id: int = 0


class WhitelistCb(CallbackData, prefix="wl"):
    action: str  # list | add | remove
    group_id: int
    target_id: int = 0


class MembersCb(CallbackData, prefix="mb"):
    action: str  # parse | top_active | top_inactive | candidates | inactive | zero
    group_id: int
    days: int = 30


class GroupCb(CallbackData, prefix="gr"):
    action: str  # select | bind
    group_id: int = 0


class OwnerCb(CallbackData, prefix="ow"):
    action: str  # groups | reset | transfer | unbind | unbind_confirm
    group_id: int = 0


class ReportCb(CallbackData, prefix="rp"):
    action: str  # weekly | monthly
    group_id: int


class RollcallCb(CallbackData, prefix="rc"):
    action: str  # start | confirm
    group_id: int = 0


class ActiveCb(CallbackData, prefix="act"):
    """User confirms they are active."""
    group_id: int
