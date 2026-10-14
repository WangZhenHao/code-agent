"use client"

import * as React from "react"
import {
  ArrowUpIcon,
  AudioLinesIcon,
  BotIcon,
  CheckIcon,
  ChevronDownIcon,
  MonitorIcon,
  PlusIcon,
  Settings2Icon,
  SmartphoneIcon,
  SparklesIcon,
  WorkflowIcon,
  XIcon,
  ZapIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import { Marquee } from "@/components/ui/marquee"
import { cn } from "@/lib/utils"

type ProductType = {
  id: string
  label: string
  icon: React.ComponentType
}


const MODES = [
  { id: "agent", label: "agent模式" },
  { id: "plan", label: "plan模式" }
]

const PROMPT_EXAMPLES = [
  "生成一个个人博客网站，支持文章分类和全文搜索",
  "做一个简洁记账工具，支持收支分类和月度图表",
  "搭一个 AI 聊天页面，支持会话保存和清空记录",
  "做一个 Todo List 应用，支持任务优先级和截止时间提醒",
  "帮我做一个旅行攻略网站，支持目的地收藏和行程规划",
  "搭建一个活动报名页，支持表单校验和名额限制",
  "做一个 Kanban 看板，支持拖拽卡片和多列状态",
  "帮我开发一个天气应用，支持城市搜索和未来 7 天预报",
  "生成一个简历制作器，支持多模板切换和 PDF 下载",
  "做一个在线代码运行器，支持 JS/Python 示例执行",
  "搭一个随机抽奖工具，支持名单导入和去重抽取",
  "做一个习惯打卡应用，支持连续天数和成就徽章",
  "做一个图片压缩工具，支持批量上传和格式转换",
  "做一个客户反馈看板，支持分类标签和导出表格",
  "做一个番茄专注计时器，支持任务分组和每日统计",
]

export default function Home() {
  const [mode, setMode] = React.useState("agent")
  const [prompt, setPrompt] = React.useState("")

  const modeLabel = MODES.find((m) => m.id === mode)?.label ?? "自动"

  return (
    <div className="bg-[#FBFAF5] h-screen">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_0%,var(--color-muted)_0%,transparent_60%)]"
      />

      <SiteHeader />

      <main className="relative flex flex-1 flex-col items-center">
        <section className="flex w-full max-w-3xl flex-col items-center pt-14 text-center sm:pt-16">
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl md:text-6xl">
            码灵编程，你的 AI 开发伙伴
          </h1>
          <p className="mt-5 text-base text-muted-foreground sm:text-lg">
            全栈、全流程、全托管式 AI 编程平台
          </p>

          

          <Composer
            mode={mode}
            modeLabel={modeLabel}
            onModeChange={setMode}
            prompt={prompt}
            onPromptChange={setPrompt}
          />
        </section>

        <section className="mt-12 w-full max-w-350">
          <p className="text-center text-sm font-medium text-muted-foreground">
            立即开启 AI 编程之旅！
          </p>
          <div className="mt-6 flex flex-col">
            <ExampleRow
              examples={PROMPT_EXAMPLES.slice(0, 5)}
              onPick={setPrompt}
              duration="56s"
            />
            <ExampleRow
              examples={PROMPT_EXAMPLES.slice(5, 10)}
              onPick={setPrompt}
              duration="72s"
              reverse
            />
            <ExampleRow
              examples={PROMPT_EXAMPLES.slice(10, 15)}
              onPick={setPrompt}
              duration="72s"
            />
          </div>
        </section>
      </main>
    </div>
  )
}

function ExampleRow({
  examples,
  onPick,
  duration,
  reverse,
}: {
  examples: string[]
  onPick: (example: string) => void
  duration: string
  reverse?: boolean
}) {
  const items = examples.map((example) => (
    <Badge
      key={example}
      asChild
      variant="outline"
      className="h-8 shrink-0 rounded-full border-border/80 bg-background/70 px-3 text-xs font-normal text-muted-foreground backdrop-blur-sm"
    >
      <button type="button" onClick={() => onPick(example)}>
        {example}
      </button>
    </Badge>
  ))

  return (
    <Marquee
      repeat={4}
      reverse={reverse}
      pauseOnHover
      className={cn(
        "items-center p-0 [--gap:0.625rem] motion-reduce:overflow-x-auto",
        "[mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)] motion-reduce:mask-none mb-2"
      )}
      style={{ "--duration": duration } as React.CSSProperties}
    >
      {items}
    </Marquee>
  )
}

function SiteHeader() {
  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center justify-between gap-4 px-4 sm:px-6">
      <div className="flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-fuchsia-500 to-violet-600 text-primary-foreground">
          <SparklesIcon className="size-4" />
        </span>
        <span className="text-base font-semibold">码灵编程</span>
      </div>

      <div className="flex items-center gap-3">
        <Button size="lg" className="rounded-full px-4">
          注册/登陆
        </Button>
      </div>
    </header>
  )
}



function Composer({
  mode,
  modeLabel,
  onModeChange,
  prompt,
  onPromptChange,
}: {
  mode: string
  modeLabel: string
  onModeChange: (mode: string) => void
  prompt: string
  onPromptChange: (prompt: string) => void
}) {

  return (
    <form
      onSubmit={(event) => event.preventDefault()}
      className="mt-7 max-w-300 text-left"
    >
      <InputGroup className="gap-0 rounded-2xl border-border/80 bg-card py-0 shadow-xs">
        <InputGroupTextarea
          rows={3}
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          placeholder="帮我做一个旅行攻略网站，实现我输入旅行地点和旅游时间，生成旅行攻略和行李建议"
          className="min-h-24 px-4 py-4 leading-6 w-200"
        />

        <InputGroupAddon
          align="block-end"
          className="gap-1.5 px-4 pb-2 text-muted-foreground"
        >
          <InputGroupButton size="icon-sm" aria-label="添加附件">
            <PlusIcon />
          </InputGroupButton>
          <InputGroupButton size="icon-sm" aria-label="参数设置">
            <Settings2Icon />
          </InputGroupButton>
          <InputGroupButton size="sm" className="gap-1.5 px-2">
            <ZapIcon />
            技能
            <span className="text-muted-foreground">12</span>
          </InputGroupButton>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <InputGroupButton size="sm" className="gap-1 px-2">
                {modeLabel}
                <ChevronDownIcon />
              </InputGroupButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-36">
              <DropdownMenuGroup>
                {MODES.map((item) => (
                  <DropdownMenuItem
                    key={item.id}
                    onSelect={() => onModeChange(item.id)}
                    className="justify-between"
                  >
                    {item.label}
                    {mode === item.id ? <CheckIcon /> : null}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            type="submit"
            size="icon"
            aria-label="发送"
            disabled={prompt.trim().length === 0}
            className="ml-auto rounded-full bg-foreground text-background hover:bg-foreground/80 disabled:opacity-40"
          >
            <ArrowUpIcon />
          </Button>

        </InputGroupAddon>
      </InputGroup>
    </form>
  )
}
