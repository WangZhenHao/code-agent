/** 与后端约定的资源类型。字段将来由 packages/protocol 生成，这里先手写占位。 */

export type SessionStatus = 'running' | 'idle' | 'failed' | 'archived'

export interface Session {
  id: string
  title: string
  status: SessionStatus
  /** 同一个会话对应的 LangGraph thread_id，也是沙箱标签的来源 */
  threadId: string
  owner: string
  turns: number
  tokens: number
  createdAt: string
  updatedAt: string
}

export type SandboxPhase = 'pending' | 'running' | 'succeeded' | 'failed' | 'terminating'

export interface Sandbox {
  id: string
  sessionId: string
  phase: SandboxPhase
  image: string
  node: string
  cpu: string
  memory: string
  /** 沙箱为空表示还没建立连接时，这里是 null */
  startedAt: string | null
  ageSeconds: number
}

export interface Overview {
  activeSessions: number
  runningSandboxes: number
  sandboxQuota: number
  tokensToday: number
  errorRate: number
  p95LatencyMs: number
}

/** 每个会话的算力/耗时趋势，用于总览图 */
export interface UsagePoint {
  time: string
  tokens: number
  sessions: number
}
