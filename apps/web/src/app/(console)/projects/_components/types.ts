import type {
  PublicStatus,
  SessionItem,
  SessionListRequest,
} from "@/api/generated/model"

/** 列表里的一条会话，字段直接取自 /session/list 的 SessionItem */
export type Project = SessionItem

export const TYPE_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "web", label: "网页应用" },
  { value: "mini_program", label: "小程序" },
] as const

/** 对应 SessionListRequest.publish：1=已部署，0=未部署；all 表示不传该字段 */
export const STATUS_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "1", label: "已部署" },
  { value: "0", label: "未部署" },
] as const

/** 值必须是接口的 SessionSort，排序在后端做（两种都是倒序） */
export const SORT_OPTIONS = [
  { value: "update_at", label: "最近编辑" },
  { value: "created_at", label: "创建时间" },
] as const

// platform 在 SessionItem 里是普通 string（不是 Platform 枚举），用宽松的键类型
export const PLATFORM_LABELS: Record<string, string> = {
  web: "网页应用",
  mini_program: "小程序",
}

export type TypeFilter = (typeof TYPE_OPTIONS)[number]["value"]
export type StatusFilter = (typeof STATUS_OPTIONS)[number]["value"]
export type SortKey = (typeof SORT_OPTIONS)[number]["value"]

/** 搜索/筛选条件的统一载荷，头部只回调这一个对象 */
export type ProjectSearchParams = {
  keyword: string
  type: TypeFilter
  status: StatusFilter
  sort: SortKey
}

export const DEFAULT_SEARCH_PARAMS: ProjectSearchParams = {
  keyword: "",
  type: "all",
  status: "all",
  sort: "created_at",
}

/**
 * 把 UI 条件翻译成 /session/list 的请求体。
 * 筛选、排序都交给后端，前端不再本地过滤——列表页没有分页 UI，
 * 先按接口上限一次取 100 条。
 */
export function toListRequest(params: ProjectSearchParams): SessionListRequest {
  return {
    page: 1,
    page_size: 100,
    keyword: params.keyword.trim() || null,
    platform: params.type === "all" ? null : params.type,
    publish:
      params.status === "all"
        ? null
        : (Number(params.status) as PublicStatus),
    sort: params.sort,
  }
}

const TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
})

/** timestamptz 的 ISO 字符串 → 「10-20 14:22」 */
export function formatUpdatedAt(iso: string) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? "—" : TIME_FORMATTER.format(date)
}
