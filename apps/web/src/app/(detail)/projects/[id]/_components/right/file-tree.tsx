"use client"

import { useRef, useState, type RefObject } from "react"

import {
  FilePlus,
  Folder,
  FolderPlus,
  Search,
  ChevronRight,
  Download,
  Copy,
  GitBranch,
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

type FileNode = {
  id: string
  name: string
  type: "folder" | "file"
  children?: FileNode[]
}

const folder = (name: string, children: FileNode[] = []): FileNode => ({
  id: name,
  name,
  type: "folder",
  children,
})

const file = (name: string): FileNode => ({ id: name, name, type: "file" })

// 暂时写死一份目录结构，接口就绪后换成后端返回（树形或展平后 assemble）
const mockTree: FileNode[] = [
  folder(".codegraph", [file("index.json")]),
  folder(".next"),
  folder("dist"),
  folder("public", [file("favicon.ico")]),
  folder("scripts", [file("build.sh")]),
  folder("src", [
    folder("app", [folder("(home)"), folder("layout.tsx")]),
    folder("components", []),
    folder("lib", []),
    file("proxy.ts"),
  ]),
  file(".babelrc"),
  file(".coze"),
  file(".gitignore"),
  file(".npmrc"),
  file("AGENTS.md"),
  file("components.json"),
  file("DESIGN.md"),
  file("eslint.config.mjs"),
  file("next-env.d.ts"),
  file("next.config.ts"),
  file("package.json"),
  file("pnpm-lock.yaml"),
  file("postcss.config.mjs"),
]

const Row = ({ node, style, dragHandle }: NodeRendererProps<FileNode>) => {
  const { data, isOpen, isLeaf } = node
  return (
    <div
      style={style}
      ref={dragHandle}
      onClick={() => node.toggle()}
      className={cn(
        "flex cursor-pointer items-center gap-1.5 rounded-md pr-2 text-sm text-foreground select-none h-full",
        "hover:bg-muted",
        node.isSelected && "bg-muted"
      )}
    >
      <ChevronRight
        className={cn(
          "size-3.5 shrink-0 text-muted-foreground transition-transform",
          isLeaf && "invisible",
          isOpen && "rotate-90"
        )}
      />
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
  onClick,
}: {
  label: string
  icon: typeof Folder
  active?: boolean
  onClick?: () => void
}) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onClick}
        aria-label={label}
        className={cn(active && "bg-muted")}
      >
        <Icon />
      </Button>
    </TooltipTrigger>
    <TooltipContent>{label}</TooltipContent>
  </Tooltip>
)

/** 左侧文件树：顶栏工具栏 + 可搜索的虚拟滚动目录树。 */
const Filetree = () => {
  const [searching, setSearching] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const treeRef = useRef<HTMLDivElement>(null)
  // usehooks-ts 的 ref 类型不接受 null（React 19 的 useRef 初值含 null），这里收窄一下
  const { height } = useResizeObserver<HTMLDivElement>({
    ref: treeRef as RefObject<HTMLDivElement>,
  })

  return (
    <div className="mr-2 flex h-full shrink-0 flex-col overflow-hidden rounded-md border border-border bg-background shadow-xs" style={{ width: '398px' }}>
      <div className="flex items-center justify-between px-2 pt-2">
        <div className="flex-1 bg-muted rounded-sm flex justify-center">
          <IconAction label="文件" icon={Folder} />
        </div>
        <div className="flex-1 flex justify-center">
          <IconAction label="搜索" icon={Search} />
        </div>
        <div className="flex-1 flex justify-center">
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
        {height ? (
          <Tree<FileNode>
            data={mockTree}
            openByDefault={false}
            idAccessor="id"
            childrenAccessor="children"
            width="100%"
            height={height}
            rowHeight={32}
            indent={14}
            paddingTop={4}
            searchTerm={searchTerm}
            disableDrag
            disableDrop
            disableEdit
            disableMultiSelection
            className="h-full"
          >
            {Row}
          </Tree>
        ) : null}
      </div>
    </div>
  )
}

export default Filetree
