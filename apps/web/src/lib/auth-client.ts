"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import axios from "axios"
import type { AxiosRequestConfig } from "axios"
import type { LoginRequest, LoginResponse, MeResponse, SendCodeRequest, SendCodeResponse, UserInfo } from "@/generated/user-models"

const TOKEN_KEY = "maling_access_token"
// Production Ingress forwards /user and /chat directly to FastAPI on this origin.
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || (process.env.NODE_ENV === "production" ? "" : "http://127.0.0.1:8000"),
  timeout: 8_000,
})

type ApiErrorBody = { detail?: unknown; message?: unknown }

export class AuthRequestError extends Error {
  retryAfterSeconds?: number
  status?: number

  constructor(message: string, retryAfterSeconds?: number, status?: number) {
    super(message)
    this.name = "AuthRequestError"
    this.retryAfterSeconds = retryAfterSeconds
    this.status = status
  }
}

function token() {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY)
}

async function requestJson<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  try {
    const accessToken = token()
    const response = await api.request<T>({
      url,
      ...config,
      headers: { ...config?.headers, ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
    })
    return response.data
  } catch (error) {
    if (!axios.isAxiosError<ApiErrorBody>(error)) throw error
    if (!error.response) throw new AuthRequestError("无法连接服务，请检查网络后重试。")
    const status = error.response.status
    if (status === 401) window.localStorage.removeItem(TOKEN_KEY)
    const detail = error.response.data?.detail
    const message = error.response.data?.message
    const retryAfterSeconds = Number(error.response.headers["retry-after"]) || undefined
    throw new AuthRequestError(
      status >= 500 ? "服务暂不可用，请稍后重试。" :
        typeof detail === "string" && detail.trim() ? detail :
        typeof message === "string" && message.trim() ? message : "请求失败，请稍后重试。",
      retryAfterSeconds,
      status,
    )
  }
}

export function useCurrentUser() {
  return useQuery<MeResponse | UserInfo | null>({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      if (!token()) return null
      try {
        return await requestJson<MeResponse>("/user/me")
      } catch (error) {
        if (error instanceof AuthRequestError && error.status === 401) return null
        throw new AuthRequestError("暂时无法获取登录状态。")
      }
    },
    retry: false,
    staleTime: 60_000,
  })
}

export function useSendCode() {
  return useMutation({
    mutationFn: (payload: SendCodeRequest) => requestJson<SendCodeResponse>("/user/send_code", { method: "POST", data: payload }),
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (credentials: LoginRequest) => {
      const result = await requestJson<LoginResponse>("/user/login", { method: "POST", data: credentials })
      if (
        typeof result.access_token !== "string" || !result.access_token ||
        !Number.isSafeInteger(result.expires_in) || result.expires_in < 1 ||
        typeof result.user?.id !== "number"
      ) {
        throw new AuthRequestError("登录服务返回了无效响应，请稍后重试。")
      }
      return result
    },
    onSuccess: (result) => {
      window.localStorage.setItem(TOKEN_KEY, result.access_token)
      queryClient.setQueryData(["auth", "me"], result.user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      window.localStorage.removeItem(TOKEN_KEY)
      queryClient.setQueryData(["auth", "me"], null)
    },
  })
}

export function useCreateChat() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { prompt: string; mode: "agent" | "plan" }) =>
      requestJson<{ id: string }>("/chat/create", {
        method: "POST",
        data: { mode: input.mode, parts: [{ type: "text", text: input.prompt.trim() }] },
        timeout: 15_000,
      }),
    onError: (error) => {
      if (error instanceof AuthRequestError && error.status === 401) queryClient.setQueryData(["auth", "me"], null)
    },
  })
}
