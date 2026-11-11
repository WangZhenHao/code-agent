"""工具调用记录表。

每次工具执行的结果落一行，SSE 只推 `tool_call_id` / `tool_name` / 参数 / 状态，
前端按 id 查这张表拿 output——大段工具输出（最长 30k 字符）不再塞进流、回放缓冲
和 `messages.parts` 各存一份。

`tool_call_id` 直接用 LangChain 的 `call_xxx` 当主键：它由模型输出生成、全局唯一，
天然就是幂等键——同一调用被重试时按 ON CONFLICT 覆盖，不会写出两行。
"""

from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ToolCallStatus(StrEnum):
    """工具调用状态。

    running 只在执行中短暂存在：进程崩溃后可能残留（没有 finally 跑完），
    这类行由 finish 节点统一收成 interrupted。
    """

    running = "running"
    success = "success"
    error = "error"
    interrupted = "interrupted"


class ToolCall(Base, TimestampMixin):
    """一次工具调用的参数与结果。"""

    __tablename__ = "tool_calls"

    tool_call_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    tool_name: Mapped[str] = mapped_column(String(64))

    # 模型给的调用参数。JSONB 而非 String：前端要按字段取值（bash 的 command、
    # edit_file 的 path），且长度不可预估。
    input: Mapped[dict | list | None] = mapped_column(JSONB, default=None)

    # 工具返回的文本（已按 MAX_OUTPUT_CHARS 截断）。running 时为空。
    output: Mapped[str | None] = mapped_column(Text, default=None)

    status: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        Index("ix_tool_calls_session_id_created_at", "session_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ToolCall id={self.tool_call_id} session_id={self.session_id} "
            f"tool={self.tool_name} status={self.status}>"
        )
