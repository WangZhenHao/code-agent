# deploy/api/agent-sandbox-router — Sandbox Router（数据面）

[agent-sandbox](../agent-sandbox/) 的**数据面**。控制面只管「Pod 起没起」,真正把 SDK 的
HTTP 请求转发到具体沙箱 Pod 的是 router;SDK 侧
[`SandboxLocalTunnelConnectionConfig`](../../../apps/api/src/app/agents/client/sandbox.py)
会 `kubectl port-forward svc/sandbox-router-svc`,**没有这个 Service 就连不上**。

用的是上游的 **Go** router——Python 版已被标记为参考实现、推荐换 Go 版。Go 版保留了
同样的 `X-Sandbox-*` 头契约和 `sandbox-router-svc` 服务名,所以 SDK 无感。

## 装

```bash
./install.sh
# 或
kubectl apply -k .
```

前置:控制面已按 [../agent-sandbox/install.sh](../agent-sandbox/install.sh) 装好。
先看要执行什么:`DRY_RUN=1 ./install.sh`

## 装完的效果

命名空间 `my-agent-sandbox-system`(与控制面一致)里多了:

- `Deployment/sandbox-router`(2 副本)
- `Service/sandbox-router-svc`(ClusterIP:8080)—— **SDK 认的就是这个名字**
- `ServiceAccount` / `ClusterRole` / `ClusterRoleBinding` / `PodDisruptionBudget` 各一

验证(与 SDK 同款隧道):

```bash
NS=my-agent-sandbox-system
kubectl -n $NS port-forward svc/sandbox-router-svc 8080:8080 &
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/healthz   # 200
```

## 三处定制（都在 `kustomization.yaml`）

| 项 | 上游 | 本 overlay | 为什么 |
| --- | --- | --- | --- |
| 命名空间 | `agent-sandbox-system` | `my-agent-sandbox-system` | 跟控制面对齐;kustomize 会同步 ClusterRoleBinding 的 `subjects` |
| 镜像 tag | `:latest` | `:v1.0.4` | registry 上 **latest 是 404**,拉不到;顺便让版本可复现 |
| NetworkPolicy | 有 | **不引** | 见下 |

**为什么不要 NetworkPolicy**:上游那份 egress 只放行到 kube-system DNS 和
`namespace=default` 的 443,本地 OrbStack 上会挡掉 router→沙箱 Pod 的 **8888** 流量。
生产要用网络策略时单列它,并把 `namespaceSelector` 收紧到你的租户命名空间。

## 鉴权

默认 `--authz-mode=allow-all`,SDK 不带任何凭据,开箱即用。要收紧就得同时开
`--authz-mode=tokenreview` + 引上游的 `rbac-tokenreview.yaml`(grant `system:auth-delegator`),
并让调用方带 Bearer token——当前 SDK 用法没走到这一步。

## 注意

- **router 不创建沙箱**。它只按 `X-Sandbox-ID` 头去解析目标 Pod;目标不存在返回 502。
  沙箱本身由 SDK 的 `create_sandbox(warmpool=...)` 提交 `SandboxClaim` 创建,需要一个**已存在的
  warmpool**。所以路由通了 ≠ 能建沙箱,还差一个 `SandboxWarmPool`。
- **`--cache-enabled=true`**(上游默认)需要 `rbac.yaml` 里对 Pod 集群级 `get/list/watch` 的授权,
  已随本 overlay 装上。它让 router 走 PodIP 快路径、绕过 DNS,预热池沙箱(没有 per-sandbox
  Service、DNS 必然 NXDOMAIN)靠它才能被路由到。
- **一个集群一份**。`ClusterRole` / `ClusterRoleBinding` 按名字唯一,装到第二个命名空间会覆盖。
- **升级**:改 `kustomization.yaml` 里 URL 和 `images.newTag` 的版本(两处都从 `v1.0.4` 改),
  重跑脚本,并更新本文档。

## 参考

| 项 | 值 |
| --- | --- |
| 上游路径 | `sandbox-router/deploy/` @ `v1.0.4` |
| 镜像 | `registry.k8s.io/agent-sandbox/sandbox-router-go:v1.0.4` |
| 许可 | Apache-2.0 |
