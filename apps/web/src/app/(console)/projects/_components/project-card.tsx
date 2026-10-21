"use client"

import { cn } from "cn"
import { CheckCircle2Icon, EllipsisIcon, StarIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import type { Project } from "./types"

type ProjectCardProps = {
  project: Project
  onOpen: () => void
  onToggleFavorite: () => void
  onDelete: () => void
}

export function ProjectCard({
  project,
  onOpen,
  onToggleFavorite,
  onDelete,
}: ProjectCardProps) {
  return (
    <div
      role="link"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault()
          onOpen()
        }
      }}
      className="group/card flex cursor-pointer flex-col rounded-xl bg-card text-card-foreground ring-1 ring-foreground/10 transition-colors outline-none hover:ring-foreground/20 focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <h2 className="truncate font-heading text-[0.95rem] font-medium">
              {project.name}
            </h2>
            {project.verified ? (
              <CheckCircle2Icon
                className="size-3.5 shrink-0 text-success"
                aria-label="已验证"
              />
            ) : null}
          </div>
          <p className="line-clamp-2 min-h-10 text-sm leading-5 text-muted-foreground">
            {project.description}
          </p>
        </div>

        <div
          className={cn(
            "flex size-16 shrink-0 items-center justify-center rounded-lg text-3xl ring-1 ring-foreground/5",
            project.tint,
          )}
          aria-hidden
        >
          {project.emoji}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 px-4 pb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {project.tags.map((tag) => (
            <Badge key={tag} variant="outline" className="font-normal">
              {tag}
            </Badge>
          ))}
        </div>

        <div
          className="flex items-center gap-0.5"
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={project.favorite ? "取消收藏" : "收藏项目"}
            aria-pressed={project.favorite}
            onClick={onToggleFavorite}
            className={cn(
              "text-muted-foreground opacity-0 transition-opacity group-hover/card:opacity-100 group-focus-within/card:opacity-100",
              project.favorite && "text-warning opacity-100",
            )}
          >
            <StarIcon className={cn(project.favorite && "fill-current")} />
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="更多操作">
                <EllipsisIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem>创建副本</DropdownMenuItem>
              <DropdownMenuItem>移动</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={onDelete}>
                删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="mt-auto flex items-center gap-1.5 border-t px-4 py-2.5 text-xs text-muted-foreground">
        <span className="flex size-4 items-center justify-center rounded-full bg-muted text-[0.6rem]">
          👤
        </span>
        <span>{project.owner}</span>
        <span>最近编辑 {project.updatedAt}</span>
      </div>
    </div>
  )
}
