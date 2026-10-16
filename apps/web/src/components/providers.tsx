"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { useCurrentUser } from "@/lib/auth-client"
import { isProtectedPath, loginRedirectPath } from "@/lib/auth-utils.mjs"

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  )

  return <QueryClientProvider client={queryClient}><AuthGate>{children}</AuthGate></QueryClientProvider>
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const user = useCurrentUser()
  const protectedPath = isProtectedPath(pathname)

  useEffect(() => {
    if (protectedPath && !user.isPending && !user.isError && !user.data) {
      router.replace(loginRedirectPath(pathname, window.location.search))
    }
  }, [pathname, protectedPath, router, user.data, user.isError, user.isPending])

  if (!protectedPath) return <>{children}</>
  if (user.isError) {
    return <div role="alert" className="flex min-h-screen items-center justify-center gap-3">{user.error.message}<Button variant="outline" onClick={() => user.refetch()}>重试</Button></div>
  }
  return user.data ? <>{children}</> : null
}
