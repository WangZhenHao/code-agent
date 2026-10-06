#!/usr/bin/env bash
# 安装 agent-sandbox 控制面（Sandbox CRD + controller）。
# 清单直接取自上游 release，不在仓库里 vendored，避免 850KB 的 CRD schema 淹掉 diff。
# 版本与命名空间的唯一真相在 ./kustomization.yaml —— 本脚本从那里读，不另存一份。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUSTOMIZATION="${HERE}/kustomization.yaml"
DRY_RUN="${DRY_RUN:-}"
DEPLOY=agent-sandbox-controller

# 从 kustomization.yaml 读命名空间，而不是让脚本自己维护一个变量——
# 双份真相正是最初 rollout status 报 "namespace not found" 的根因。
NAMESPACE="$(sed -n 's/^namespace:[[:space:]]*//p' "$KUSTOMIZATION" | head -1)"
if [[ -z "$NAMESPACE" ]]; then
  echo "错误：没能在 ${KUSTOMIZATION} 里读到顶层 namespace: 字段" >&2
  exit 1
fi

echo "命名空间: ${NAMESPACE}（来自 kustomization.yaml）"

if [[ -n "$DRY_RUN" ]]; then
  echo "[dry-run] kubectl kustomize ${HERE}"
  echo "[dry-run] kubectl apply -k ${HERE}"
  echo "[dry-run] kubectl -n ${NAMESPACE} rollout status deploy/${DEPLOY} --timeout=180s"
  kubectl kustomize "$HERE" >/dev/null
  echo "[dry-run] 清单渲染通过。"
  exit 0
fi

# kubectl kustomize 在 apply 前先把远程清单拉下来渲染，万一 URL 挂了会在这里
# 明确报错，好过 apply 到一半失败。
kubectl apply -k "$HERE"
kubectl -n "$NAMESPACE" rollout status deploy/"$DEPLOY" --timeout=180s

echo
echo "完成。核对："
kubectl get crd 2>/dev/null | grep -E 'agents\.x-k8s\.io' || echo "  警告：没找到 agents.x-k8s.io CRD"