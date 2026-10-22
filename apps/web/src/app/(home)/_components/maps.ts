export const MODES = [
  { id: "agent", label: "agent模式" },
  { id: "plan", label: "plan模式" },
]

/**
 * 可选模型列表。
 *
 * 名字是直接传给后端 `ChatCreateRequest.model` 的字符串，后端再交给统一网关
 * 按 OpenAI 协议路由（见 apps/api/src/app/models/llm.py）。所以这里不需要区分
 * 是哪家厂商——新增模型等于网关侧先支持，再在这里加一行。
 */
export type ModelOption = {
  id: string
  label: string
  /** 下拉框里的分组标题 */
  vendor: string
  /** 一句话说明，展示在下拉项的副标题上 */
  description: string
}

export const MODELS: ModelOption[] = [
  {
    id: "deepseek-v4-flash",
    label: "DeepSeek V4 Flash",
    vendor: "DeepSeek",
    description: "响应快，适合日常开发",
  },
  {
    id: "deepseek-v4-pro",
    label: "DeepSeek V4 Pro",
    vendor: "DeepSeek",
    description: "更强的推理与代码能力",
  },
  {
    id: "claude-sonnet-5",
    label: "Claude Sonnet 5",
    vendor: "Anthropic",
    description: "综合能力均衡，适合大多数任务",
  },
  {
    id: "claude-opus-5",
    label: "Claude Opus 5",
    vendor: "Anthropic",
    description: "最擅长复杂工程任务",
  },
  {
    id: "claude-haiku-4-5-20251001",
    label: "Claude Haiku 4.5",
    vendor: "Anthropic",
    description: "轻量高速，适合小改动",
  },
  {
    id: "claude-fable-5-1",
    label: "Claude Fable 5.1",
    vendor: "Anthropic",
    description: "偏创意与写作场景",
  },
  {
    id: "gpt-5",
    label: "GPT-5",
    vendor: "OpenAI",
    description: "通用能力强的旗舰模型",
  },
  {
    id: "gpt-5-mini",
    label: "GPT-5 mini",
    vendor: "OpenAI",
    description: "成本低的轻量版本",
  },
  {
    id: "gpt-4.1",
    label: "GPT-4.1",
    vendor: "OpenAI",
    description: "擅长代码与长上下文",
  },
  {
    id: "kimi-k2",
    label: "Kimi K2",
    vendor: "Moonshot",
    description: "长上下文，擅长读大仓库",
  },
]

/** 与后端 ChatCreateRequest.model 的默认值保持一致 */
export const DEFAULT_MODEL = "deepseek-v4-flash"

/** 按厂商分组，下拉框按这个结构渲染分组标题 */
export function groupModels(models: ModelOption[] = MODELS) {
  const groups = new Map<string, ModelOption[]>()
  for (const model of models) {
    const list = groups.get(model.vendor) ?? []
    list.push(model)
    groups.set(model.vendor, list)
  }
  return Array.from(groups, ([vendor, items]) => ({ vendor, items }))
}
