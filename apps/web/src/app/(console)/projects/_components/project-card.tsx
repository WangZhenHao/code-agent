"use client"

import Link from "next/link"

import { cn } from "cn"
import { EllipsisIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { PLATFORM_LABELS, formatUpdatedAt, type Project } from "./types"

/** 没有封面图时按平台给个占位图标和底色 */
const PLATFORM_PLACEHOLDER: Record<string, { emoji: string; tint: string }> = {
  web: { emoji: "🌐", tint: "bg-sky-100 dark:bg-sky-950" },
  mini_program: { emoji: "📱", tint: "bg-emerald-100 dark:bg-emerald-950" },
}

type ProjectCardProps = {
  project: Project
  onDelete: () => void
}

export function ProjectCard({ project, onDelete }: ProjectCardProps) {
  // platform 在接口里是普通 string，不保证一定是已知枚举，统一兜底到 web
  const plugin =
    PLATFORM_PLACEHOLDER[project.platform ?? "web"] ?? PLATFORM_PLACEHOLDER.web
  const isPublished = project.publish === 1

  return (
    <Link
      href={`/projects/${project.id}`}
      className="group/card flex flex-col rounded-xl bg-card text-card-foreground ring-1 ring-foreground/10 transition-colors outline-none hover:ring-foreground/20 focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <h2 className="truncate font-heading text-[0.95rem] font-medium">
              {project.title}
            </h2>
          </div>
          <p className="line-clamp-2 min-h-10 text-sm leading-5 text-muted-foreground">
            {project.description || "暂无描述"}
          </p>
        </div>

        {project.title_image ? (
          // 封面是后端给的任意 URL，走到这里已经有授权以外的域名风险，
          // 用普通 img 而不是 next/image，避免给每个域名配 remotePatterns
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={project.title_image}
            alt=""
            className="size-16 shrink-0 rounded-lg object-cover ring-1 ring-foreground/5"
          />
        ) : (
          <div
            className={cn(
              "flex size-16 shrink-0 items-center justify-center rounded-lg text-3xl ring-1 ring-foreground/5",
              plugin.tint,
            )}
            aria-hidden
          >
            {plugin.emoji}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 px-4 pb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="font-normal">
            {PLATFORM_LABELS[project.platform ?? "web"] ?? "网页应用"}
          </Badge>
          <Badge
            variant={isPublished ? "secondary" : "outline"}
            className="font-normal"
          >
            {isPublished ? "已部署" : "未部署"}
          </Badge>
        </div>

        {/* 卡片整体是链接，操作区必须拦住冒泡，否则点菜单/删除会直接跳转 */}
        <div
          className="flex items-center gap-0.5 bg-white"
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
          }}
        >
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="更多操作">
                <EllipsisIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={onDelete}>
                删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="mt-auto flex items-center gap-1.5 border-t px-4 py-2.5 text-xs text-muted-foreground">
        <span>最近编辑 {formatUpdatedAt(project.updated_at)}</span>
      </div>
    </Link>
  )
}
