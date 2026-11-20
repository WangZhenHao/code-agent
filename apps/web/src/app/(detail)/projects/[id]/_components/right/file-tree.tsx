"use client"

import { useCallback, useMemo, useRef, useState, type RefObject } from "react"
import { toast } from "sonner"

import {
  FilePlus,
  Folder,
  FolderPlus,
  Search,
  ChevronRight,
  Download,
  Copy,
  GitBranch,
  RefreshCw,
} from "lucide-react"
import {
  DefaultFolderIcon,
  DefaultFolderOpenedIcon,
  FileIcon,
} from "@react-symbols/icons/utils"
import { Tree, type NodeRendererProps } from "react-arborist"
import { useResizeObserver } from "usehooks-ts"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { useWsRequest } from "@/lib/ws/request"
import { useProjectOperateStore } from "@/store/project-operate"
import { useFileTree, type FileNode } from "./use-file-tree"

const Row = ({
  node,
  style,
  dragHandle,
  loadingPaths,
  openingPaths,
  onOpenFile,
}: NodeRendererProps<FileNode> & {
  loadingPaths: ReadonlySet<string>
  /** 正在 `file.read` 的文件路径集合，行首显示 spinner */
  openingPaths: ReadonlySet<string>
  onOpenFile: (node: FileNode) => void
}) => {
  const { data, isOpen, isLeaf } = node
  const loading = loadingPaths.has(data.id) || openingPaths.has(data.id)
  return (
    <div
      style={style}
      ref={dragHandle}
      onClick={() => {
        // 文件不展开，点击即读内容并打开 tab；目录照旧懒加载子项
        if (data.type === "file") {
          node.select()
          onOpenFile(data)
        } else {
          node.toggle()
        }
      }}
      className={cn(
        "flex h-full cursor-pointer items-center gap-1.5 rounded-md pr-2 text-sm text-foreground select-none",
        "hover:bg-muted",
        node.isSelected && "bg-muted"
      )}
    >
      {loading ? (
        <Spinner className="size-3.5 shrink-0 text-muted-foreground" />
      ) : (
        <ChevronRight
          className={cn(
            "size-3.5 shrink-0 text-muted-foreground transition-transform",
            isLeaf && "invisible",
            isOpen && "rotate-90"
          )}
        />
      )}
      {data.type === "folder" ? (
        isOpen ? (
          <DefaultFolderOpenedIcon className="size-4 shrink-0" />
        ) : (
          <DefaultFolderIcon className="size-4 shrink-0" />
        )
      ) : (
        <FileIcon fileName={data.name} autoAssign className="size-4 shrink-0" />
      )}
      <span className="truncate">{data.name}</span>
    </div>
  )
}

/** 树面板顶部的图标按钮，统一成 xl icon-sm 的 ghost 样式 */
const IconAction = ({
  label,
  icon: Icon,
  active,
  disabled,
  onClick,
}: {
  label: string
  icon: typeof Folder
  active?: boolean
  disabled?: boolean
  onClick?: () => void
}) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        className={cn(active && "bg-muted")}
      >
        <Icon />
      </Button>
    </TooltipTrigger>
    <TooltipContent>{label}</TooltipContent>
  </Tooltip>
)

