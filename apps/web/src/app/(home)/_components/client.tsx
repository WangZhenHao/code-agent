"use client"

import * as React from "react"

import { Composer } from "./composer"
import { SiteHeader } from "./site-header"
import { CapabilitySection } from "./capability-section"
import SectionRow from "./section-row"

export function Client() {
  const [prompt, setPrompt] = React.useState("")

  return (
    <div className="min-h-screen bg-[#FBFAF5]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_0%,var(--color-muted)_0%,transparent_60%)]"
      />

      <SiteHeader />

      <main className="relative flex flex-1 flex-col items-center px-4 pb-24 sm:px-6">
        <section className="mt-16 flex w-full max-w-3xl flex-col items-center text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl md:text-6xl">
            码灵编程，你的 AI 开发伙伴
          </h1>
          <p className="mt-5 text-base text-muted-foreground sm:text-lg">
            全栈、全流程、全托管式 AI 编程平台
          </p>

          <Composer
            className="w-200 mt-7"
            prompt={prompt}
            onPromptChange={setPrompt}
          />
        </section>

        <SectionRow setPrompt={setPrompt} />

        <CapabilitySection />
      </main>
    </div>
  )
}
