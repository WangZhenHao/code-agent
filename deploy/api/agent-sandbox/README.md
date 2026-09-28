# deploy/api/agent-sandbox — Agent Sandbox 控制面

沙箱的**控制面**。给集群装上 `Sandbox` CRD 与控制器，来源是
[kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox) 官方发布的安装 manifest。

**这里不放 yaml，只有一个安装脚本** —— 清单直接用上游 URL 装。理由：

- 上游三个 manifest 合计 ~850KB（最大的 428KB 全是 CRD 的 OpenAPI schema），进仓库只会把 diff 淹掉，review 时也没人会真去读。
- 版本号已经钉在 URL 路径里（`releases/download/v1.0.4/`），可复现性由 URL 保证，不需要靠 vendored 文件保证。
- 升级时不用改文件，只改下面的 `VERSION` 一个变量。

## 上游信息

| 项 | 值 |
| --- | --- |
| 仓库 | https://github.com/kubernetes-sigs/agent-sandbox |
| 版本 | **v1.0.4**（2026-09-24 发布） |
| 安装方式 | `kubectl apply -f`（非 Helm） |
| 控制器镜像 | `registry.k8s.io/agent-sandbox/agent-sandbox-controller:v1.0.4` |
| 控制器命名空间 | `agent-sandbox-system` |
| 许可 | Apache-2.0 |

## 安装

```bash
deploy/api/agent-sandbox/install.sh
```

脚本做两件事：按选定的 manifest apply，然后等 controller rollout 完成。

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `VERSION` | `v1.0.4` | 上游 release tag，改这个就是升级/回滚 |
| `MANIFEST` | `sandbox-with-extensions.yaml` | 三个 manifest 三选一，见下表 |
| `DRY_RUN` | 空 | 设为 `1` 只打印命令，不实际 apply |

```bash
# 只装核心
MANIFEST=sandbox.yaml deploy/api/agent-sandbox/install.sh

# 先看要执行什么
DRY_RUN=1 deploy/api/agent-sandbox/install.sh
```

## 三个 manifest 怎么选

三者是**互斥**的选择，不是叠加，只能挑一个：

| 文件 | 内容 | 适用 |
| --- | --- | --- |
| `sandbox.yaml` | 核心：`Sandbox` CRD + controller | 只需要「一会话一沙箱」，本项目当前够用 |
| `extensions.yaml` | 扩展：`SandboxTemplate` / `SandboxClaim` / `SandboxWarmPool` CRD + 扩展 controller | 核心之上加模板、预热池（**要求核心已安装**） |
| `sandbox-with-extensions.yaml` | 前两者的合并版 | 图省事，一次装全（上游推荐） |

装合并版就不要再单独 apply 另外两个，否则同一批 CRD / ClusterRole 会重复提交。

## 装了之后集群里多了什么

- **Namespace** `agent-sandbox-system` —— 控制器自己住的地方。
- **CRD**（集群级，装一次全局可用）：
  - `sandboxes.agents.x-k8s.io`（核心，`v1beta1`）
  - `sandboxclaims.extensions.agents.x-k8s.io`
  - `sandboxtemplates.extensions.agents.x-k8s.io`
  - `sandboxwarmpools.extensions.agents.x-k8s.io`
- **控制器** `Deployment/agent-sandbox-controller`（`--leader-elect=true`，指标端口 8080/8081）。
- `ClusterRole` / `ClusterRoleBinding` / `ServiceAccount` / `Service` 各一。

`Sandbox` 的 `spec` 很薄，共 6 个字段：

| 字段 | 说明 |
| --- | --- |
| `podTemplate` | 本质是一份 Pod spec（容器、资源、`runtimeClass` 等） |
| `operatingMode` | `Running`（默认）/ `Suspended`，暂停与恢复 |
| `service` | bool，是否为该沙箱创建 headless Service（提供稳定网络身份） |
| `volumeClaimTemplates` | PVC 模板，让 `workspace` 跨重启存活 |
| `shutdownPolicy` | 默认 `Retain`，可选 `Delete` |
| `shutdownTime` | 定时收尾时间（date-time） |

