# WebSocket 接入指南

前后端只有三种消息，都是 JSON-RPC 2.0：

| 方向 | 形状 | 场景 |
|---|---|---|
| 前端 → 后端 | `{"jsonrpc":"2.0","id":6,"method":"...","params":{...}}` | 前端发请求 |
| 后端 → 前端（应答） | `{"jsonrpc":"2.0","id":6,"result":{...}}` | 对应上面那条的回复 |
| 后端 → 前端（推送） | `{"jsonrpc":"2.0","method":"...","params":{...}}` | 后端主动发，**没有 id** |

另外两种出错形态：

```json
{"jsonrpc":"2.0","id":6,"error":{"code":-32601,"message":"未知方法: xxx"}}
{"jsonrpc":"2.0","method":"ping","params":{"ts":1729999999999}}
```

---

## 前端发请求

### 案例 1：连接一次，之后随时发

`onopen` 是**每次建立连接时触发一次**，不是每次发消息都触发。连接建好后，
用户点一次按钮就 `send()` 一次，不需要再碰 `onopen`。

```ts
const token = localStorage.getItem("access_token");
const ws = new WebSocket(
  `wss://your-host/ws/devbox/${sessionId}?token=${encodeURIComponent(token)}`,
);

// 连接建立后只关心"以后怎么发"，不需要在 onopen 里发具体请求
ws.onopen = () => console.log("connected");

// 点一次发一条。id 每次自增，用来对应应答
let nextId = 1;
button.addEventListener("click", () => {
  ws.send(
    JSON.stringify({
      jsonrpc: "2.0",
      id: nextId++,
      method: "preview.status",
      params: {},          // 必须是对象，不支持位置参数数组
    }),
  );
});
```

**不要在点击时 `new WebSocket()`**——那会每点一次建一条连接，服务端每个连接
都会订阅一遍 devbox，还会各自跑心跳；连接数一多，`publish_devbox_event`
就会把同一条推送发 N 遍给同一个用户。

#### 点击比连接建立早怎么办

`CONNECTING` 状态下 `send()` 会抛 `InvalidStateError`。两种处理，任选其一：

```ts
// 做法 A：没连上就先排着，连上后一起发
const queue: string[] = [];
function sendRaw(text: string) {
  if (ws.readyState === WebSocket.OPEN) ws.send(text);
  else queue.push(text);
}
ws.onopen = () => {
  while (queue.length) ws.send(queue.shift()!);
};

// 做法 B：没连上就禁用按钮
button.disabled = true;
ws.onopen = () => (button.disabled = false);
```

#### 断线了怎么办

服务端 `--reload` 重启、网络抖动、空闲被代理掐断都会关连接。要么自己重连，
要么直接用 `ws.readyState` 拦住：

```ts
ws.onclose = (e) => {
  console.warn("closed", e.code, e.reason);
  // 4401 = 令牌失效，重连也没用，应该去重新登录
  // 其余（1006 / 1009 等）可以退避后重连
  if (e.code !== 4401) setTimeout(() => location.reload(), 3000); // 或自己重连
};
```

浏览器 `WebSocket` 构造函数**设不了请求头**，令牌只能走 `?token=`
（`?access_token=` 也认）。非浏览器客户端（Node / Python / 服务端脚本）可以走
`Authorization: Bearer <token>`，就不必把令牌写进 URL。

### 案例 2：带 id 的请求 + 等应答（Promise 封装）

```ts
let nextId = 1;
const pending = new Map<number, (msg: any) => void>();

function call(ws: WebSocket, method: string, params: Record<string, unknown> = {}) {
  const id = nextId++;
  return new Promise<any>((resolve, reject) => {
    pending.set(id, (msg) => {
      if (msg.error) {
        reject(new Error(`${msg.error.code}: ${msg.error.message}`));
      } else {
        resolve(msg.result);
      }
    });

    ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));

    // 超时兜底：拿不到应答就清掉，避免 pending 越积越多
    setTimeout(() => {
      if (pending.delete(id)) reject(new Error(`timeout: ${method}`));
    }, 10_000);
  });
}

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.id !== undefined) {
    const cb = pending.get(msg.id);
    if (cb) {
      pending.delete(msg.id);   // 先删再调，回调里抛异常也不会留下脏记录
      cb(msg);
    }
    return;
  }
  handlePush(msg);              // 没有 id = 推送
};

