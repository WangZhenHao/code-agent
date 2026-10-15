import * as React from "react"

import { Badge } from "@/components/ui/badge"
import { Marquee } from "@/components/ui/marquee"
import { cn } from "@/lib/utils"

export function ExampleRow({
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
