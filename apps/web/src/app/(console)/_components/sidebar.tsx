"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  BellIcon,
  ChevronsUpDownIcon,
  CirclePlusIcon,
  InfoIcon,
  LayoutGridIcon,
  Settings2Icon,
  Share2Icon,
  SparklesIcon,
} from "lucide-react"
import * as React from "react"

type NavItem = {
  title: string
  icon: React.ComponentType
  /** 未提供 href 的条目为占位项，暂不可点击 */
  href?: string
  hint?: "notice" | "new"
}

type NavGroup = {
  label: string
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "项目",
    items: [
      { title: "项目管理", icon: LayoutGridIcon, href: "/projects" },
    ],
  }
]

const USER = {
  name: "广宝哥",
  email: "guangbao@example.com",
  avatar: "/home/1.png",
}

export function AppSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const [logoutOpen, setLogoutOpen] = React.useState(false)

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-3">
        <div className="flex h-8 items-center gap-2 px-1">
          <Button
            asChild
            variant="ghost"
            size="icon-sm"
            className="shrink-0 group-data-[collapsible=icon]:hidden"
          >
            <Link href="/create" aria-label="码灵编程首页">
              <SparklesIcon />
            </Link>
          </Button>
          <span className="truncate text-sm font-semibold group-data-[collapsible=icon]:hidden">
            码灵编程
          </span>
          <Badge
            variant="secondary"
            className="ml-0.5 h-4 rounded-sm px-1 text-[10px] font-normal"
          >
            NEW
          </Badge>
          <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:ml-0" />
        </div>

        <SidebarMenu className="gap-1.5">
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              tooltip="新建项目"
              className="bg-primary font-medium text-primary-foreground hover:bg-primary/80 hover:text-primary-foreground"
            >
              <Link href="/create">
                <CirclePlusIcon />
                <span>新建项目</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <PlaceholderOrLink
                    key={item.title}
                    item={item}
                    active={item.href === pathname}
                  />
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="gap-2">

        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton size="lg" tooltip={USER.name} className="pr-8">
                  <Avatar className="size-8">
                    <AvatarImage src={USER.avatar} alt={USER.name} />
                    <AvatarFallback>{USER.name.slice(0, 1)}</AvatarFallback>
                  </Avatar>
                  <span className="truncate text-sm font-medium group-data-[collapsible=icon]:hidden">{USER.name}</span>
                  <ChevronsUpDownIcon />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <SidebarMenuAction aria-label="通知" className="top-2 right-2">
                <BellIcon />
                <span className="absolute top-1 right-1 size-1.5 rounded-full bg-destructive" />
              </SidebarMenuAction>
              <DropdownMenuContent
                side="top"
                align="start"
                sideOffset={8}
                className="w-(--radix-dropdown-menu-trigger-width) min-w-56"
              >
                <DropdownMenuGroup>
                  <DropdownMenuItem onSelect={() => router.push("/settings/profile")}>
                    <Share2Icon />
                    用户信息设置
                  </DropdownMenuItem>
                  <DropdownMenuItem>
                    <Settings2Icon />
                    通用设置
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem>
                    <InfoIcon />
                    帮助与反馈
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => setLogoutOpen(true)}
                  >
                    退出登录
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <LogoutDialog open={logoutOpen} onOpenChange={setLogoutOpen} />
    </Sidebar>
  )
}

function PlaceholderOrLink({ item, active }: { item: NavItem; active: boolean }) {
  const { isMobile, setOpenMobile } = useSidebar()

  const content = (
    <>
      <item.icon />
      <span>{item.title}</span>
    </>
  )

  if (!item.href) {
    return (
      <SidebarMenuItem>
        <SidebarMenuButton aria-disabled tooltip={item.title}>
          {content}
        </SidebarMenuButton>
      </SidebarMenuItem>
    )
  }

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
        <Link
          href={item.href}
          onClick={() => {
            if (isMobile) setOpenMobile(false)
          }}
        >
          {content}
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function LogoutDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>退出登录</DialogTitle>
          <DialogDescription>
            退出后需要重新登录才能继续使用码灵编程。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              onOpenChange(false)
              // TODO: 接入实际的登出逻辑（清理会话后跳转登录页）
            }}
          >
            确认退出
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