const status = await call(ws, "preview.status");
console.log(status.status, status.preview_url);
```

### 案例 3：发一条通知（不要应答）

请求里**不带 `id` 这个键**就是通知：后端照样执行 handler，但**不回包**。

```ts
ws.send(JSON.stringify({
  jsonrpc: "2.0",
  method: "preview.status",
  params: {},
}));
// 不会有任何应答回来，别在这里 await
```

注意 `"id": null`（键在、值为 null）**不是**通知——那会被当作「请用 null 作为 id 回我」，
照样收到应答。区分只看**有没有 `id` 这个键**。

### 案例 4：手工联调（websockets / wscat）

```python
# cd apps/api && uv run python - <<'PY' ... 见下一行的文件版本
import asyncio, json, websockets


async def main():
    url = "ws://localhost:8000/ws/devbox/<session_id>?token=<jwt>"
    async with websockets.connect(url) as ws:
        await ws.send(
            json.dumps(
                {"jsonrpc": "2.0", "id": 6, "method": "preview.status", "params": {}}
            )
        )
        print(await ws.recv())


asyncio.run(main())
```

或者：

```bash
wscat -c "ws://localhost:8000/ws/devbox/<session_id>?token=<jwt>"
> {"jsonrpc":"2.0","id":6,"method":"preview.status","params":{}}
```

发通知（不带 id）时服务端不回包，`recv()` 会一直等着——联调时别把「不回」
当成「连不上」。

### 发错了会收到什么

| 前端发了 | 收到 |
|---|---|
| `{"jsonrpc":"2.0","id":6,"method":"nope"}` | `error.code = -32601`「未知方法」 |
| `params` 里多一个键 / 类型不对 | `error.code = -32602`（`params` 模型是 `extra="forbid"`） |
| `jsonrpc` 不是 `"2.0"` | `error.code = -32600` |
| `not json` | `error.code = -32700`，`id = null` |
| `[{"jsonrpc":"2.0","id":1,"method":"preview.status"}]` | `error.code = -32600`「不支持批量请求」 |
| 二进制帧 | `error.code = -32600`「只能发送文本帧」 |
| 单帧超过 256 KiB（默认） | 连接被 **close 1009**，之后收不到任何消息 |
| 连发太快（单连接并发 > 32） | `error.code = -32002`，`id = null` |

握手阶段的失败是**关闭码**，不是 HTTP 错误（实现是「先 accept 再 close」，
理由见 `apps/api/src/app/api/ws/core/auth.py`）：

| 关闭码 | 含义 |
|---|---|
| 4401 | 没有令牌 / 令牌无效 / 过期 / 用户不存在 → 重新登录 |
| 4403 | Origin 不在允许列表 |
| 4404 | `devbox_id` 不存在、已删除、或不属于当前用户 |

---

## 后端怎么推

### 案例 5：最简推送

在任意服务端代码里调一个**同步**函数（不要 `await`）：

```python
from app.api.ws.core import hub

hub.publish_devbox_event(
    "k2x9ab1cd0ef", "preview.ready", {"url": "http://abc.localtest.me/"}
)
```

连着这个 session（devbox）的所有前端立刻收到：

```json
{"jsonrpc":"2.0","method":"preview.ready","params":{"url":"http://abc.localtest.me/"}}
```

返回值是推给了几个连接；返回 `0` 表示当前没人连着（不报错）。

### 案例 6：仓库里已有的真实例子

`apps/api/src/app/api/sandbox/service.py::_persist_preview` 每次写预览状态后推一条：

```python
from app.api.ws.core import hub as ws_hub
from app.api.ws.service import preview_params

try:
    ws_hub.publish_devbox_event(
        id,  # 这个 session 的所有连接
        "web.server_status_changed",  # 前端按这个字符串分发
        {
            "status": "ready" if preview_status == PreviewStatus.running else "idle",
            "preview_enable": "",
            "preview": preview_params(row),  # 和 preview.status 应答同一形状
        },
    )
except Exception:
    logger.warning("预览状态推送失败 id=%s", id, exc_info=True)
