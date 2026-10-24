/**
 * `GET /chat/message/{id}` 的 `parts` → LangChain 消息。
 *
 * 两轮消息的 parts 形状不一样（见 api/chat/schemas.py 的 `MessageItem`）：
 * - user 消息：请求体里的 ContentBlock，如 `{ type: "text", text }`；
 * - assistant 消息：`message_to_dict()` 的结果，形如
 *   `{ type: "ai", data: { content, tool_calls, id, … } }`，一轮里有多条
 *   （模型回复 + 工具调用 + 最终答复）。
 *
 * 转换目标是 `BaseMessage`，和 SSE 的 `stream.messages` 同形，这样两边
 * 共用同一个渲染组件，也共享 `message.text` / `tool_calls` / `id` 的语义。
 */

import {
  HumanMessage,
  mapStoredMessageToChatMessage,
  type BaseMessage,
  type MessageContent,
  type StoredMessage,
} from "@langchain/core/messages";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** 把一条 MessageItem（的 parts）展开成可渲染的消息。 */
export function toHistoryMessages(item: {
  id: string;
  role: string;
  parts?: unknown;
}): BaseMessage[] {
  const parts = Array.isArray(item.parts) ? item.parts : [];
  if (item.role === "user") {
    // parts 本身就是 ContentBlock[]，直接当 content 用；连带 id 一起给出去，
    // 和 assistant 行一样有稳定的消息 id。
    const message = new HumanMessage({
      id: item.id,
      content: parts as MessageContent,
    });
    return message.text ? [message] : [];
  }

  const result: BaseMessage[] = [];
  for (const part of parts) {
    if (!isRecord(part) || !isRecord(part.data)) continue;
    // 只渲染模型产出的消息；工具结果（type=tool）不单独成气泡。
    if (part.type !== "ai") continue;
    try {
      // data 原样喂给构造函数：content / tool_calls / id 都在里面，
      // 由 langchain 自己的反序列化负责，不在这里手挑字段。
      result.push(
        mapStoredMessageToChatMessage(part as unknown as StoredMessage),
      );
    } catch {
      // 未知 type 或字段缺失时跳过这一条，不拖垮整轮历史。
    }
  }
  return result;
}
