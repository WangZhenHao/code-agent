#!/usr/bin/env bash
# 安装 Kubernetes Dashboard 后台管理，并打印登录 token。
# 清单取自上游 release（见 ./kustomization.yaml），本脚本只负责 apply + 等待 + 发 token。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN="${DRY_RUN:-}"
NS=kubernetes-dashboard
DEPLOY=kubernetes-dashboard
NODEPORT=30443

if [[ -n "$DRY_RUN" ]]; then
  echo "[dry-run] kubectl apply -k ${HERE}"
  kubectl kustomize "$HERE" >/dev/null
  echo "[dry-run] 清单渲染通过。"
  exit 0
fi

kubectl apply -k "$HERE"

# metrics-scraper 慢一点，但 dashboard 主容器起来页面就能开，只等它。
kubectl -n "$NS" rollout status deploy/"$DEPLOY" --timeout=180s

echo
echo "== 访问地址 =="
echo "  https://localhost:${NODEPORT}      （自签证书，浏览器告警点继续即可）"
echo "  或    kubectl -n ${NS} port-forward svc/${DEPLOY} 8443:443"

echo
echo "== 登录 token（永久，复制粘贴到登录页）=="
# 取自 admin-user-token Secret（见 admin-user.yaml）。它是 legacy 类型
# service-account-token，JWT 里没有 exp，不会过期——不像 `kubectl create token`
# 签的短期 token。改了 ServiceAccount 或删了 Secret 才会失效。
kubectl -n "$NS" get secret admin-user-token -o jsonpath='{.data.token}' | base64 -d
echo