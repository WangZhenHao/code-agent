# deploy/dashboard — Kubernetes Dashboard（集群后台管理）

官方 [Kubernetes Dashboard](https://github.com/kubernetes/dashboard)，给集群一个 Web 管理台：
看 Pod / Deployment / Service / 日志 / 事件 / CPU 内存，不用天天 `kubectl`。

## 装

```bash
./install.sh
```

脚本做三件事：`kubectl apply -k` 装官方清单 + 管理员账号，等 rollout，然后**打印登录 token**。

## 登录

- 地址：<https://localhost:30443>（OrbStack 把 NodePort 映射到 localhost；自签证书，浏览器告警选「继续」）
- 认证方式：**Token**（不是 kubeconfig，不要点那个）
- Token：**永久有效**，取自 `admin-user-token` Secret。随时重新取：

```bash
kubectl -n kubernetes-dashboard get secret admin-user-token -o jsonpath='{.data.token}' | base64 -d
```

> **为什么不是 `kubectl create token`**：那条路走 TokenRequest API，签的是带 `exp` 的短期
> token（默认 1 小时），**改不成永久**。永久 token 只能靠 `admin-user.yaml` 里那个
> `type: kubernetes.io/service-account-token` 的 Secret——它的 JWT 没有 `exp`。
> 代价是「泄露即永久有效」，生产集群别这么干。

## 文件

| 文件 | 作用 |
| --- | --- |
| `kustomization.yaml` | 引用上游 v2.7.0 清单 + 把 Service 改成 NodePort:30443 |
| `admin-user.yaml` | ServiceAccount + ClusterRoleBinding(cluster-admin) + 永久 token Secret |
| `install.sh` | apply → 等 rollout → 打印永久 token |

清单不 vendored 进仓库，版本以 `kustomization.yaml` 里的 tag 为唯一真相——换版本改那一行。

## 说明

- **admin-user 是 cluster-admin**，按开发集群用途给的。生产请换成只读 ClusterRole
  （`get/list/watch`），别把全权限 token 发出去。改 `admin-user.yaml` 的 `roleRef` 即可。
- **免登录（Skip）没开**。官方默认就关着，这里也保持关闭——开了等于集群任意人可写。
- **metrics**：`dashboard-metrics-scraper` 提供 CPU/内存曲线。它依赖集群有 metrics-server；
  OrbStack 自带，曲线能出。没有的话页面能开，只是资源图是空的。
- **卸载**：`kubectl delete -k .`。CRD 无，命名空间 `kubernetes-dashboard` 一并删即可。

> 生产环境请只暴露在内网/跳板机后，别直接怼公网。
