import { useEffect, useState } from "react";
import type { GraphNode } from "../../contracts/node_graph";
import { buildRvgenUri, copyRvgenUri, openRvgenUri } from "../lib/rvopen";
import { typeLabel } from "../flow/nodes/ModuleNode";

export interface DetailDrawerProps {
  node: GraphNode | null;
  onClose: () => void;
}

export function DetailDrawer({ node, onClose }: DetailDrawerProps) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    setCopyState("idle");
  }, [node?.id]);

  if (!node) return null;
  const uri = buildRvgenUri(node);

  const handleOpen = () => {
    if (!uri) return;
    openRvgenUri(uri);
    void copyRvgenUri(uri).then((result) => setCopyState(result === "copied" ? "copied" : "failed"));
  };

  const handleCopy = async () => {
    if (!uri) return;
    const result = await copyRvgenUri(uri);
    setCopyState(result === "copied" ? "copied" : "failed");
  };

  return (
    <aside className="detail-drawer" data-testid="detail-drawer" aria-label={`节点详情 ${node.label}`}>
      <header className="detail-drawer__header">
        <div>
          <h2>{node.label}</h2>
          <p className="detail-drawer__id">{node.id}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭详情">
          ×
        </button>
      </header>

      <dl className="detail-drawer__facts">
        <div>
          <dt>类型</dt>
          <dd>{typeLabel(node)}</dd>
        </div>
        <div>
          <dt>模块</dt>
          <dd>{node.module ?? "-"}</dd>
        </div>
        <div>
          <dt>时钟域</dt>
          <dd>{node.domain ?? "-"}</dd>
        </div>
        <div>
          <dt>时钟</dt>
          <dd>{node.clock ?? "-"}</dd>
        </div>
        <div>
          <dt>位置</dt>
          <dd>{node.loc ? `${node.loc.file}:${node.loc.line}` : "未知（W10）"}</dd>
        </div>
        {node.status ? (
          <div>
            <dt>状态</dt>
            <dd>{node.status}</dd>
          </div>
        ) : null}
      </dl>

      <section className="detail-drawer__ports">
        <h3>端口</h3>
        {node.ports && node.ports.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>名字</th>
                <th>方向</th>
                <th>位宽</th>
                <th>类型</th>
              </tr>
            </thead>
            <tbody>
              {node.ports.map((port) => (
                <tr key={port.name}>
                  <td>{port.name}</td>
                  <td>{port.dir}</td>
                  <td>
                    {typeof port.width_bits === "number"
                      ? port.width_bits
                      : (port.width_expr ?? "?")}
                    {port.unresolved ? ` (${port.unresolved})` : ""}
                  </td>
                  <td>{port.kind ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="detail-drawer__empty">无端口</p>
        )}
      </section>

      <footer className="detail-drawer__footer">
        <button type="button" onClick={handleOpen} disabled={!uri} data-testid="rvgen-open-button">
          在编辑器中打开
        </button>
        <button type="button" onClick={handleCopy} disabled={!uri} data-testid="rvgen-button">
          复制 rvgen://
        </button>
        {copyState === "copied" ? (
          <span>已请求打开；若未响应，rvgen:// 已复制（需先运行 scripts/register-rvopen-*）</span>
        ) : null}
        {copyState === "failed" ? <span>复制失败：请手动复制 {uri}</span> : null}
        {!uri ? <span>该节点没有 loc，无法跳转（W10）</span> : null}
      </footer>
    </aside>
  );
}
