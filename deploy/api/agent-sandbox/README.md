# deploy/api/agent-sandbox — Agent Sandbox 控制面

给集群装上 `Sandbox` CRD 与控制器，来源是
[kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox) 官方发布的安装 manifest。

仓库里**不放上游 manifest**（合计 ~850KB，最大的 428KB 全是 CRD 的 OpenAPI schema），
只放安装脚本 + 一份 [kustomization.yaml](kustomization.yaml) overlay：清单按 URL 现拉，
版本钉在 URL 路径里，本项目的定制（命名空间）走 overlay，上游内容保持原样。

## 安装

```bash
deploy/api/agent-sandbox/install.sh
# 等价于
kubectl apply -k deploy/api/agent-sandbox/
```

脚本做两件事：施加 overlay，然后等 controller rollout 完成。

命名空间、版本、用哪个 manifest **都只在 [`kustomization.yaml`](kustomization.yaml) 里改**，
脚本从那里读，不自己存一份：

```yaml
namespace: my-agent-sandbox-system   # ← 换命名空间改这行
resources:
  - https://github.com/kubernetes-sigs/agent-sandbox/releases/download/v1.0.4/sandbox-with-extensions.yaml
```

先看要执行什么：`DRY_RUN=1 deploy/api/agent-sandbox/install.sh`

## 装完的效果

集群里多了：

- **Namespace** `my-agent-sandbox-system` —— 控制器住的命名空间（上游默认 `agent-sandbox-system`，本项目覆盖）。
- **4 个 CRD**（集群级，装一次全局可用）：
  - `sandboxes.agents.x-k8s.io`（核心，`v1beta1`）
  - `sandboxclaims.extensions.agents.x-k8s.io`
  - `sandboxtemplates.extensions.agents.x-k8s.io`
  - `sandboxwarmpools.extensions.agents.x-k8s.io`
- **控制器** `Deployment/agent-sandbox-controller`（1 副本，`--leader-elect=true`）。
- `ClusterRole` / `ClusterRoleBinding` / `ServiceAccount` / `Service` 各一。

验证：

```bash
NS=my-agent-sandbox-system
kubectl -n $NS rollout status deploy/agent-sandbox-controller
kubectl get crd | grep -E 'agents\.x-k8s\.io'
kubectl get sandboxes -A                                          # 空列表且不报错 = CRD 生效
kubectl -n $NS logs deploy/agent-sandbox-controller | grep -c forbidden   # 应为 0
```

## 参考

| 项 | 值 |
| --- | --- |
| 上游仓库 | https://github.com/kubernetes-sigs/agent-sandbox |
| 版本 | **v1.0.4** |
| 控制器镜像 | `registry.k8s.io/agent-sandbox/agent-sandbox-controller:v1.0.4` |
| 许可 | Apache-2.0 |

三个 manifest 三选一（互斥，改 `kustomization.yaml` 里 `resources:` 的文件名）：

| 文件 | 内容 |
| --- | --- |
| `sandbox.yaml` | 核心：`Sandbox` CRD + controller |
| `extensions.yaml` | 扩展：Template / Claim / WarmPool + 扩展 controller（**要求核心已装**） |
| `sandbox-with-extensions.yaml` | 前两者合并版（当前使用） |

`Sandbox` 的 `spec` 共 6 个字段：`podTemplate`、`operatingMode`（`Running`/`Suspended`）、
`service`、`volumeClaimTemplates`、`shutdownPolicy`（默认 `Retain`）、`shutdownTime`。

## 注意

- **一个集群只能装一份控制面**。`ClusterRole` / `ClusterRoleBinding` 集群级且按名字唯一，
  装到第二个命名空间会覆盖第一份的绑定、抢走其权限。换命名空间要先把旧的删干净。
- **为什么用 kustomize 而不是 sed**：上游把 `agent-sandbox-system` 硬编码在 6 处，其中两处是
  `ClusterRoleBinding` 的 `subjects[].namespace`。只改 `metadata.namespace` 会让 SA 和授权
  对不上、RBAC 失效（控制器刷 `cannot list resource ... at the cluster scope`）。
  kustomize 的 `namespace:` 转换器会自动同步 subjects。
- 控制器的 `Deployment` 没配 resources，是 BestEffort，节点内存吃紧时最先被驱逐。
- **升级**：改 `kustomization.yaml` 里 `resources:` 的版本路径（`v1.0.4` → `v1.0.5`），重跑脚本，
  并更新本文档顶部的版本号。升级前先看上游 release notes 有无 CRD 字段删除/重命名。

## 与本项目的关系

本项目现在由 [sandbox-image/index.yaml](../sandbox-image/index.yaml) 定义沙箱的「模板与约束」——
它是**模板不是 Deployment**，真正的沙箱 Pod 由 `apps/api` 的沙箱层按会话动态创建。
引入 agent-sandbox 是为了把「Pod 生命周期」交给 CRD 控制器，换来裸 Pod 没有的：
稳定身份 + 持久存储、暂停/恢复、预热池。

**边界**：agent-sandbox 只管到「Pod 起没起、活没活」，**不碰代码执行**——容器内读写文件、跑命令
仍是 `apps/api` 的沙箱层负责（`exec` 进容器）。core 约定 1（沙箱唯一入口）不变。

**当前状态**：`apps/api` 侧的沙箱层尚未存在，也就谈不上提交 `Sandbox` CR。
切换是独立的一步，涉及 RBAC 调整（API 的 SA 要拿到 `sandboxes` / `sandboxclaims` 权限）。
