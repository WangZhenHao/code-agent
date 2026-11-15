"use client"

import { Button } from "@/components/ui/button"
import BrandMark from "@/components/custom/BrandMark"

export function SiteHeader({ onLogin }: { onLogin: () => void }) {
  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center justify-between gap-4 px-4 sm:px-6">
      <div className="flex items-center gap-2">
        <BrandMark size={30} />
        <span className="text-base font-semibold">码灵编程</span>
      </div>

      <div className="flex items-center gap-3">
        <Button size="lg" className="rounded-full px-4" onClick={onLogin}>
          注册/登陆
        </Button>
      </div>
    </header>
  )
}