```

**要点**：
- 推送是尽力而为。没有连接时返回 0，不报错；包 `try/except` 是为了万一 `params`
  不可序列化，也不能让 start/stop 主流程失败。
- `params` 里放心塞嵌套 dict / list / None，内部会 `json.dumps`。
- `method` 是前端的唯一分发键，改名字等于改前端代码。

### 案例 7：在异步路由里推

`publish_devbox_event` 虽然是同步的，但内部只做「入队」，不阻塞，直接在 async
函数里调即可：

```python
from app.api.ws.core import hub

@router.post("/something")
async def do_something(...):
    result = await some_work()
    hub.publish_devbox_event(session_id, "work.done", {"result": result})
    return result
```

### 案例 8：从后台线程里推

不在事件循环线程里（比如 `asyncio.to_thread` 里跑的函数）时，要回到主循环：

```python
import asyncio

loop = asyncio.get_running_loop()  # 进线程前先拿到
await asyncio.to_thread(run_blocking_work)
loop.call_soon_threadsafe(
    hub.publish_devbox_event, session_id, "work.done", {"ok": True}
)
```

### 案例 9：加一个新的请求方法（前端能主动问）

推送是后端 → 前端；如果前端要**主动问**一个新东西，那是往 `methods/` 加 handler：

```python
# apps/api/src/app/api/ws/methods/file.py
from pydantic import BaseModel, ConfigDict

from app.api.ws.core.registry import rpc_method


class FileStatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class FileStatResult(BaseModel):
    path: str
    size: int


@rpc_method("file.stat", params_model=FileStatParams)
async def file_stat(ctx, params: FileStatParams) -> FileStatResult:
    # ctx.user / ctx.devbox_id 可用；也能用 ctx.notify(...) 推消息
    return FileStatResult(path=params.path, size=0)
```

然后在 `apps/api/src/app/api/ws/methods/__init__.py` 里 import 一次：

```python
from app.api.ws.methods import file, preview  # noqa: F401
```

漏了这一步的表现是方法存在但永远回 -32601。

前端调用：

```ts
await call(ws, "file.stat", { path: "" });
// → {"jsonrpc":"2.0","id":1,"result":{"path":"","size":0}}
```

---

## 前端怎么收

```ts
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  if (msg.id !== undefined) {
    // 应答
    pending.get(msg.id)?.(msg);
    return;
  }

  // 推送，按 method 分发
  switch (msg.method) {
    case "ping":
      return;                                  // 心跳，忽略即可
    case "web.server_status_changed":
      refreshPreview(msg.params);
      break;
    case "preview.ready":
      iframe.src = msg.params.url;
      break;
    default:
      console.warn("unknown push", msg.method, msg.params);
  }
};
```

**前端两条约定**：
1. 无 `id` 的消息一律**不回复**（JSON-RPC 规范要求）；有 `id` 的才去 `pending` 里找。
2. 收到不认识的 `method` 要静默忽略，不能报错——后端随时可能加新推送（比如 `ping`）。

---

## 方法命名约定

- 领域前缀 + 点号：`preview.status`、`file.stat`、`agent.run_started`
- 请求和推送分开两个命名空间，别撞车：请求 `preview.status`（前端主动问），
  推送 `web.server_status_changed`（沿用 Coze 的名字）
- 加新方法或推送时，在 `apps/api/src/app/api/ws/router.py` 模块 docstring 的
  「已注册方法」一节登记——ws 路由不进 OpenAPI，那份 docstring 是唯一文档

---

## 常见坑

| 现象 | 原因 |
|---|---|
| 前端收不到推送 | 没连上，或连的 `devbox_id` 和推送时传的 `session_id` 不一致。`publish_devbox_event` 返回 0 就是没人在线 |
| 多副本部署偶发收不到 | `hub` 是**进程内**的：`start_sandbox` 在 A 副本、WS 连接在 B 副本时，B 上的客户端收不到。单副本没问题；要跨副本就把 `hub.py` 内部换成 Redis Pub/Sub，调用方不用改 |
| 推送丢了 | 出站队列满时会丢弃通知（客户端不读）。状态类消息丢得起——前端重连后发一次 `preview.status` 就能补齐 |
| 前端发完请求拿不到应答 | 可能漏了 `id`（成了通知），或 `id` 用了字符串/数字混用导致 `pending` 对不上 |
| 握手失败只看到 `1006` | 之前关掉了 accept-then-close 的路径，浏览器就只能看到 1006。现在实现是先 accept 再带码 close，应该能拿到 4401/4403/4404 |
