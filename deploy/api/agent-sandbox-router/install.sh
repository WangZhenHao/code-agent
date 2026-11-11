#!/usr/bin/env bash
# 安装 Sandbox Router（数据面）。控制面（controller + CRD）由
# ../agent-sandbox/install.sh 负责，两者都装齐 SDK 才连得上。
# 版本与命名空间的唯一真相在 ./kustomization.yaml —— 本脚本从那里读，不另存一份。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUSTOMIZATION="${HERE}/kustomization.yaml"
DRY_RUN="${DRY_RUN:-}"
DEPLOY=sandbox-router

NAMESPACE="$(sed -n 's/^namespace:[[:space:]]*//p' "$KUSTOMIZATION" | head -1)"
if [[ -z "$NAMESPACE" ]]; then
  echo "错误：没能在 ${KUSTOMIZATION} 里读到顶层 namespace: 字段" >&2
  exit 1
fi

echo "命名空间: ${NAMESPACE}（来自 kustomization.yaml）"

if [[ -n "$DRY_RUN" ]]; then
  echo "[dry-run] kubectl kustomize ${HERE}"
  kubectl kustomize "$HERE" >/dev/null
  echo "[dry-run] 清单渲染通过。"
  exit 0
fi

kubectl apply -k "$HERE"
kubectl -n "$NAMESPACE" rollout status deploy/"$DEPLOY" --timeout=180s

echo
echo "完成。核对（SDK 会 port-forward 这个服务名，必须存在）："
kubectl -n "$NAMESPACE" get svc/sandbox-router-svc 2>/dev/null \
  || echo "  警告：没找到 svc/sandbox-router-svc，SDK 会连不上"