/** 左侧文件树：顶栏工具栏 + 可搜索的虚拟滚动目录树。数据来自 WS `file.stat`。 */
const Filetree = () => {
  const [searching] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const treeRef = useRef<HTMLDivElement>(null)
  // usehooks-ts 的 ref 类型不接受 null（React 19 的 useRef 初值含 null），这里收窄一下
  const { height } = useResizeObserver<HTMLDivElement>({
    ref: treeRef as RefObject<HTMLDivElement>,
  })

  const { tree, loadingPaths, rootLoading, rootError, refresh, loadChildren } =
    useFileTree()
  const { invoke } = useWsRequest()
  const openFile = useProjectOperateStore((state) => state.openFile)
  const [openingPaths, setOpeningPaths] = useState<ReadonlySet<string>>(
    new Set()
  )

  // 目录 → 节点索引：onToggle 只给 id，要拿节点类型才知道是不是目录
  const nodesById = useMemo(() => {
    const map = new Map<string, FileNode>()
    const walk = (nodes: FileNode[]) => {
      for (const node of nodes) {
        map.set(node.id, node)
        if (node.children) walk(node.children)
      }
    }
    walk(tree)
    return map
  }, [tree])

  const handleToggle = (id: string) => {
    const node = nodesById.get(id)
    // 没有 children 的节点是叶子，toggle 不会触发；目录则在这里懒加载
    if (node) void loadChildren(node)
  }

  // 点文件：`file.read` 拉内容，塞进 tabList 并切过去
  const handleOpenFile = useCallback(
    async (node: FileNode) => {
      if (openingPaths.has(node.id)) return
      setOpeningPaths((prev) => new Set(prev).add(node.id))
      try {
        const result = await invoke("file.read", { path: node.id })
        openFile(node.id, result.content)
      } catch (error) {
        const message = error instanceof Error ? error.message : "读取文件失败"
        toast.error(`打开 ${node.id} 失败：${message}`)
      } finally {
        setOpeningPaths((prev) => {
          const next = new Set(prev)
          next.delete(node.id)
          return next
        })
      }
    },
    [invoke, openFile, openingPaths]
  )

  const renderRow = (props: NodeRendererProps<FileNode>) => (
    <Row
      {...props}
      loadingPaths={loadingPaths}
      openingPaths={openingPaths}
      onOpenFile={(node) => void handleOpenFile(node)}
    />
  )

  return (
    <div
      className="mr-2 flex h-full shrink-0 flex-col overflow-hidden rounded-md border border-border bg-background shadow-xs"
      style={{ width: "398px" }}
    >
      <div className="flex items-center justify-between px-2 pt-2">
        <div className="flex flex-1 justify-center rounded-sm bg-muted">
          <IconAction label="文件" icon={Folder} />
        </div>
        <div className="flex flex-1 justify-center">
          <IconAction label="搜索" icon={Search} />
        </div>
        <div className="flex flex-1 justify-center">
          <IconAction label="分支" icon={GitBranch} />
        </div>
      </div>

      <div className="flex h-8 shrink-0 items-center justify-between gap-2 px-2">
        <span
          className={cn(
            "truncate px-1 text-[13px] font-medium text-foreground",
            searching && "hidden"
          )}
        >
          Projects
        </span>
        <div className="flex items-center">
          <IconAction label="下载" icon={Download} />
          <IconAction label="新建文件" icon={FilePlus} />
          <IconAction label="新建文件夹" icon={FolderPlus} />
          <IconAction label="复制路径" icon={Copy} />
          <IconAction
            label="刷新"
            icon={RefreshCw}
            disabled={rootLoading}
            onClick={() => void refresh()}
          />
        </div>
      </div>

      {searching && (
        <div className="px-2 pb-1">
          <Input
            autoFocus
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="搜索文件"
            className="h-7 text-xs"
          />
        </div>
      )}

      <div ref={treeRef} className="min-h-0 flex-1 px-2">
        {rootLoading && tree.length === 0 ? (
          <div className="flex h-10 items-center gap-2 px-1 text-xs text-muted-foreground">
            <Spinner className="size-3.5" />
            加载中…
          </div>
        ) : rootError && tree.length === 0 ? (
          <div className="flex flex-col items-start gap-2 px-1 py-2 text-xs text-muted-foreground">
            <span className="line-clamp-2">读取文件树失败：{rootError}</span>
            <Button variant="outline" size="sm" onClick={() => void refresh()}>
              重试
            </Button>
          </div>
        ) : tree.length === 0 ? (
          <div className="px-1 py-2 text-xs text-muted-foreground">
            目录为空
          </div>
        ) : height ? (
          <Tree<FileNode>
            data={tree}
            openByDefault={false}
            idAccessor="id"
            childrenAccessor="children"
            width="100%"
            height={height}
            rowHeight={32}
            indent={14}
            paddingTop={4}
            searchTerm={searchTerm}
            onToggle={handleToggle}
            disableDrag
            disableDrop
            disableEdit
            disableMultiSelection
            className="h-full"
          >
            {renderRow}
          </Tree>
        ) : null}
      </div>
    </div>
  )
}

export default Filetree
