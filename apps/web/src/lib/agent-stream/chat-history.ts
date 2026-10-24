/**
 * `GET /chat/message/{id}` 的 `parts` → 展示用文本。
 *
 * 两轮消息的 parts 形状不一样（见 api/chat/schemas.py 的 `MessageItem`）：
 * - user 消息：请求体里的 ContentBlock，如 `{ type: "text", text }`；
 * - assistant 消息：`message_to_dict()` 的结果，形如
 *   `{ type: "ai", data: { content, tool_calls, id, … } }`，一轮里有多条
 *   （模型回复 + 工具调用 + 最终答复）。
 *
 * 这里只抽「能显示的文字」，工具调用交给调用方从 `toolCalls` 里取。
 */

export interface HistoryMessage {
  /** 稳定 key：assistant 用 LangChain 消息 id，user 用行 id */
  key: string;
  /** LangChain 消息 id；user 行没有，用来和 SSE 消息去重 */
  langchainId?: string;
  role: "user" | "assistant";
  text: string;
  toolCalls: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** `content` 可能是字符串，也可能是 content block 数组。 */
function textOfContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .flatMap((block) =>
      isRecord(block) && block.type === "text" && typeof block.text === "string"
        ? [block.text]
        : [],
    )
    .join("");
}

/** 把一条 MessageItem（的 parts）展开成可渲染的多条。 */
export function toHistoryMessages(item: {
  id: string;
  role: string;
  parts?: unknown;
}): HistoryMessage[] {
  const parts = Array.isArray(item.parts) ? item.parts : [];
  if (item.role === "user") {
    const text = parts
      .flatMap((part) =>
        isRecord(part) && part.type === "text" && typeof part.text === "string"
          ? [part.text]
          : [],
      )
      .join("\n");
    return text ? [{ key: item.id, role: "user", text, toolCalls: [] }] : [];
  }

  const result: HistoryMessage[] = [];
  parts.forEach((part, index) => {
    if (!isRecord(part) || !isRecord(part.data)) return;
    const data = part.data;
    // 只渲染模型产出的消息；工具结果（type=tool）不单独成气泡。
    if (part.type !== "ai") return;
    const langchainId = typeof data.id === "string" ? data.id : undefined;
    const toolCalls = Array.isArray(data.tool_calls)
      ? data.tool_calls.flatMap((call) =>
          isRecord(call) && typeof call.name === "string" ? [call.name] : [],
        )
      : [];
    const text = textOfContent(data.content);
    if (!text && toolCalls.length === 0) return;
    result.push({
      key: langchainId ?? `${item.id}-${index}`,
      langchainId,
      role: "assistant",
      text,
      toolCalls,
    });
  });
  return result;
}
