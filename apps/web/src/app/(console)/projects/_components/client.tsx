"use client"

import * as React from "react"
import { useRouter } from "next/navigation"

import { ProjectsHeader } from "./header"
import { ProjectCard } from "./project-card"
import {
  DEFAULT_SEARCH_PARAMS,
  PROJECTS,
  type Project,
  type ProjectSearchParams,
} from "./types"

export function ProjectsClient() {
  const router = useRouter()
  const [projects, setProjects] = React.useState<Project[]>(PROJECTS)
  const [searchParams, setSearchParams] = React.useState<ProjectSearchParams>(
    DEFAULT_SEARCH_PARAMS,
  )
  const { keyword, type, status, favoriteOnly, sort } = searchParams

  const visibleProjects = React.useMemo(() => {
    const q = keyword.trim().toLowerCase()
    const list = projects.filter((project) => {
      if (
        q &&
        !`${project.name}${project.description}`.toLowerCase().includes(q)
      )
        return false
      if (type !== "all" && project.type !== type) return false
      if (status !== "all" && project.status !== status) return false
      if (favoriteOnly && !project.favorite) return false
      return true
    })

    return [...list].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name, "zh-Hans-CN")
      if (sort === "created") return b.id.localeCompare(a.id)
      return b.updatedAt.localeCompare(a.updatedAt)
    })
  }, [projects, keyword, type, status, favoriteOnly, sort])

  const toggleFavorite = (id: string) => {
    setProjects((prev) =>
      prev.map((project) =>
        project.id === id
          ? { ...project, favorite: !project.favorite }
          : project,
      ),
    )
  }

  const removeProject = (id: string) => {
    setProjects((prev) => prev.filter((project) => project.id !== id))
  }

  return (
    <div className="flex flex-1 flex-col">
      <ProjectsHeader params={searchParams} onSearch={setSearchParams} />

      <div className="px-6 pb-10">
        {visibleProjects.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visibleProjects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onOpen={() => router.push(`/projects/${project.id}`)}
                onToggleFavorite={() => toggleFavorite(project.id)}
                onDelete={() => removeProject(project.id)}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-20 text-center">
            <p className="text-sm font-medium">没有匹配的项目</p>
            <p className="text-sm text-muted-foreground">
              试试调整搜索关键词或筛选条件。
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
