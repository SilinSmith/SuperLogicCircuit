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
});
