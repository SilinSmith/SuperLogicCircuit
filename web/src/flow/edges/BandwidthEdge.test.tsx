import { render, screen } from "@testing-library/react";
import { Position, ReactFlowProvider, type EdgeProps } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { dataEdge, clockEdge } from "../../test/fixtures";
import { edgeLabel } from "../../lib/bandwidth";
import { BandwidthEdge, BandwidthLabel } from "./BandwidthEdge";
import type { BandwidthEdgeData, FlowEdge } from "../types";

function renderEdge(edge = dataEdge) {
  const props = {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceX: 0,
    sourceY: 0,
    targetX: 240,
    targetY: 0,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { graph: edge } satisfies BandwidthEdgeData,
    selected: false,
    animated: false,
    interactionWidth: 20,
  } as unknown as EdgeProps<FlowEdge>;
  return render(
    <ReactFlowProvider>
      <svg>
        <BandwidthEdge {...props} />
      </svg>
    </ReactFlowProvider>,
  );
}

describe("BandwidthEdge", () => {
  it("快照稳定", () => {
    const { container } = renderEdge();
    expect(container).toMatchSnapshot();
  });

  it("derived 带宽显示 bits/cycle 与十进制 GB/s", () => {
    const { container } = render(<BandwidthLabel id={dataEdge.id} x={120} y={0} label={edgeLabel(dataEdge)} />);
    expect(container).toMatchSnapshot();
    expect(screen.getByTestId(`edge-label-${dataEdge.id}`)).toHaveTextContent(
      "8 bit/cyc · 0.050 GB/s (decimal)",
    );
  });

  it("时钟边只显示 clock 不足以表示带宽", () => {
    render(<BandwidthLabel id={clockEdge.id} x={120} y={0} label={edgeLabel(clockEdge)} />);
    expect(screen.getByTestId(`edge-label-${clockEdge.id}`)).toHaveTextContent("clock");
  });

  it("带宽来源与 trace 利用率使用不同标记", () => {
    const { rerender } = render(
      <BandwidthLabel id="e-explicit" x={0} y={0} label="12.8 GB/s" source="explicit" />,
    );
    expect(screen.getByTestId("edge-label-e-explicit")).toHaveTextContent("E");
    rerender(<BandwidthLabel id="e-derived" x={0} y={0} label="8 bit/cyc" source="derived" />);
    expect(screen.getByTestId("edge-label-e-derived")).toHaveTextContent("D");
    rerender(
      <BandwidthLabel id="e-trace" x={0} y={0} label="8 bit/cyc" source="trace" utilization={0.83} />,
    );
    expect(screen.getByTestId("edge-label-e-trace")).toHaveTextContent("T");
    expect(screen.getByTestId("edge-label-e-trace")).toHaveTextContent("83%");
  });
});
