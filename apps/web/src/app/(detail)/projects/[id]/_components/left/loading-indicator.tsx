"use client"

import { motion } from "motion/react"

import { cn } from "@/lib/utils"

/** 三点跳动 + 文案的加载态，用于历史拉取、等待模型首字等场景。 */
export function LoadingIndicator({
  label,
  className,
}: {
  label: string
  className?: string
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-2 py-1 text-sm text-muted-foreground",
        className
      )}
    >
      {label}
      <span aria-hidden className="inline-flex items-center gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="size-1.5 rounded-full bg-current"
            animate={{ scale: [0.6, 1, 0.6], opacity: [0.4, 1, 0.4] }}
            transition={{
              duration: 1.4,
              repeat: Infinity,
              ease: "easeInOut",
              delay: i * 0.16,
            }}
          />
        ))}
      </span>  
    </div>
  )
}
