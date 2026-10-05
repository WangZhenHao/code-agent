"""会话表与消息表。

`Session` + `Messages` 放同一个文件，不放各自的模块：两者互相引用（Messages 有
session_id，Session 概念上有 messages 列表），跨文件就得靠字符串化的
`ForeignKey("sessions.id")` 或者延迟 import 绕循环，一个文件里最省事。

字段落地自 Prisma schema，几处需要说明的换算：

1. `status Int @default(0)` 在 Prisma 里**不是 enum**，是整数状态码，所以这里用
   `IntEnum` 落到 INTEGER 列，而不是像 Role 那样用 StrEnum 落 VARCHAR。
2. `title String` / `model String` 这类无长度上限的 Prisma String，这里按语义给了
   长度：title 255（chat/service.py 现在拿 message[:30] 当标题，留足余量）、
   model 64（`claude-sonnet-5` 这种名字不会更长）。
3. `parts Json?` 落 JSONB。这是项目第一次用 JSON 列——user.py 当初把 profile 退成
   String(2048) 是因为「格式等前端定」，但 parts 存的是模型输出的结构化片段
   （文本块、工具调用块等），String 长度和结构都撑不住，用 JSONB 是必要的。
4. Messages 只有 createdAt、没有 updatedAt，所以**不继承 TimestampMixin**，
   自己声明 created_at。消息是只追加的，updated_at 没有意义。
"""

from datetime import datetime
from enum import IntEnum, StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.ids import ID_LENGTH, new_id


class SessionStatus(IntEnum):
    """会话状态。整数状态码，落 INTEGER 列。

    删除是状态 0，不是独立的 is_deleted 列——整个表只有这一处表达「这条还在不在」，
    列表查询带 `status != SessionStatus.delete`（不要用 `== running`，那样以后
    加终态就会把新状态一起排除掉）。
    """

    delete = 0  # 已删除（软删）
    running = 1  # 进行中


class Role(StrEnum):
    """消息角色。"""

    user = "user"
    assistant = "assistant"
    error = "error"


class MessageStatus(StrEnum):
    """消息状态。interrupted = 流到一半断了（进程重启、客户端断开、上游 5xx）。"""

    complete = "complete"
    interrupted = "interrupted"


class PreviewStatus(StrEnum):
    """沙箱预览的状态。Prisma 里只给了 `@default(idle)`，其余值待补。

    ⚠️ 除了 idle，其余取值是从 `apps/admin/src/api/types.ts` 的
    `SandboxPhase = 'pending' | 'running' | 'succeeded' | 'failed' | 'terminating'`
    推的，与你 Prisma 里的 `enum PreviewStatus` 可能不一致，请核对。
    """

    idle = "idle"
    building = "building"
    running = "running"
    failed = "failed"


class Session(Base, TimestampMixin):
    """一次对话会话。

    id 本身就是 LangGraph 的 thread_id（仓库根 README 约定 #4「会话即 thread」），
    所以没有额外的 thread_id 列。也因此主键必须是 String 而不是自增 int——
    checkpointer 的 thread_id 是字符串。

    is_deleted 列已去掉：删除是 `status == SessionStatus.delete`（0）。列表查询带
    `status != SessionStatus.delete`，本轮不加全局 filter，等接接口时在 service 层
    显式写（和 user.py 一样不搞隐式魔法）。
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)

    title: Mapped[str] = mapped_column(String(255))
    title_image: Mapped[str | None] = mapped_column(String(2048), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # default 是 Python 端默认值（ORM insert 生效），server_default 是 DB 端默认值
    # （裸 SQL / 数据修复脚本 insert 也生效）。非空列两个都要给，只给 default 的话
    # 裸 SQL 会撞 NOT NULL。
    status: Mapped[int] = mapped_column(
        Integer, default=SessionStatus.running, server_default=text(str(SessionStatus.running.value))
    )
    # publish：是否已发布；views：浏览量
    publish: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    views: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    preview_port: Mapped[int | None] = mapped_column(Integer, default=None)
    # default 存枚举的 value 字符串（"idle"），与 String 列一致
    preview_status: Mapped[str] = mapped_column(
        String(16), default=PreviewStatus.idle, server_default=PreviewStatus.idle.value
    )
    preview_url: Mapped[str | None] = mapped_column(String(2048), default=None)

    git_repo_name: Mapped[str | None] = mapped_column(String(256), default=None)
    git_repo_url: Mapped[str | None] = mapped_column(String(2048), default=None)

    # ondelete="CASCADE"：用户注销时其会话一并清掉。DB 层做级联而不是 ORM 层
    # （不加 relationship + cascade="all, delete-orphan"），因为绕过 ORM 的
    # 删除/清理脚本也需要它。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        # 会话列表页的查询形态：where user_id = ? and status != delete order by updated_at desc
        Index("ix_sessions_user_id_updated_at", "user_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} title={self.title!r} status={self.status}>"


class Messages(Base):
    """会话里的一条消息。

    表名沿用 Prisma 的 `@@map("messages")`；类名也保持 `Messages`（复数）不改叫
    Message，是为了和前端/Prisma 侧对得上，避免以后对着两边 schema 打岔。
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))

    # 模型输出的结构化片段。JSONB 而非 JSON：需要按键/路径查询，且写入时
    # 会做去重和解析，读性能也更好。
    parts: Mapped[dict | list | None] = mapped_column(JSONB, default=None)

    # 这一轮耗时，毫秒
    duration: Mapped[int | None] = mapped_column(Integer, default=None)
    git_commit_sha: Mapped[str | None] = mapped_column(String(64), default=None)

    # 不继承 TimestampMixin：Prisma 里 Messages 只有 createdAt。
    # 但 onupdate 那半没有意义不代表 created_at 可以不要——没有它消息列表
    # 就只能按 id 排序，而 id 是随机的 cuid 不可排序。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # 拉某个会话的消息，按时间正序
        Index("ix_messages_session_id_created_at", "session_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Messages id={self.id} session_id={self.session_id} role={self.role}>"
