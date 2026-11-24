import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

export interface EChartProps {
  option: EChartsCoreOption;
  height?: number;
  testId?: string;
  label: string;
}

/** 每次卸载必须 dispose；尺寸变化用 ResizeObserver，卸载时一并断开。 */
export function EChart({ option, height = 260, testId, label }: EChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = echarts.init(host, undefined, { renderer: "canvas" });
    chart.setOption(option);

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(host);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = echarts.getInstanceByDom(host);
    chart?.setOption(option, true);
  }, [option]);

  return (
    <div
      ref={hostRef}
      role="img"
      aria-label={label}
      data-testid={testId}
      style={{ width: "100%", height }}
    />
  );
}
