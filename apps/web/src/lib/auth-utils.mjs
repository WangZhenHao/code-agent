/** @param {unknown} value @returns {string | null} */
export function safeRelativePath(value) {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    return null
  }

  try {
    const url = new URL(value, "https://local.invalid")
    if (url.origin !== "https://local.invalid") return null
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return null
  }
}

/** @param {string} pathname @returns {boolean} */
export function isProtectedPath(pathname) {
  return pathname === "/create" || pathname === "/projrects" || pathname.startsWith("/projrects/")
}

/** @param {string} pathname @param {string} search @returns {string} */
export function loginRedirectPath(pathname, search) {
  const returnTo = safeRelativePath(`${pathname}${search}`) || "/"
  const query = new URLSearchParams({ login: "true", redirect_url: returnTo })
  return `/?${query.toString()}`
}
