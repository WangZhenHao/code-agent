import { create } from "zustand"
import type { ChatDetailResponse } from "@/api/generated/model"

interface ProjectDetailState {
  /** 当前会话的详情数据，null = 还未加载 */
  info: ChatDetailResponse | null

  /** 用完整的 API 返回结果替换 info（client.tsx 的 useEffect 调用） */
  setInfo: (info: ChatDetailResponse) => void

  /** 更新 info 的单个字段（浅 merge） */
  updateField: <K extends keyof ChatDetailResponse>(
    key: K,
    value: ChatDetailResponse[K]
  ) => void

  /** 用于切会话时清空（key 变化时 client.tsx 调用） */
  clear: () => void
}

export const useProjectDetailStore = create<ProjectDetailState>()((set) => ({
  info: null,
  setInfo: (info) => set({ info }),
  updateField: (key, value) =>
    set((state) => ({
      info: state.info ? { ...state.info, [key]: value } : null,
    })),
  clear: () => set({ info: null }),
}))
