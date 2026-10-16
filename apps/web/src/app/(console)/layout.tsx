import { AppSidebar } from "./_components/sidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

// 路由组 (console) 下的 layout 未被 next typegen 枚举进 LayoutProps，这里直接声明 props。
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider className="h-svh min-h-0 overflow-hidden">
      <AppSidebar />
      <SidebarInset className="overflow-y-auto">{children}</SidebarInset>
    </SidebarProvider>
  )
}
