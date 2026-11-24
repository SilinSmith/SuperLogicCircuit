import { render, screen } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { uartNode } from "../../test/fixtures";
import { ModuleNode } from "./ModuleNode";
import type { FlowNode, ModuleNodeData } from "../types";

function renderNode(node = uartNode) {
  const props = {
    id: node.id,
    type: "module",
    data: { graph: node } satisfies ModuleNodeData,
    selected: false,
    isConnectable: true,
    zIndex: 0,
    dragging: false,
    selectable: true,
    deletable: true,
    draggable: true,
    position: { x: 0, y: 0 },
  } as unknown as NodeProps<FlowNode>;
  return render(
    <ReactFlowProvider>
      <ModuleNode {...props} />
    </ReactFlowProvider>,
  );
}

describe("ModuleNode", () => {
  it("快照稳定", () => {
    const { container } = renderNode();
    expect(container).toMatchSnapshot();
  });

  it("展示模块名、端口与位宽，超出 8 个端口折叠", () => {
    renderNode();
    expect(screen.getByText("uart")).toBeInTheDocument();
    expect(screen.getByText("module")).toBeInTheDocument();
    expect(screen.getByText("cfg")).toBeInTheDocument();
    expect(screen.getByText("8b")).toBeInTheDocument();
    expect(screen.getByText("sys")).toBeInTheDocument();
  });

  it("端口超过上限时给出 +N 提示", () => {
    const many = {
      ...uartNode,
      ports: Array.from({ length: 10 }, (_, index) => ({
        name: `p${index}`,
        dir: "input" as const,
        width_bits: 1,
      })),
    };
    renderNode(many);
    expect(screen.getByText("+2 个端口")).toBeInTheDocument();
  });
});
