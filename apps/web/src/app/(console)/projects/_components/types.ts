export type Project = {
  id: string
  name: string
  description: string
  emoji: string
  /** 缩略图背景色，使用语义色系之外的柔和色块 */
  tint: string
  tags: string[]
  type: ProjectType
  status: ProjectStatus
  favorite: boolean
  verified?: boolean
  owner: string
  updatedAt: string
}

export const TYPE_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "web", label: "网页应用" },
  { value: "mini-program", label: "小程序" }
] as const
export const STATUS_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "active", label: "进行中" },
  { value: "archived", label: "已部署" },
] as const
export const SORT_OPTIONS = [
  { value: "updated", label: "最近编辑" },
  { value: "created", label: "创建时间" },
] as const

export type TypeFilter = (typeof TYPE_OPTIONS)[number]["value"]
export type StatusFilter = (typeof STATUS_OPTIONS)[number]["value"]
export type SortKey = (typeof SORT_OPTIONS)[number]["value"]

export type ProjectType = Exclude<TypeFilter, "all">
export type ProjectStatus = Exclude<StatusFilter, "all">

/** 搜索/筛选条件的统一载荷，头部只回调这一个对象 */
export type ProjectSearchParams = {
  keyword: string
  type: TypeFilter
  status: StatusFilter
  favoriteOnly: boolean
  sort: SortKey
}

export const DEFAULT_SEARCH_PARAMS: ProjectSearchParams = {
  keyword: "",
  type: "all",
  status: "all",
  favoriteOnly: false,
  sort: "updated",
}

export const PROJECTS: Project[] = [
  {
    id: "car-official",
    name: "汽车官网",
    description: "汽车官网，展示车型、资讯及服务，提供便捷购车体验。",
    emoji: "🚘",
    tint: "bg-sky-100 dark:bg-sky-950",
    tags: ["网页应用"],
    type: "web",
    status: "active",
    favorite: false,
    verified: true,
    owner: "广宝哥",
    updatedAt: "10-20 14:22",
  }
]
