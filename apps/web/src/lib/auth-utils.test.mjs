import assert from "node:assert/strict"
import test from "node:test"
import { isProtectedPath, loginRedirectPath, safeRelativePath } from "./auth-utils.mjs"

test("only existing console pages require login", () => {
  assert.equal(isProtectedPath("/"), false)
  assert.equal(isProtectedPath("/create"), true)
  assert.equal(isProtectedPath("/projrects"), true)
  assert.equal(isProtectedPath("/projrects/abc123"), true)
  assert.equal(isProtectedPath("/missing"), false)
})

test("safeRelativePath accepts a same-site path and rejects open redirects", () => {
  assert.equal(safeRelativePath("/projrects/42?tab=files"), "/projrects/42?tab=files")
  assert.equal(safeRelativePath("https://evil.example/path"), null)
  assert.equal(safeRelativePath("//evil.example/path"), null)
  assert.equal(safeRelativePath("/\\evil.example"), null)
})

test("login redirect preserves the protected path as an encoded relative target", () => {
  const redirect = new URL(loginRedirectPath("/projrects", "?tab=recent"), "https://app.example")
  assert.equal(redirect.origin, "https://app.example")
  assert.equal(redirect.searchParams.get("login"), "true")
  assert.equal(redirect.searchParams.get("redirect_url"), "/projrects?tab=recent")
})
