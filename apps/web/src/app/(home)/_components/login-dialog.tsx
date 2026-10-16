"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { SparklesIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { AuthRequestError, useLogin, useSendCode } from "@/lib/auth-client"
import { safeRelativePath } from "@/lib/auth-utils.mjs"

const PHONE_PATTERN = /^1[3-9]\d{9}$/

export function LoginDialog({
  open,
  onOpenChange,
  redirectTo,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  redirectTo: string | null
}) {
  const [phone, setPhone] = React.useState("")
  const [code, setCode] = React.useState("")
  const [retryAfter, setRetryAfter] = React.useState(0)
  const [debugCode, setDebugCode] = React.useState<string | null>(null)
  const phoneInputRef = React.useRef<HTMLInputElement>(null)
  const router = useRouter()
  const sendCode = useSendCode()
  const login = useLogin()
  const phoneIsValid = PHONE_PATTERN.test(phone)

  React.useEffect(() => {
    if (retryAfter <= 0) return
    const timer = window.setTimeout(() => setRetryAfter((seconds) => seconds - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [retryAfter])

  function updatePhone(value: string) {
    setPhone(value.replace(/\D/g, "").slice(0, 11))
    setCode("")
    sendCode.reset()
    login.reset()
    setDebugCode(null)
    setRetryAfter(0)
  }

  function handleLoginOpenChange(nextOpen: boolean) {
    onOpenChange(nextOpen)
    if (nextOpen) return
    setCode("")
    setDebugCode(null)
    sendCode.reset()
    login.reset()
  }

  function handleSendCode() {
    if (!phoneIsValid || retryAfter > 0 || sendCode.isPending) return
    sendCode.mutate({ phone: `+86${phone}` }, {
      onSuccess: (result) => {
        setRetryAfter(60)
        setDebugCode(result.code ?? null)
      },
      onError: (error) => {
        if (error instanceof AuthRequestError && error.retryAfterSeconds) setRetryAfter(error.retryAfterSeconds)
      },
    })
  }

  function handleLoginSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!phoneIsValid || !/^\d{6}$/.test(code)) return
    login.mutate({ phone: `+86${phone}`, code }, {
      onSuccess: () => {
        const destination = safeRelativePath(redirectTo)
        handleLoginOpenChange(false)
        if (destination && destination !== "/") router.replace(destination)
        else router.refresh()
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleLoginOpenChange}>
      <DialogContent
        showCloseButton={false}
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          phoneInputRef.current?.focus()
        }}
        className="max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-[420px] overflow-y-auto rounded-[24px] bg-card px-7 pb-8 pt-9 text-card-foreground shadow-2xl ring-0 sm:overflow-visible sm:px-9 sm:pb-9 sm:pt-10"
      >
        <DialogClose asChild>
          <Button type="button" variant="ghost" size="icon" aria-label="关闭登录窗口" className="absolute right-4 top-4 rounded-full text-muted-foreground sm:-right-11 sm:top-0 sm:bg-black/60 sm:text-white">
            <XIcon />
          </Button>
        </DialogClose>
        <DialogHeader className="mb-8 items-center text-center">
          <div className="mb-5 flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-fuchsia-500 to-violet-600 text-primary-foreground shadow-sm">
            <SparklesIcon className="size-6" />
          </div>
          <DialogTitle className="text-[22px] font-semibold tracking-tight">欢迎使用码灵编程</DialogTitle>
          <DialogDescription className="sr-only">使用手机号验证码登录，未注册手机号验证后将自动创建账号</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleLoginSubmit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="auth-phone" className="sr-only">手机号</label>
            <div className="flex h-12 overflow-hidden rounded-xl border border-input bg-background transition-shadow focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15">
              <span className="my-3 flex items-center border-r border-input px-4 text-sm text-foreground">+86</span>
              <Input
                id="auth-phone"
                ref={phoneInputRef}
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder="请输入手机号码"
                value={phone}
                onChange={(event) => updatePhone(event.target.value)}
                aria-invalid={phone.length === 11 && !phoneIsValid}
                className="h-full rounded-none border-0 px-4 text-base shadow-none focus-visible:border-0 focus-visible:ring-0 md:text-base"
              />
            </div>
            {phone.length === 11 && !phoneIsValid ? <p role="alert" className="mt-2 text-xs text-destructive">请输入有效的手机号码</p> : null}
          </div>

          <div>
            <label htmlFor="auth-code" className="sr-only">验证码</label>
            <div className="flex h-12 overflow-hidden rounded-xl border border-input bg-background transition-shadow focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15">
              <Input
                id="auth-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="请输入验证码"
                value={code}
                onChange={(event) => {
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                  login.reset()
                }}
                aria-invalid={code.length > 0 && code.length !== 6}
                aria-describedby="auth-code-help"
                className="h-full rounded-none border-0 px-4 text-base shadow-none focus-visible:border-0 focus-visible:ring-0 md:text-base"
              />
              <Button
                type="button"
                variant="ghost"
                onClick={handleSendCode}
                disabled={!phoneIsValid || retryAfter > 0 || sendCode.isPending}
                className="h-full shrink-0 rounded-none px-4 text-sm text-foreground hover:bg-muted disabled:text-muted-foreground"
              >
                {sendCode.isPending ? "发送中…" : retryAfter > 0 ? `${retryAfter} 秒后重发` : "发送验证码"}
              </Button>
            </div>
            <p id="auth-code-help" className="sr-only">输入收到的 6 位短信验证码</p>
          </div>

          {sendCode.error ? <p role="alert" className="text-sm text-destructive">{sendCode.error.message}</p> : null}
          {login.error ? <p role="alert" className="text-sm text-destructive">{login.error.message}</p> : null}
          {debugCode ? <p role="status" className="text-sm text-muted-foreground">本地调试验证码：{debugCode}</p> : null}

          <Button type="submit" disabled={!phoneIsValid || code.length !== 6 || login.isPending} className="h-12 w-full rounded-xl text-sm font-medium">
            {login.isPending ? "正在登录…" : "登录"}
          </Button>
        </form>
        <p className="mt-4 text-center text-xs leading-5 text-muted-foreground">未注册手机号验证后将自动创建账号</p>
      </DialogContent>
    </Dialog>
  )
}
