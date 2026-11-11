#!/usr/bin/env bash
# 装 ingress-nginx + 开放 snippet + 施加通配 Ingress，让 <沙箱ID>.k8s.orb.local 可用。
# 幂等：重复跑不会重复创建。详见 ./README.md。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN="${DRY_RUN:-}"
INGRESS_NGINX_VERSION=v1.15.1
NS=ingress-nginx

if [[ -n "$DRY_RUN" ]]; then
  echo "[dry-run] kubectl apply -f .../controller-${INGRESS_NGINX_VERSION}/deploy/static/provider/cloud/deploy.yaml"
  echo "[dry-run] kubectl -n ${NS} patch configmap ingress-nginx-controller（开 snippet + risk-level）"
  echo "[dry-run] kubectl apply -f ${HERE}/index.yaml"
  exit 0
fi

echo "== 1/3 安装 ingress-nginx ${INGRESS_NGINX_VERSION} =="
kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-${INGRESS_NGINX_VERSION}/deploy/static/provider/cloud/deploy.yaml"
kubectl -n "$NS" rollout status deploy/ingress-nginx-controller --timeout=180s

echo
echo "== 2/3 开放 snippet 注解（默认两层门禁都要开）=="
kubectl -n "$NS" patch configmap ingress-nginx-controller --type merge \
  -p '{"data":{"allow-snippet-annotations":"true","annotations-risk-level":"Critical"}}'
kubectl -n "$NS" rollout restart deploy/ingress-nginx-controller
kubectl -n "$NS" rollout status deploy/ingress-nginx-controller --timeout=120s

echo
echo "== 3/3 施加通配 Ingress =="
kubectl apply -f "${HERE}/index.yaml"

echo
echo "完成。验证："
echo "  SB=<沙箱ID>"
echo "  curl -s -o /dev/null -w '%{http_code}\\n' http://\$SB.k8s.orb.local/   # 期望 200"
echo
echo "若返回 'Empty reply from server'，是本地代理 fake-IP 与 OrbStack 的 198.18 段撞车——"
echo "见 ./README.md 的「坑」一节。"
