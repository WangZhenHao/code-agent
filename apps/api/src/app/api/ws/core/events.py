"""服务端 → 前端推送事件的注册表：名字、说明、params 形状。

和 `registry.py` 是同一个套路，方向相反：那边登记前端**发起**的请求方法，
这里登记后端**主动发**的通知。两者的共同点是「名字 + 形状」的单一事实源——
`scripts/gen_ws_contract.py` 读这份表，生成前端的 TS 类型和 ws.md 的表格。

为什么 params 必须是 pydantic 模型而不是裸 dict：`hub.publish_devbox_event`
的签名是 `(devbox_id, method: str, params: dict)`，事件名拼错、字段改名都能
静默通过。过一层注册表后，`publish()` 的入参有类型，改形状不跟前端/文档同步
会在 `make gen-ws-check` 和 mypy 处暴露。

新增事件：写一个 params 模型（共享形状放 `ws/schemas.py`），在下面登记一次，
调用点用 `publish(EVENT_NAME, Params(...))`，然后 `make gen-ws`。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.api.ws.core import hub
from app.api.ws.schemas import ProjectUpdateParams, ServerStatusChangedParams

# ── 事件名常量 ────────────────────────────────────────────────────────────
# 调用点引用这些常量而不是字面量：拼错当场 AttributeError，不是"推送静默丢了"。
SERVER_STATUS_CHANGED = "web.server_status_changed"
PROJECT_UPDATE = "web.project_update"


@dataclass(frozen=True, slots=True)
class EventSpec:
    name: str
    description: str
    params_model: type[BaseModel]


_EVENTS: dict[str, EventSpec] = {}


def _register(name: str, description: str, params_model: type[BaseModel]) -> EventSpec:
    # 重名当场炸，理由同 registry.py：两条推送共用一个名字，表现是"前端把 A 的
    # 数据当成 B 的"，线上极难排查；import 期抛错则进程根本起不来。
    if name in _EVENTS:
        raise RuntimeError(f"WS 推送事件重复登记: {name}")
    spec = EventSpec(name=name, description=description, params_model=params_model)
    _EVENTS[name] = spec
    return spec


def registered() -> dict[str, EventSpec]:
    """只读快照，给文档/代码生成用。"""
    return dict(_EVENTS)


def publish(devbox_id: str, event: str, params: BaseModel) -> int:
    """把一条事件推给该 devbox（= 会话 id）的所有连接，返回推给了几个。

    比直接调 `hub.publish_devbox_event` 多两件事：

    - 校验 `params` 的类型和登记的形状对得上，写错事件名直接 KeyError；
    - `model_dump(mode="json")`：hub 内部走 `json.dumps`，pydantic 实例和
      datetime 这类值不转换就是 TypeError。

    推送是尽力而为——没有连接时返回 0，不抛错。
    """
    spec = _EVENTS[event]
    if not isinstance(params, spec.params_model):
        raise TypeError(
            f"事件 {event} 的 params 应为 {spec.params_model.__name__}，"
            f"实际是 {type(params).__name__}"
        )
    return hub.publish_devbox_event(devbox_id, event, params.model_dump(mode="json"))


_register(
    SERVER_STATUS_CHANGED,
    "预览状态变化（起沙箱、探测成功/失败）",
    ServerStatusChangedParams,
)
_register(
    PROJECT_UPDATE,
    "建会话后异步生成的标题/描述，已落库",
    ProjectUpdateParams,
)
