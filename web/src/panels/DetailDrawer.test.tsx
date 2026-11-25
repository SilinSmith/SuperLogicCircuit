import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { uartNode } from "../test/fixtures";
import { DetailDrawer } from "./DetailDrawer";

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  writeText.mockClear();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
});

describe("DetailDrawer", () => {
  it("渲染端口表与定位信息", () => {
    render(<DetailDrawer node={uartNode} onClose={() => {}} />);
    expect(screen.getByRole("heading", { name: "uart" })).toBeInTheDocument();
    expect(screen.getByText("slc.yaml:23")).toBeInTheDocument();
    expect(screen.getByText("cfg")).toBeInTheDocument();
    expect(screen.getAllByText("8").length).toBeGreaterThan(0);
  });

  it("slc:// 按钮复制带 file/line 的 URI", async () => {
    render(<DetailDrawer node={uartNode} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("slc-button"));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const uri = String(writeText.mock.calls[0][0]);
    expect(uri).toContain("slc://open?");
    expect(uri).toContain("file=slc.yaml");
    expect(uri).toContain("line=23");
    expect(await screen.findByText(/已复制/)).toBeInTheDocument();
  });

  it("无 loc 的节点禁用跳转按钮", () => {
    render(<DetailDrawer node={{ ...uartNode, id: "stats:demo", loc: null }} onClose={() => {}} />);
    expect(screen.getByTestId("slc-button")).toBeDisabled();
    expect(screen.getByText(/没有 loc/)).toBeInTheDocument();
  });
});
