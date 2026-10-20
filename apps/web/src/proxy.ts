import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

/** 与 src/lib/auth.ts 的 LOGIN_FLAG_COOKIE 保持一致（proxy 不引用客户端模块） */
const LOGIN_FLAG_COOKIE = "logged_in"

/**
 * 登录态守卫：
 * - 未登录访问控制台路由 → 回到 "/"（登录页）
 * - 已登录访问 "/" → 进入 "/create"
 *
 * 注意：这里只判断 cookie 是否存在，令牌是否有效由后端接口（401）兜底。
 */
export function proxy(request: NextRequest) {
  const loggedIn = Boolean(request.cookies.get(LOGIN_FLAG_COOKIE)?.value)
  const { pathname } = request.nextUrl

  if (!loggedIn && pathname !== "/") {
    return NextResponse.redirect(new URL("/", request.url))
  }

  if (loggedIn && pathname === "/") {
    return NextResponse.redirect(new URL("/create", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/", "/create", "/projects/:path*", "/settings/:path*"],
}
