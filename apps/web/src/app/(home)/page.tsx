"use client"

import * as React from "react"

import { Composer } from "./_components/composer"
import { ExampleRow } from "./_components/example-row"
import { SiteHeader } from "./_components/site-header"

const MODES = [
  { id: "agent", label: "agent模式" },
  { id: "plan", label: "plan模式" },
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
