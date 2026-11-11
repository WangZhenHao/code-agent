import { cn } from "@/lib/utils"

type BrandMarkProps = {
  /** 直径，单位 px */
  size?: number
  className?: string
}

export default function BrandMark({ size = 56, className }: BrandMarkProps) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cn(
        "relative flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-fuchsia-500 via-violet-500 to-blue-500",
        className
      )}
    >
      <svg
        viewBox="0 0 24 24"
        style={{ width: size / 2, height: size / 2 }}
        className="text-primary-foreground"
      >
        <path
          fill="currentColor"
          d="M12 4c1.8 2.7 5 5.4 5 9a5 5 0 0 1-10 0c0-3.6 3.2-6.3 5-9Z"
        />
      </svg>
    </span>
  )
}
