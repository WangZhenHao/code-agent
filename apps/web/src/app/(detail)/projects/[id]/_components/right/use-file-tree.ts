"use client"

/**
 * 文件树的取数逻辑：`file.stat` 懒加载。
 *
 * 初始只拉根目录一层，展开某个目录时才 `file.stat(path)` 拉它的直接子项。
 * 后端 `FileChild` 不带 path，所以节点 id 用相对路径（根为 `""`）自己拼——
 * 这同时解决了 React key 跨目录撞车（原来 `id === name`）。
 *
 * react-arborist 4.x 用 `isLeaf = !Array.isArray(children)` 判断叶子
 * （`node-api.js`），目录必须带 `children` 数组才可展开；「子项加载过没有」
 * 另用 `loadedPaths` 记，不能只看 `children.length === 0`（空目录也是 0）。
 */

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { useWsRequest } from "@/lib/ws/request"
import type { WsRequestResult } from "@/lib/ws/generated/contract"

export type FileNode = {
  /** 相对 `/workspace` 的路径；根目录为空串 */
  id: string
  name: string
  type: "folder" | "file"
  /** 只有目录有；初始 `[]` 占位，展开时替换成真实子项 */
  children?: FileNode[]
}

type FileStatResult = WsRequestResult["file.stat"]
type FileChild = NonNullable<FileStatResult["children"]>[number]

/** 后端不保证顺序（SDK list 原样返回），这里统一目录在前、同类型按名字排。 */
function sortEntries(entries: FileChild[]): FileChild[] {
  return [...entries].sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

function toNode(parentPath: string, entry: FileChild): FileNode {
  const path = parentPath ? `${parentPath}/${entry.name}` : entry.name
  return {
    id: path,
    name: entry.name,
    type: entry.isDirectory ? "folder" : "file",
    children: entry.isDirectory ? [] : undefined,
  }
}

function toNodes(parentPath: string, entries: FileChild[]): FileNode[] {
  return sortEntries(entries).map((entry) => toNode(parentPath, entry))
}

/** 不可变替换：按 id 找到节点，换上新的 children；找不到就原样返回。 */
function replaceChildren(
  nodes: FileNode[],
  id: string,
  children: FileNode[]
): FileNode[] {
  let changed = false
  const next = nodes.map((node) => {
    if (node.id === id) {
      changed = true
      return { ...node, children }
    }
    if (!node.children?.length) return node
    const replaced = replaceChildren(node.children, id, children)
    if (replaced === node.children) return node
    changed = true
    return { ...node, children: replaced }
  })
  return changed ? next : nodes
}

export function useFileTree() {
  const { invoke } = useWsRequest()
  const [tree, setTree] = useState<FileNode[]>([])
  const [loadedPaths, setLoadedPaths] = useState<ReadonlySet<string>>(new Set())
  const [loadingPaths, setLoadingPaths] = useState<ReadonlySet<string>>(
    new Set()
  )
  const [rootLoading, setRootLoading] = useState(false)
  const [rootError, setRootError] = useState<string | null>(null)

  const loadRoot = useCallback(async () => {
    setRootLoading(true)
    setRootError(null)
    try {
      const result = await invoke("file.stat", { path: "" })
      setTree(toNodes("", result.children ?? []))
      setLoadedPaths(new Set())
      setLoadingPaths(new Set())
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取目录失败"
      setRootError(message)
      toast.error(`读取文件树失败：${message}`)
    } finally {
      setRootLoading(false)
    }
  }, [invoke])

  // 挂载即拉根目录。用 setTimeout 推迟一轮：effect 里直接 setState 会被
  // react-hooks/set-state-in-effect 判错（预览面板同款处理）。
  useEffect(() => {
    const timer = setTimeout(() => void loadRoot(), 0)
    return () => clearTimeout(timer)
  }, [loadRoot])

  const loadChildren = useCallback(
    async (node: FileNode) => {
      if (node.type !== "folder") return
      if (loadedPaths.has(node.id) || loadingPaths.has(node.id)) return

      setLoadingPaths((prev) => new Set(prev).add(node.id))
      try {
        const result = await invoke("file.stat", { path: node.id })
        setTree((prev) =>
          replaceChildren(
            prev,
            node.id,
            toNodes(node.id, result.children ?? [])
          )
        )
        setLoadedPaths((prev) => new Set(prev).add(node.id))
      } catch (error) {
        // 失败保持「未加载」：下次展开会重试
        const message = error instanceof Error ? error.message : "读取目录失败"
        toast.error(`读取 ${node.id || "/"} 失败：${message}`)
      } finally {
        setLoadingPaths((prev) => {
          const next = new Set(prev)
          next.delete(node.id)
          return next
        })
      }
    },
    [invoke, loadedPaths, loadingPaths]
  )

  return {
    tree,
    loadedPaths,
    loadingPaths,
    rootLoading,
    rootError,
    refresh: loadRoot,
    loadChildren,
  }
}
