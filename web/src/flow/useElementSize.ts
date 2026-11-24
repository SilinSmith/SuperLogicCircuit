import { useCallback, useEffect, useRef, useState, type RefCallback } from "react";

export interface ElementSize {
  width: number;
  height: number;
}

const EMPTY: ElementSize = { width: 0, height: 0 };

/**
 * 观察容器尺寸。视图卸载时必须 disconnect（R05 泄漏清单），
 * 因此这里把 observer 生命周期收敛到一个 hook，便于单测断言。
 */
export function useElementSize<T extends HTMLElement>(): [RefCallback<T>, ElementSize] {
  const [size, setSize] = useState<ElementSize>(EMPTY);
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback<RefCallback<T>>((element) => {
    observerRef.current?.disconnect();
    observerRef.current = null;
    if (!element || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const box = entry.contentRect;
      setSize({ width: box.width, height: box.height });
    });
    observer.observe(element);
    observerRef.current = observer;

    const rect = element.getBoundingClientRect();
    setSize({ width: rect.width, height: rect.height });
  }, []);

  useEffect(
    () => () => {
      observerRef.current?.disconnect();
      observerRef.current = null;
    },
    [],
  );

  return [ref, size];
}
