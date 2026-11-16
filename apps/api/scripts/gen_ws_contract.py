"""从 WS 推送事件注册表生成前端契约：TS 类型 + ws.md 的事件表。

单一事实源是 `app.api.ws.core.events` 里的 `_EVENTS`。本脚本只读不写业务代码，
产出两处，内容没变时零 diff：

    apps/web/src/lib/ws/generated/contract.ts            前端类型
    apps/api/src/app/api/ws/ws.md（两条标记之间的表格）  文档

用法（仓库根）：

    uv run --project apps/api python apps/api/scripts/gen_ws_contract.py
    uv run --project apps/api python apps/api/scripts/gen_ws_contract.py --check

`--check` 只比对不落盘，供 `make lint` / CI 防漂移。
"""

from __future__ import annotations

import argparse
import difflib
import sys
import types
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from app.api.ws.core.events import registered

REPO_ROOT = Path(__file__).resolve().parents[3]
TS_TARGET = REPO_ROOT / "apps/web/src/lib/ws/generated/contract.ts"
MD_TARGET = REPO_ROOT / "apps/api/src/app/api/ws/ws.md"

MARK_BEGIN = "<!-- gen:push-events -->"
MARK_END = "<!-- gen:push-events:end -->"

TS_PRIMITIVES: dict[type, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


def _union_members(tp: Any) -> tuple[list[Any], bool]:
    """拆 `A | B` / `Optional[A]`，返回 (非 None 分支, 是否含 None)。"""
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:
        members = list(get_args(tp))
        has_none = type(None) in members
        return [m for m in members if m is not type(None)], has_none
    return [tp], False


def ts_type(tp: Any, indent: int = 0) -> str:
    """pydantic 字段类型 → TS 类型表达式。

    只支持契约里实际用得到的几种；遇到别的**直接抛错**而不是退化成 `any`：
    生成出来的类型悄悄变成 any，等于没生成，还让人以为契约被检查过。
    """
    members, has_none = _union_members(tp)
    if len(members) == 1:
        rendered = _ts_single(members[0], indent)
    else:
        rendered = " | ".join(_ts_single(m, indent) for m in members)
    return f"{rendered} | null" if has_none else rendered


def _ts_single(tp: Any, indent: int) -> str:
    if tp in TS_PRIMITIVES:
        return TS_PRIMITIVES[tp]

    origin = get_origin(tp)
    if origin is Literal:
        return " | ".join(f'"{arg}"' for arg in get_args(tp))
    if origin in (list, tuple):
        (item,) = get_args(tp) or (Any,)
        return f"{ts_type(item, indent)}[]"
    if origin is dict:
        return "Record<string, unknown>"
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return ts_object(tp, indent)
    raise TypeError(f"生成器不认识这个类型: {tp!r}，请扩展 scripts/gen_ws_contract.py")


def ts_object(model: type[BaseModel], indent: int = 0) -> str:
    """嵌套对象按 2 空格缩进展开，输出直接就是 prettier 认得的合法 TS。"""
    fields = model.model_fields
    if not fields:
        return "Record<string, never>"

    pad = " " * indent
    inner = " " * (indent + 2)
    lines: list[str] = ["{"]
    for name, field in fields.items():
        lines.append(f"{inner}{name}: {ts_type(field.annotation, indent + 2)}")
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def render_ts() -> str:
    events = registered()
    names = list(events)
    union = " | ".join(f'"{n}"' for n in names)

    lines = [
        "// 由 apps/api/scripts/gen_ws_contract.py 生成，不要手改。",
        "// 重新生成：make gen-ws（改了 apps/api/src/app/api/ws/core/events.py 之后）。",
        "",
        f"export type WsPushEvent = {union}",
        "",
        "export interface WsPushParams {",
    ]
    for name in names:
        shape = ts_object(events[name].params_model, indent=2)
        lines.append(f'  "{name}": {shape}')
    lines.extend(
        [
            "}",
            "",
            "export const WS_PUSH_EVENTS: readonly WsPushEvent[] = [",
            *(f'  "{n}",' for n in names),
            "]",
            "",
        ]
    )
    return "\n".join(lines)


def render_md_table() -> str:
    events = registered()
    rows = [
        "| method | 何时发 | params |",
        "| --- | --- | --- |",
    ]
    for name, spec in events.items():
        shape = " ".join(ts_object(spec.params_model).split()).replace("|", "\\|")
        rows.append(f"| `{name}` | {spec.description} | `{shape}` |")
    return "\n".join(rows)


def replace_markdown_section(original: str, table: str) -> str:
    begin = original.find(MARK_BEGIN)
    end = original.find(MARK_END)
    if begin == -1 or end == -1 or end < begin:
        raise SystemExit(
            f"{MD_TARGET} 里找不到 {MARK_BEGIN} / {MARK_END} 标记，无法定位事件表"
        )
    head = original[: begin + len(MARK_BEGIN)]
    tail = original[end:]
    return f"{head}\n{table}\n{tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="只比对，不写文件；有差异则非零退出"
    )
    args = parser.parse_args()

    ts_text = render_ts()
    md_text = replace_markdown_section(MD_TARGET.read_text(), render_md_table())

    targets = [(TS_TARGET, ts_text), (MD_TARGET, md_text)]
    drift = False
    for path, new in targets:
        old = path.read_text() if path.exists() else ""
        if old == new:
            continue
        if args.check:
            drift = True
            rel = path.relative_to(REPO_ROOT)
            sys.stdout.writelines(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                )
            )
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new)
        print(f"wrote {path.relative_to(REPO_ROOT)}")

    if args.check and drift:
        print("\nWS 契约与生成物不一致，跑 make gen-ws 重新生成。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
