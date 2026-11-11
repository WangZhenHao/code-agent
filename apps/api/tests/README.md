# 测试

**完整镜像 `src/app`**：测试文件的路径 = 被测文件在 `src/app` 下的路径，只把
`src/app` 换成 `tests`、文件名前面加 `test_`。

```
src/app/api/agent/service.py   →  tests/api/agent/test_service.py
src/app/agents/tools/guard.py  →  tests/agents/tools/test_guard.py
```

所以新增测试的落点是**算出来的，不是选的**；文件名里不带 `agent_` / `chat_`
这类前缀来消歧，同名模块靠目录分开。

例外只有两类，都放在就近的层级：

- 一个模块要按场景拆成多个文件时，文件名取场景名（`tests/agents/test_graphs.py`
  测的是 `agents/graphs.py`，和它同层，不建单独目录）；
- 跨模块的集成型测试（真起 app、跑整张图）将来放 `tests/integration/`，
  不和单元测试混。

## 跑法

必须在 `apps/api` 下执行（`python -m` 从 cwd 起算，`app` 包才 import 得到）。

```bash
# 全部（Makefile 的 make test 就是这个）
uv run python -m unittest discover -s tests

# 某个包
uv run python -m unittest discover -s tests/api/agent
uv run python -m unittest discover -s tests/api/user/code

# 单个文件 / 单个用例
uv run python -m unittest tests.api.agent.test_service
uv run python -m unittest tests.api.agent.test_service.AgentCommandTestCase.test_empty_parts_is_422
```

用 unittest 而不是 pytest：项目**没有** pytest 依赖，测试文件也都是
`unittest.TestCase`。每层目录的 `__init__.py` 是必需的——unittest 的 discover
只会递归进 import 得进来的子目录，缺一个，那棵子树下的用例会**静默消失**
（不报错，只是少跑）。

## 约定

- **全部离线**。不连 Postgres / Redis / K8s 沙箱，不起带 checkpointer 的图。
  外部依赖用假对象（见 `tests/api/agent/test_service.py` 的 `FakeSession` /
  `FakeThreadSession`、`tests/agents/tools/test_tools.py` 的 `FakeSandbox`）。
- **不做真实时间等待**。TTL / 冷却这类时间语义用 `mock.patch` 推
  `time.monotonic`，不要 `sleep`。
- **注释写清「为什么」**：每个断言背后对应哪条线上事故或设计约束，比断言本身
  更重要——测试改红时，读注释才知道是代码错了还是约束变了。
- **断言行为，不断言实现**。比如 plan 模式的只读工具集是写死的名字集合，而不是
  从源码 import 那个常量——常量一改断言跟着变，等于没测。

## 目录

| 测试 | 被测对象 |
|---|---|
| `api/agent/test_router.py` | `api/agent/router.py`：路径参数绑定、SSE 响应头、鉴权 |
| `api/agent/test_service.py` | `api/agent/service.py`：commands / stream / abort 的编排与副作用顺序 |
| `api/chat/test_create.py` | `api/chat/service.py` 的 `create_chat`：建会话与起第一轮的事务边界 |
| `api/user/code/test_code_store.py` | `api/user/code/code_store.py`：验证码冷却、单次消费、失败计数 |
| `api/user/code/test_phone.py` | `api/user/code/phone.py`：手机号归一化（所有写法收敛到同一裸号） |
| `agents/test_graphs.py` | `agents/graphs.py`：条件边、分支汇聚、finish 落库状态、图懒编译 |
| `agents/tools/test_tools.py` | `agents/tools/`：bash / read / write / edit / glob / grep / skill |
| `agents/tools/test_guard.py` | `agents/tools/guard.py`：plan 模式 bash 只读白名单 |
| `agents/helper/abort_agent/test_abort.py` | `agents/helper/abort_agent/`：run 注册表、消息缓冲、中止赛跑 |

## 还没有测试的部分

记在这里，避免"以为覆盖了"：

- `security.py`（JWT 签发/校验）、`db/ids.py`、`settings.py`——都是纯函数，
  补起来最快，成本最低；
- `agents/threading/`（`event_bus` / `thread_session`）——需要假 Redis；
- `agents/helper/middleware.py`（`TrackingSummarization`）、`message_persistence.py`；
- `api/session/`、`api/sandbox/`、`api/user/service.py`。
