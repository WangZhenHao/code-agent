"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { AuthRequestError, useCreateChat, useCurrentUser, useLogout } from "@/lib/auth-client"
import { safeRelativePath } from "@/lib/auth-utils.mjs"

import { Composer, type Mode } from "./_components/composer"
import { LoginDialog } from "./_components/login-dialog"
import { SiteHeader } from "./_components/site-header"
import { CapabilitySection } from "./_components/capability-section"
import SectionRow, { PROMPT_EXAMPLES } from "./_components/section-row"

const MODE_LABELS: Record<Mode, string> = { agent: "agent模式", plan: "plan模式" }

export default function Home() {
  const [mode, setMode] = React.useState<Mode>("agent")
  const [prompt, setPrompt] = React.useState("")
  const [loginOpen, setLoginOpen] = React.useState(false)
  const [redirectTo, setRedirectTo] = React.useState<string | null>(null)
  const router = useRouter()
  const userQuery = useCurrentUser()
  const logout = useLogout()
  const createChat = useCreateChat()

  const openLogin = React.useCallback((destination: string | null = null) => {
    setRedirectTo(destination)
    setLoginOpen(true)
  }, [])

  React.useEffect(() => {
    const currentUrl = new URL(window.location.href)
    if (currentUrl.searchParams.get("login") !== "true") return

    const destination = safeRelativePath(currentUrl.searchParams.get("redirect_url"))
    const timer = window.setTimeout(() => {
      openLogin(destination)
      currentUrl.searchParams.delete("login")
      currentUrl.searchParams.delete("redirect_url")
      window.history.replaceState(window.history.state, "", `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [openLogin])

  function handleLogout() {
    logout.mutate(undefined, { onSuccess: () => router.replace("/") })
  }

  function handleLoginOpenChange(open: boolean) {
    setLoginOpen(open)
    if (!open) setRedirectTo(null)
  }

  function handleCreate() {
    const message = prompt.trim()
    if (!message || userQuery.isPending || createChat.isPending) return
    if (!userQuery.data) {
      openLogin()
      return
    }

    createChat.mutate({ prompt: message, mode }, {
      onSuccess: ({ id }) => router.push(`/projrects/${encodeURIComponent(id)}`),
      onError: (error) => {
        if (error instanceof AuthRequestError && error.status === 401) openLogin()
      },
    })
  }

  const modeLabel = MODE_LABELS[mode]
  return (
    <div className="min-h-screen bg-[#FBFAF5]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_0%,var(--color-muted)_0%,transparent_60%)]"
      />

      <SiteHeader
        authenticated={Boolean(userQuery.data)}
        onLogin={() => openLogin()}
        onLogout={handleLogout}
        loggingOut={logout.isPending}
      />

      <main className="relative flex flex-1 flex-col items-center px-4 pb-24 sm:px-6">
        <section className="mt-16 flex w-full max-w-3xl flex-col items-center text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl md:text-6xl">
            码灵编程，你的 AI 开发伙伴
          </h1>
          <p className="mt-5 text-base text-muted-foreground sm:text-lg">
            全栈、全流程、全托管式 AI 编程平台
          </p>

          <Composer
            examples={PROMPT_EXAMPLES}
            mode={mode}
            modeLabel={modeLabel}
            onModeChange={setMode}
            prompt={prompt}
            onPromptChange={(value) => {
              setPrompt(value)
              createChat.reset()
            }}
            onCreate={handleCreate}
            submitting={userQuery.isPending || createChat.isPending}
          />
          {createChat.error ? <p role="alert" className="mt-3 text-sm text-destructive">{createChat.error.message}</p> : null}
        </section>

        <SectionRow setPrompt={setPrompt} />

        <CapabilitySection />
      </main>
      <LoginDialog open={loginOpen} onOpenChange={handleLoginOpenChange} redirectTo={redirectTo} />
    </div>
  )
}
