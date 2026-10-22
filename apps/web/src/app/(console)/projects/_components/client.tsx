"use client"

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/http"
import {
  sessionDeleteSessionDeleteIdPost,
  sessionListSessionListPost,
} from "@/api/generated/session/session"

import { ProjectsHeader } from "./header"
import { ProjectCard } from "./project-card"
import {
  DEFAULT_SEARCH_PARAMS,
  toListRequest,
  type ProjectSearchParams,
} from "./types"

const LIST_QUERY_KEY = ["session", "list"] as const
const SEARCH_DEBOUNCE_MS = 300

/** 输入框每敲一个字都发请求太浪费，300ms 内没有新输入才真正去查 */
function useDebouncedValue<T>(value: T, delay: number) {
  const [debounced, setDebounced] = React.useState(value)

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

export function ProjectsClient() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = React.useState<ProjectSearchParams>(
    DEFAULT_SEARCH_PARAMS,
  )

  const debouncedKeyword = useDebouncedValue(
    searchParams.keyword,
    SEARCH_DEBOUNCE_MS,
  )

  const request = React.useMemo(
    () => toListRequest({ ...searchParams, keyword: debouncedKeyword }),
    // searchParams 里的 keyword 换成防抖后的值，其余字段即时生效
    [searchParams, debouncedKeyword],
  )

  // 接口是 POST，orval 只会生成 useMutation；这里要的是「按条件取数据」，
  // 所以直接用生成的请求函数配 useQuery，拿到 loading / error / 缓存
  const listQuery = useQuery({
    queryKey: [...LIST_QUERY_KEY, request],
    queryFn: ({ signal }) =>
      sessionListSessionListPost(request, undefined, signal),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => sessionDeleteSessionDeleteIdPost(id),
    onSuccess: () => {
      // 不手动改动本地列表：删除后 total 也变了，重拉一次最省心
      queryClient.invalidateQueries({ queryKey: LIST_QUERY_KEY })
    },
  })

  const projects = listQuery.data?.data ?? []
  const isFirstLoading = listQuery.isPending
  const isError = listQuery.isError

  return (
    <div className="flex flex-1 flex-col">
      <ProjectsHeader params={searchParams} onSearch={setSearchParams} />

      <div className="px-6 pb-10">
        {isFirstLoading ? (
          <div className="grid grid-cols-1 gap-4 pt-1 sm:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, index) => (
              <div
                key={index}
                className="h-46 animate-pulse rounded-xl bg-muted"
              />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-20 text-center">
            <p className="text-sm font-medium">项目列表加载失败</p>
            <p className="text-sm text-muted-foreground">
              {listQuery.error instanceof ApiError
                ? listQuery.error.message
                : "请稍后重试。"}
            </p>
            <button
              type="button"
              onClick={() => listQuery.refetch()}
              className="text-sm font-medium underline underline-offset-4"
            >
              重新加载
            </button>
          </div>
        ) : projects.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 pt-1 sm:grid-cols-3 xl:grid-cols-4">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onDelete={() => deleteMutation.mutate(project.id)}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl py-20 text-center">
            <p className="text-sm text-muted-foreground">暂无项目</p>
          </div>
        )}
      </div>
    </div>
  )
}
