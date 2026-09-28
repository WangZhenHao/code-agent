#!/usr/bin/env bash
# 安装 agent-sandbox 控制面（Sandbox CRD + controller）。
# 清单直接取自上游 release，不在仓库里 vendored，避免 850KB 的 CRD schema 淹掉 diff。
# 版本可复现性由 URL 路径里的 tag 保证。
set -euo pipefail

VERSION="${VERSION:-v1.0.4}"
MANIFEST="${MANIFEST:-sandbox-with-extensions.yaml}"
DRY_RUN="${DRY_RUN:-}"

NAMESPACE=agent-sandbox-system
DEPLOY=agent-sandbox-controller
BASE="https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}"

case "$MANIFEST" in
  sandbox.yaml|extensions.yaml|sandbox-with-extensions.yaml) ;;
  *) echo "MANIFEST 只能是 sandbox.yaml / extensions.yaml / sandbox-with-extensions.yaml，收到：$MANIFEST" >&2; exit 1 ;;
esac

URL="${BASE}/${MANIFEST}"
echo "版本:     ${VERSION}"
echo "清单:     ${MANIFEST}"
echo "控制器 ns: ${NAMESPACE}"

if [[ -n "$DRY_RUN" ]]; then
  echo "[dry-run] kubectl apply -f ${URL}"
  echo "[dry-run] kubectl -n ${NAMESPACE} rollout status deploy/${DEPLOY} --timeout=180s"
  exit 0
fi

# 先探一下 URL 是否存在，好在 kubectl 之前给出更清楚的报错。
# 用 HEAD 只探存在性，不下整个文件（最大的清单 428KB）。
# 探测失败不算数：有些网络/代理环境不允许 HEAD（GitHub 会 302 到 CDN，也许被拦），
# 这时 alert 一句就继续，让真正的 kubectl apply 决定成败。
if ! curl -fsSLI "$URL" -o /dev/null 2>/dev/null; then
  echo "提示：探测 ${URL} 没成功（可能只是环境不允许 HEAD），继续尝试 apply。" >&2
fi

kubectl apply -f "$URL"
kubectl -n "$NAMESPACE" rollout status deploy/"$DEPLOY" --timeout=180s

echo
echo "完成。核对："
kubectl get crd 2>/dev/null | grep -E 'agents\.x-k8s\.io' || echo "  警告：没找到 agents.x-k8s.io CRD"
