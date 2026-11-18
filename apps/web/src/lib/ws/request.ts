/**
 * 请求方法的类型化调用入口。
 *
 * `useWs().call<T>` 只认识裸字符串和手写的 `T`；这里把生成物里的
 * `WsRequestParams` / `WsRequestResult` 绑到方法名上，method 写错、params 字段
 * 对不上、result 用错属性都是编译期错误。
 *
 * 方法清单来自 `apps/api` 的 `@rpc_method` 登记（`make gen-ws` 生成），
 * 不要手改 generated/contract.ts。
 */

"use client"

import { useCallback, useMemo } from "react"

import { useWs } from "@/components/providers/ws-provider"
import type {
  WsRequestMethod,
  WsRequestParams,
  WsRequestResult,
} from "@/lib/ws/generated/contract"

/** `call()` 失败时抛的错误。`code` 是 JSON-RPC 错误码（如 -32001 = 找不到）。 */
export type WsRequestError = Error & { code?: number }

/** 文件不存在 / 路径越界（后端 `schemas.RESOURCE_NOT_FOUND`）。 */
export const RESOURCE_NOT_FOUND = -32001

export function useWsRequest() {
  const { call } = useWs()

  const invoke = useCallback(
    <M extends WsRequestMethod>(
      method: M,
      params: WsRequestParams[M],
      timeoutMs?: number
    ): Promise<WsRequestResult[M]> =>
      call<WsRequestResult[M]>(
        method,
        params as Record<string, unknown>,
        timeoutMs
      ),
    [call]
  )

  return useMemo(() => ({ invoke }), [invoke])
}
