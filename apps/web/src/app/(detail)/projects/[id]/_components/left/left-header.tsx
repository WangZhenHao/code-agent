"use client"

import { useRouter } from "next/navigation"
import { ChevronLeft } from "lucide-react"

const LeftHeader = ({className = ''}: { className?: string }) => {
  const router = useRouter()

  return <div className={`flex items-center h-14 shrink-0 py-3 px-0 text-foreground ${className}`}>
    <div className="flex flex-1 items-center">
      <div className="cursor-pointer" onClick={() => router.back()}>
            <ChevronLeft />
      </div>
      <div className="pl-3">标题</div>
    </div>
  </div>;
}

export default LeftHeader;
