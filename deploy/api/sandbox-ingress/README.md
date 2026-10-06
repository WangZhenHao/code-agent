# deploy/api/sandbox-ingress — 用域名访问沙箱

配一条**通配 Ingress**,让每个沙箱都能通过

```
http://<沙箱ID>.localtest.me/          ← 首选（公共 DNS → 127.0.0.1）
http://<沙箱ID>.k8s.orb.local/         ← 后备（OrbStack magic DNS）
```

直接访问(打开的固定是沙箱里 Next dev server 的 3000 端口)。

## 选哪个域名

| 域名 | 解析 | 何时用 |
| --- | --- | --- |
| `*.localtest.me` | 公共 DNS,所有子域 → `127.0.0.1`(IPv6 为正常回环 `::1`) | **首选**。不受本地代理污染,Chrome 首选 IPv6 也不挂。 |
| `*.k8s.orb.local` | OrbStack magic DNS | 后备。**两个坑**:① 会多解析出一个**不可达的 IPv6**(`fd07:…`),Chrome 优先试它导致请求 pending;② 与 Clash 等代理的 fake-ip 网段(默认 `198.18.0.1/16`)冲突时会污染 DNS 缓存。 |

**为什么 `localtest.me` 更稳**:它的所有子域名都解析到 `127.0.0.1`,而本机 80 端口就是
ingress-nginx(LoadBalancer 暴露在本机)。纯 IPv4 + 正常回环 IPv6,绕开了上面两个坑。

## 为什么这样设计

agent-sandbox 的 router 是**无状态**的,靠请求头 `X-Sandbox-ID` 决定转发给哪个沙箱。所以
**不需要给每个沙箱建 Ingress**(沙箱短命、名字和 IP 每次都变,那样既做不完也没意义),
只需**一条通配规则**覆盖所有沙箱:

```
浏览器 → <沙箱ID>.k8s.orb.local → OrbStack LB
       → Ingress(通配 *.k8s.orb.local)
       → nginx snippet 从 Host 剥出沙箱 ID ──► 注入 X-Sandbox-ID 头
       → svc/sandbox-router-svc → 目标沙箱 Pod:3000
```

新沙箱创建后**零额外配置**,域名立刻可用。

## 依赖(装一次)

### 1. ingress-nginx

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=180s
```

> **版本**:钉 `v1.15.1`。这是支持 k8s 1.35 的最后一个版本——ingress-nginx 已于 2026-03
> 停止维护(不再有安全补丁)。本地开发可用;生产请评估 Gateway API 等替代。

### 2. 放开 snippet 注解

默认门禁两层,都要开:

```bash
kubectl -n ingress-nginx patch configmap ingress-nginx-controller --type merge \
  -p '{"data":{"allow-snippet-annotations":"true","annotations-risk-level":"Critical"}}'
kubectl -n ingress-nginx rollout restart deploy/ingress-nginx-controller
```

- 不设 `allow-snippet-annotations` → snippet 被静默忽略
- 不设 `annotations-risk-level=Critical` → webhook 直接拒绝创建 Ingress
  (`ConfigurationSnippet contains risky annotation based on ingress configuration`)

### 3. 施加本 overlay

```bash
kubectl apply -f deploy/api/sandbox-ingress/index.yaml
```

## 验证

```bash
SB=<沙箱ID>   # 例如 python-sandbox-warmpool-sjzj4
curl -s -o /dev/null -w '%{http_code}\n' http://$SB.localtest.me/    # 期望 200
```

沙箱内需要先起 dev server(`commands.run("sh -c 'cd /workspace && nohup npm run dev > /tmp/next.log 2>&1 &'")`),
否则 3000 端口没人听,router 会返回 502。

## 坑 2:k8s.orb.local 的 IPv6 让 Chrome 转圈

**症状**:Safari / curl 能开,但 **Chrome 一直 pending**。

**根因**:`*.k8s.orb.local` 会解析出**两个**地址——

- `192.168.138.3`(IPv4,可达)
- `fd07:b51a:…`(IPv6,**不可达**,OrbStack 的内部 ULA 地址)

Chrome 的 Happy Eyeballs 会**优先试 IPv6**,连不上就卡住;Safari/curl 的回退更干脆。

**验证**:

```bash
dscacheutil -q host -a name <沙箱ID>.k8s.orb.local   # 会看到 ip_address 和 ipv6_address
curl -4 ...   # 秒回 200
curl -6 ...   # 卡满超时
```

**解法**:换 `*.localtest.me`(它的 IPv6 是正常回环 `::1`),或给 Chrome 传
`--host-resolver-rules` 强制绑 IPv4。

## 坑 1:本地代理和 OrbStack 抢网段

**症状**:`http://<id>.k8s.orb.local/` 返回 `Empty reply from server`(不是 connection refused);
或域名解析时有时无、最后解析不出来。

**根因**:**Clash / Surge 等代理的 TUN 模式**默认 `fake-ip-range: 198.18.0.1/16`,而
**OrbStack 也用 `198.18.0.0/15`** 做它到集群的隧道。两者撞车:

- 代理把 `*.k8s.orb.local` 当普通域名,发一个 fake-IP(`198.18.x`);
- 流量进代理隧道后,没有认领这个 fake-IP 的真实后端 → 连接被接受后**空响应**。
- 现象上 `198.18.x` 能连上(nc 通)但 `curl` 得到 Empty reply,而真实 LB VIP
  (`192.168.139.2`)反而好使。

**验证方法**:

```bash
ifconfig utun4 | grep inet          # 有 198.18.0.1 = 代理 TUN 在跑
netstat -rn | grep '^198\.18'       # 有到 utun4 的路由 = 冲突存在
```

**解法**(任选):

1. **把代理的 fake-ip-range 挪出 198.18**(如改 `198.19.0.1/16`)或切换代理模式 —— 根治。
2. 让代理对 `*.orb.local` 不走 fake-IP。
3. 临时关掉系统代理的 TUN。

## 说明

- 子域名**只能编码沙箱 ID**,编码不了端口,所以这里固定转发到 **3000**。要访问运行时的
  8888(`/execute` 等),得另配一条 Ingress 或在 snippet 里按需切换。
- `k8s.orb.local` 是 OrbStack 的 magic DNS,只在本机 OrbStack 环境有效。
- snippet 里用 `if ($host ~ ...)` 做正则提取——nginx 的 `if` 有坑(在 location 上下文里
  有陷阱),但 `set` 变量这种用法是安全的。
