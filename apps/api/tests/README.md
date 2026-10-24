# 测试

按源码目录镜像组织：`tests/api/` 对应 `src/app/api/`，`tests/agents/` 对应
`src/app/agents/`。加新测试时放到被测模块那一侧，不要平铺在 `tests/` 根下。

## 跑法

```bash
# 全部（Makefile 里的 make test 就是这个）
uv run python -m unittest discover -s tests

# 单层
uv run python -m unittest discover -s tests/api
uv run python -m unittest discover -s tests/agents

# 单个文件 / 单个用例
uv run python -m unittest tests.api.test_agent_service
uv run python -m unittest tests.api.test_agent_service.AgentCommandTestCase.test_empty_parts_is_422
```

用 unittest 而不是 pytest：项目**没有** pytest 依赖，测试文件也都是
`unittest.TestCase`。目录里两个 `__init__.py` 是必需的——unittest 的
discover 只会递归进 import 得进来的子目录，缺了它们下面一个用例都找不到。

## 约定

- **全部离线**。不连 Postgres / Redis / K8s 沙箱，不起图带 checkpointer。
  外部依赖用假对象（见 `test_agent_service.py` 的 `FakeSession` /
  `FakeThreadSession`、`test_tools.py` 的 `FakeSandbox`）。
- **不做真 IO 时间的等待**。TTL / 冷却这类时间语义用 `mock.patch` 推
  `time.monotonic`，不要 `sleep`。
- **注释写清「为什么」**：每个断言背后对应哪条线上事故或设计约束，比断言本身
  更重要——测试改红的时候，读注释才知道是代码错了还是约束变了。

## 目录

### `tests/api/`

| 文件 | 被测对象 |
|---|---|
| `test_agent_router.py` | `api/agent/router.py`：路径参数绑定、SSE 响应头、鉴权 |
| `test_agent_service.py` | `api/agent/service.py`：commands / stream / abort 的编排与副作用顺序 |
| `test_chat_create.py` | `api/chat/service.py` 的 `create_chat`：建会话与起第一轮的事务边界 |
| `test_code_store.py` | `api/user/code/code_store.py`：验证码的冷却、单次消费、失败计数 |
| `test_phone.py` | `api/user/code/phone.py`：手机号归一化（所有写法必须收敛到同一裸号） |

### `tests/agents/`

| 文件 | 被测对象 |
|---|---|
| `test_graphs.py` | `agents/graphs.py`：条件边、分支汇聚、finish 的状态落库、图懒编译 |
| `test_tools.py` | `agents/tools/`：bash / read / write / edit / glob / grep / skill |
| `test_guard.py` | `agents/tools/guard.py`：plan 模式 bash 只读白名单 |
| `test_abort.py` | `agents/helper/abort_agent/`：run 注册表、消息缓冲、中止赛跑 |
