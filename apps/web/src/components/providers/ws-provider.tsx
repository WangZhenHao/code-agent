"use client";

/**
 * 会话级 WebSocket 的 React 入口。
 *
 * 挂载在会话页面最外层，整棵子树共享同一条连接：
 *   - `useWs().sendWs(method, params)` 发请求
 *   - `useWsEvent(method, handler)` 订阅后端推送，handler 里自己 setState
 *
 * 数据不放进 context value：推送频率由后端决定（心跳 25s 一条，业务推送可能更密），
 * 塞进 value 会让每次推送都重渲染所有消费者。context 只承载稳定的 `sendWs`。
 */

import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";

import { createWsClient } from "@/lib/ws/client";
import type { WsClient } from "@/lib/ws/client";

interface WsContextValue {
  sendWs: (method: string, params: Record<string, unknown>) => void;
}

const WsContext = createContext<WsContextValue | null>(null);
/** 订阅用的 client 单独放一个 context：不对外暴露，避免组件直接操作连接 */
const WsClientContext = createContext<WsClient | null>(null);

export function WsProvider({
  devboxId,
  children,
}: {
  devboxId: string;
  children: ReactNode;
}) {
  const client = useMemo(() => createWsClient({ devboxId }), [devboxId]);

  useEffect(() => {
    client.connect();
    return () => client.close();
  }, [client]);

  const value = useMemo<WsContextValue>(
    () => ({ sendWs: (method, params) => client.sendWs(method, params) }),
    [client],
  );

  return (
    <WsClientContext.Provider value={client}>
      <WsContext.Provider value={value}>{children}</WsContext.Provider>
    </WsClientContext.Provider>
  );
}

export function useWs(): WsContextValue {
  const ctx = useContext(WsContext);
  if (!ctx) throw new Error("useWs 必须在 <WsProvider> 内使用");
  return ctx;
}

/**
 * 订阅后端推送。`handler` 放进 ref，调用方不必 useCallback 包裹：
 * 组件重渲染不会退订重订，连接上的订阅表只有一条。
 */
export function useWsEvent(
  method: string,
  handler: (params: Record<string, unknown>) => void,
) {
  const client = useContext(WsClientContext);
  const handlerRef = useRef(handler);

  if (!client) throw new Error("useWsEvent 必须在 <WsProvider> 内使用");

  // ref 的写必须在 effect 里：render 期间写 ref 会被 react-hooks/refs 判错。
  // 这个 effect 在下方订阅 effect 之前声明，每次 render 都先把最新 handler 落进 ref。
  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(
    () => client.subscribe(method, (params) => handlerRef.current(params)),
    [client, method],
  );
}
