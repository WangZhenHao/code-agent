import axios, { AxiosError } from "axios";
import type { AxiosRequestConfig, AxiosResponse } from "axios";

import { hasLoginFlag } from "@/lib/auth";
import { useUserStore } from "@/store/user";

/** 后端统一错误体（FastAPI 默认 `{"detail": ...}`） */
export interface ApiErrorBody {
  detail?: unknown;
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export const AXIOS_INSTANCE = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
});

AXIOS_INSTANCE.interceptors.request.use((config) => {
  const token = useUserStore.getState().token;
  if (token) config.headers.set("Authorization", `Bearer ${token}`);
  return config;
});

AXIOS_INSTANCE.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status ?? 0;
    const body = error.response?.data;
    const detail = body?.detail;
    const message =
      typeof detail === "string" ? detail : (error.message ?? "请求失败");

    // 令牌失效：清理会话并回登录页（登录接口本身的 401 交给调用方展示错误）
    if (status === 401 && typeof window !== "undefined") {
      const isLoginRequest = error.config?.url?.includes("/user/login");
      if (!isLoginRequest && hasLoginFlag()) {
        useUserStore.getState().logout();
        window.location.replace("/");
      }
    }

    return Promise.reject(new ApiError(status, message, body));
  },
);

/** Orval mutator：返回 response.data，hooks 的类型推断依赖这个签名 */
export const customInstance = <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig,
): Promise<T> => {
  const source = axios.CancelToken.source();
  const promise = AXIOS_INSTANCE({
    ...config,
    ...options,
    cancelToken: source.token,
  }).then((response: AxiosResponse<T>) => response.data);

  // @ts-expect-error Orval 约定：给返回的 promise 挂上 cancel，供 hook 的 AbortSignal 用
  promise.cancel = () => source.cancel("Query was cancelled");

  return promise;
};

export type ErrorType<Error> = AxiosError<Error>;
export type BodyType<Body> = Body;

export default customInstance;
