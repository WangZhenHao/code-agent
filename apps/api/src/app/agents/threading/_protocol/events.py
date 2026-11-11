"""事件通道识别、订阅过滤与 lifecycle 判定。

纯函数，无状态无 IO。`matches_subscription` 的形状由前端 SDK 的订阅参数决定
（`channels` / `namespaces` / `depth`），改之前先对照
[app/api/agent/schemas.py] 里 `SubscribeParams` 的说明。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeGuard


def is_record(value: Any) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict)


def segment_matches(filter_segment: str, event_segment: str) -> bool:
    if ":" in filter_segment:
        return filter_segment == event_segment
    return event_segment.split(":")[0] == filter_segment


def get_event_channel(event: dict[str, Any]) -> str:
    method = event["method"]
    # Python v3 已经把命名 custom 通道发成 `custom:<name>`。
    if method.startswith("custom:"):
        return method
    if method != "custom":
        return method
    data = event["params"]["data"]
    if is_record(data) and isinstance(data.get("name"), str):
        return f"custom:{data['name']}"
    return "custom"


def matches_subscription(event: dict[str, Any], params: dict[str, Any]) -> bool:
    """订阅过滤器：channels（含 `custom` 通配所有 `custom:*`）+ namespaces/depth。"""
    channel = get_event_channel(event)
    channels = params.get("channels")
    if (
        isinstance(channels, list)
        and channels
        and channel not in channels
        and not (channel.startswith("custom:") and "custom" in channels)
    ):
        return False

    namespaces = params.get("namespaces")
    if not isinstance(namespaces, list) or not namespaces:
        return True

    raw_namespace = event["params"].get("namespace")
    namespace = raw_namespace if isinstance(raw_namespace, list) else []

    depth = params.get("depth")
    for prefix in namespaces:
        if not isinstance(prefix, list):
            continue
        if len(prefix) > len(namespace):
            continue
        prefix_matches = all(
            segment_matches(segment, namespace[index] if index < len(namespace) else "")
            for index, segment in enumerate(prefix)
        )
        if not prefix_matches:
            continue
        if depth is None or len(namespace) - len(prefix) <= depth:
            return True
    return False


def is_after_replay_cursor(event: dict[str, Any], params: dict[str, Any]) -> bool:
    since = params.get("since")
    return not isinstance(since, int) or (event.get("seq") or -1) > since


def is_root_lifecycle(event: Mapping[str, Any], name: str) -> bool:
    """判断是否是根命名空间上的某类 lifecycle 事件（running/completed/...）。

    只认根命名空间：子图（codeAgent）跑完也会发一条 lifecycle completed，把它
    当终态会让客户端在外层图还在跑（后面还有 finish 节点）时就断开。
    """
    if event.get("method") != "lifecycle":
        return False
    params = event.get("params")
    if not is_record(params):
        return False
    namespace = params.get("namespace")
    if not isinstance(namespace, list) or len(namespace) != 0:
        return False
    data = params.get("data")
    if not is_record(data):
        return False
    return data.get("event") == name
