import { SparklesIcon } from "lucide-react"

import { Button } from "@/components/ui/button"

export function SiteHeader() {
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