## 验证

```bash
kubectl get ns agent-sandbox-system
kubectl -n agent-sandbox-system rollout status deploy/agent-sandbox-controller
kubectl get crd | grep -E 'agents\.x-k8s\.io'
kubectl get sandboxes -A          # 空列表且不报错，说明 CRD 生效
```

## 与本项目的关系

本项目现在由 [deploy/api/sandbox-image/index.yaml](../sandbox-image/index.yaml) 定义沙箱的「模板与约束」——
注意它是**模板不是 Deployment**，真正的沙箱 Pod 由 `apps/api` 的沙箱层（`apps/api/src/app/`，
规划中的 `sandbox/kubernetes.py`）按会话动态创建。引入 agent-sandbox
是为了把「Pod 生命周期」交给 CRD 控制器，换来裸 Pod 没有的几件事：

- **稳定身份 + 持久存储** —— 沙箱重启后 hostname / 网络标识不变，`workspace` 可以挂 PVC 跨重启存活（现在是 `emptyDir`，Pod 删掉即消失）。
- **暂停 / 恢复** —— `operatingMode: Suspended` 比反复删建 Pod 更省事。
- **预热池** —— `SandboxWarmPool` 把「等 Pod 就绪」的秒级延迟挪到用户点开对话之前。

**边界的划法**：agent-sandbox 只管到「Pod 起没起、活没活」这一层，**不碰代码执行**。
容器内读写文件、跑命令仍然是 `apps/api` 的沙箱层负责（`exec` 进容器），`Sandbox` 的
`podTemplate` 就是给那段代码做样板用的。core 约定 1（沙箱唯一入口）不变。

**当前状态**：`apps/api` 侧的沙箱层**尚未**存在（`src/app/` 下还没有 `sandbox/` 模块），
也就谈不上提交 `Sandbox` CR。切换是独立的一步，涉及 `deploy/sandbox/` 的重写与 RBAC 调整
（API 的 SA 要拿到 `sandboxes` / `sandboxclaims` 的权限），届时再改。

## 注意

- **本项目自己的定制不写在这里**。namespace、ResourceQuota、NetworkPolicy、沙箱镜像
  这些写在 [deploy/api/sandbox-image/index.yaml](../sandbox-image/index.yaml)，上游 manifest 保持原样不动。
- `extensions.yaml` 里的 controller 与核心 controller **同名同命名空间**
  （`agent-sandbox-controller`），`sandbox-with-extensions.yaml` 也是；这是上游的合并方式，
  单独叠加安装才会冲突，按上表三选一即可。
- agent-sandbox 是**编排层不是隔离层**：真正的隔离靠 `RuntimeClass`（gVisor / Kata）。
  不配 `runtimeClass` 时，`Sandbox` 里的容器与普通 Pod 是同一个隔离级别。
- 控制器的 `Deployment` **没有配 resources**，是 BestEffort 优先级，节点内存吃紧时最先被驱逐。
  本地 kind / OrbStack 单节点集群上尤其明显，可以按需补 requests。
- 控制器默认 `--leader-elect=true`，apiserver 短暂不可达（宿主机休眠、集群过载）会触发
  `leader election lost` 并重启。这是预期行为，但重启次数会累积，别把它当异常。
- 升级前先看上游 release notes 里有没有 CRD 字段的删除或重命名 —— CRD 一旦装错版本，
  已有的 `Sandbox` 资源可能直接被拒。

## 升级

改 `VERSION` 然后重跑脚本即可：

```bash
VERSION=v1.0.5 deploy/api/agent-sandbox/install.sh
```

升级后把本文档顶部「上游信息」表里的版本号一起更新。
