"use client";

import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

import { clearLoginFlag, setLoginFlag } from "@/lib/auth";
import type { LoginResponse, UserInfo } from "@/api/generated/model";

interface UserState {
  token: string | null;
  user: UserInfo | null;
  login: (res: LoginResponse) => void;
  logout: () => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      login: (res) => {
        setLoginFlag(res.expires_in);
        set({ token: res.access_token, user: res.user });
      },
      logout: () => {
        clearLoginFlag();
        set({ token: null, user: null });
      },
    }),
    {
      name: "code-agent-user",
      partialize: (state) => ({ token: state.token, user: state.user }),
    },
  ),
);

/** persist 在客户端挂载后才完成回填，用该标记避免 SSR / 首屏渲染不一致 */
export function useHydrated() {
  return useSyncExternalStore(
    (onChange) => {
      // 服务端（SSR）拿不到 persist API，回退到普通 store 订阅
      const persist = useUserStore.persist;
      if (!persist) return useUserStore.subscribe(onChange);
      const unsubscribeHydration = persist.onFinishHydration(onChange);
      const unsubscribeStore = useUserStore.subscribe(onChange);
      return () => {
        unsubscribeHydration();
        unsubscribeStore();
      };
    },
    () => useUserStore.persist?.hasHydrated() ?? false,
    () => false,
  );
}
