/**
 * 登录标记 cookie：不存放令牌，只给 Next proxy 做路由判断（JS 可读，非 httpOnly）。
 * 令牌本身由 zustand persist 保存，请求头由 http.ts 从 store 读取。
 */
export const LOGIN_FLAG_COOKIE = "logged_in";

const DEFAULT_MAX_AGE = 7 * 24 * 60 * 60; // 7 天，与后端令牌有效期一致

export function setLoginFlag(maxAge = DEFAULT_MAX_AGE) {
  if (typeof document === "undefined") return;
  document.cookie = `${LOGIN_FLAG_COOKIE}=1; path=/; max-age=${maxAge}; SameSite=Lax`;
}

export function hasLoginFlag(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie
    .split("; ")
    .some((item) => item.startsWith(`${LOGIN_FLAG_COOKIE}=`));
}

export function clearLoginFlag() {
  if (typeof document === "undefined") return;
  document.cookie = `${LOGIN_FLAG_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}
