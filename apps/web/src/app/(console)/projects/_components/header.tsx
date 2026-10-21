"use client"

import { useRouter } from "next/navigation"

import {
  FolderPlusIcon,
  ListFilterIcon,
  PlusCircleIcon,
  SearchIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import {
  DEFAULT_SEARCH_PARAMS,
  SORT_OPTIONS,
  STATUS_OPTIONS,
  TYPE_OPTIONS,
  type ProjectSearchParams,
  type SortKey,
  type StatusFilter,
  type TypeFilter,
} from "./types"

type ProjectsHeaderProps = {
  /** 当前搜索条件（受控），未传时使用默认值 */
  params?: ProjectSearchParams
  /** 任一搜索条件变化时调用，回传合并后的完整条件 */
  onSearch: (params: ProjectSearchParams) => void
}

export function ProjectsHeader({
  params = DEFAULT_SEARCH_PARAMS,
  onSearch,
}: ProjectsHeaderProps) {
  const router = useRouter()

  const update = (patch: Partial<ProjectSearchParams>) =>
    onSearch({ ...params, ...patch })

  // 新增文件夹的弹窗尚未实现，先留空
  const handleNewFolder = () => {}

  const handleNewProject = () => router.push("/create")

  return (
    <header className="sticky top-0 z-20 flex flex-col gap-4 bg-background px-6 pt-6 pb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-heading text-xl font-semibold tracking-tight">
          项目开发
        </h1>

        <div className="flex flex-wrap items-center gap-2">
          <InputGroup className="w-52">
            <InputGroupAddon>
              <SearchIcon className="text-muted-foreground" />
            </InputGroupAddon>
            <InputGroupInput
              placeholder="搜索项目"
              value={params.keyword}
              onChange={(event) => update({ keyword: event.target.value })}
            />
          </InputGroup>
          <Button onClick={handleNewProject}>
            <PlusCircleIcon data-icon="inline-start" />
            新增项目
          </Button>
        </div>
      </div>

      <p className="text-sm font-medium text-muted-foreground">项目</p>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={params.type}
          onValueChange={(value) => update({ type: value as TypeFilter })}
        >
          <SelectTrigger className="w-48">
            <span className="text-muted-foreground">项目类型</span>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>

        <Select
          value={params.status}
          onValueChange={(value) => update({ status: value as StatusFilter })}
        >
          <SelectTrigger className="w-48">
            <span className="text-muted-foreground">项目状态</span>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {STATUS_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2 sm:ml-auto">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <ListFilterIcon data-icon="inline-start" />
                高级筛选
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuLabel>显示范围</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={params.favoriteOnly ? "favorite" : "all"}
                onValueChange={(value) =>
                  update({ favoriteOnly: value === "favorite" })
                }
              >
                <DropdownMenuRadioItem value="all">
                  全部项目
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="favorite">
                  仅收藏
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>排序方式</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={params.sort}
                onValueChange={(value) => update({ sort: value as SortKey })}
              >
                {SORT_OPTIONS.map((option) => (
                  <DropdownMenuRadioItem
                    key={option.value}
                    value={option.value}
                  >
                    {option.label}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  )
}
