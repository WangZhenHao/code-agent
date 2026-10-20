"use client"

import * as React from "react"
import { InfoIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group"
import { Separator } from "@/components/ui/separator"
import { cn } from "cn"
import BrandMark from "@/components/custom/BrandMark"

const LOGIN_INSTRUCTIONS = [
  "码灵账号页面全新升级",
  "登录即代表你已阅读并同意《用户协议》和《隐私政策》",
]

export function Login({ className }: { className?: string }) {
  const [phone, setPhone] = React.useState("")
  const [code, setCode] = React.useState("")
  const [agreed, setAgreed] = React.useState(false)

  const canSubmit = agreed && /^1\d{10}$/.test(phone) && code.length >= 4

  return (
    <div className={cn("flex w-full flex-col gap-6", className)}>
      <div className="flex flex-col items-center gap-4">
        <BrandMark />
        <h2 className="text-2xl font-semibold tracking-tight">欢迎使用码灵</h2>
      </div>

      <div className="flex flex-col gap-3">
        <InputGroup className="h-11 rounded-xl px-1">
          <InputGroupAddon className="pl-3">
            <InputGroupText className="text-foreground">+86</InputGroupText>
            <Separator orientation="vertical" className="h-4 self-center" />
          </InputGroupAddon>
          <InputGroupInput
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder="请输入手机号"
            maxLength={11}
            value={phone}
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
          />
        </InputGroup>

        <InputGroup className="h-11 rounded-xl">
          <InputGroupInput
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="请输入验证码"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          />
          <InputGroupAddon align="inline-end" className="pr-1">
            <InputGroupButton variant="ghost" className="text-muted-foreground">
              发送验证码
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </div>

      <label className="flex items-start gap-2 text-sm text-muted-foreground">
        <Checkbox
          className="mt-0.5"
          checked={agreed}
          onCheckedChange={(v) => setAgreed(v === true)}
        />
        已阅读并同意
        <a href="#" className="text-foreground hover:underline">
          用户协议
        </a>
        、
        <a href="#" className="text-foreground hover:underline">
          隐私政策
        </a>
      </label>

      <Button size="lg" className="h-11 rounded-xl" disabled={!canSubmit}>
        登录
      </Button>

      <div className="flex flex-col gap-3 text-sm text-muted-foreground">
        {LOGIN_INSTRUCTIONS.map((text) => (
          <p key={text} className="flex items-start gap-1.5 leading-relaxed">
            <InfoIcon className="mt-0.5 size-4 shrink-0" />
            <span>{text}</span>
          </p>
        ))}
      </div>
    </div>
  )
}

export type LoginDialogRef = {
  open: () => void
  close: () => void
}

export function LoginDialog({ ref }: { ref?: React.Ref<LoginDialogRef> }) {
  const [open, setOpen] = React.useState(false)

  React.useImperativeHandle(
    ref,
    () => ({
      open: () => setOpen(true),
      close: () => setOpen(false),
    }),
    []
  )

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="gap-0 rounded-3xl p-6 sm:max-w-105">
        <DialogTitle className="sr-only">登录码灵编程</DialogTitle>
        <Login />
      </DialogContent>
    </Dialog>
  )
}

export default Login
