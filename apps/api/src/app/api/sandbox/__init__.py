"""沙箱领域：SDK 客户端封装（client/）与生命周期服务（service.py、sweeper.py）。

本包对外只暴露「按会话 id 的启停」这一层，分两类：

**用户动作触发**（service.py）——调用方按「还要不要这份数据」挑停法：

- `start_sandbox(id)`：启动或复用，返回 SDK 的 Sandbox 句柄（拿到就能直接
  `commands.run(...)`，不必再按 id 查一次），并把预览状态写回 sessions 表。
- `stop_sandbox(id)`：**暂停**，删 Pod 留卷，下次 start 唤回来 /workspace 还在。
  会话级的默认动作。
- `delete_sandbox(id)`：**销毁**，连 PVC 一起释放，不可逆。只给「确定不再需要
  数据」的路径用（如用户删会话）。

**无人触发时的兜底**（sweeper.py）——由 main.py 的 lifespan 启停，回收动作本身
复用 `stop_sandbox`，不另写一套：

- `start_sweeper()` / `stop_sweeper()`：起停进程内的定时调度器。
- `sweep_expired_previews()`：扫一遍 preview_time 超时的会话逐个回收。正常不用
  手工调，留着是给日志排查和将来手动触发用。

底层的 SDK 客户端（`sandbox_client`、`create_sandbox_for_id` 等）不在本层，
见子包 `app.api.sandbox.client`。

导入方式：
    from app.api.sandbox import start_sandbox, stop_sandbox, delete_sandbox
"""

# service 先于 sweeper：sweeper 内部要 import 本模块的 service，先落地前者，
# 后者那句 import 命中 sys.modules 里已完成的模块，不会撞上半初始化的包。
from app.api.sandbox.service import (
    delete_sandbox,
    start_sandbox,
    stop_sandbox,
)
from app.api.sandbox.sweeper import (
    start_sweeper,
    stop_sweeper,
    sweep_expired_previews,
)

__all__ = [
    "delete_sandbox",
    "start_sandbox",
    "start_sweeper",
    "stop_sandbox",
    "stop_sweeper",
    "sweep_expired_previews",
]
