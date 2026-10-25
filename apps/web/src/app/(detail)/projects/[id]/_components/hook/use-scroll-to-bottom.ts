"use client";

import { useCallback, useEffect, useRef } from "react";

// 距离底部多少像素以内算「贴着底部」。留点余量：流式内容在两次滚动之间会
// 先长高几像素，判定太严会让自动跟随提前断掉。
const STICK_THRESHOLD = 32;

/**
 * 聊天列表的滚动控制。
 *
 * - `scrollToBottom()`：无条件置底，用于「进会话拿到历史」「提交新消息」这类
 *   必须回到最新一条的时机，用户正往上翻也照样拉回来。
 * - 内容变化后的自动跟随：只有当前仍贴着底部才继续滚；用户手动往上翻过就停，
 *   直到他自己滚回底部才恢复。
 *
 * 内容增长用 ResizeObserver 观察而不是依赖 React 的依赖数组：流式 token、
 * 图片加载、代码块重排都会改变高度，而它们不一定让某个 prop 的引用变化。
 */
export const useScrollToBottom = () => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // 真正承载消息内容的容器（滚动容器的子元素），高度变化从它身上观察。
  const contentRef = useRef<HTMLDivElement | null>(null);
  // 是否跟随底部。用户往上滚就置 false，滚回底部再置 true。
  const stickToBottomRef = useRef(true);

  // 统一用瞬时滚动：平滑滚动途中的中间位置会被 handleScroll 判成「不在底部」，
  // 长历史下一路滚下来还会和流式新增内容打架。
  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottomRef.current = true;
    el.scrollTop = el.scrollHeight;
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceToBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceToBottom <= STICK_THRESHOLD;
  }, []);

  useEffect(() => {
    const content = contentRef.current;
    const el = scrollRef.current;
    if (!content || !el) return;

    const observer = new ResizeObserver(() => {
      if (!stickToBottomRef.current) return;
      el.scrollTop = el.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  return { scrollRef, contentRef, handleScroll, scrollToBottom };
};
