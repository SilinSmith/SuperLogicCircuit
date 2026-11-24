import { useCallback, useEffect, useState } from "react";
import type { GraphNode, NodeGraph } from "../contracts/node_graph";
import { GraphLoadError, loadGraph, resolveGraphUrl } from "./api/graph";
import { DetailDrawer } from "./panels/DetailDrawer";
import { DataflowView } from "./views/DataflowView";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; graph: NodeGraph; url: string }
  | { status: "error"; message: string; detail?: string; url: string };

export function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const url = resolveGraphUrl();
    setState({ status: "loading" });
    setSelected(null);
    loadGraph(url, controller.signal)
      .then((graph) => setState({ status: "ready", graph, url }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const message = error instanceof GraphLoadError ? error.message : "加载 node_graph.json 失败";
        const detail =
          error instanceof GraphLoadError
            ? error.detail
            : error instanceof Error
              ? error.message
              : String(error);
        setState({ status: "error", message, detail, url });
      });
    return () => controller.abort();
  }, [reloadToken]);

  const handleSelect = useCallback((node: GraphNode) => setSelected(node), []);
  const handleClose = useCallback(() => setSelected(null), []);

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__brand">
          <span className="app__logo">rvgen</span>
          <span className="app__subtitle">静态结构看板</span>
        </div>
        <div className="app__meta" data-testid="graph-meta">
          {state.status === "ready" ? (
            <>
              <span>{state.graph.nodes.length} 节点</span>
              <span>{state.graph.edges.length} 边</span>
              <span className="app__digest">{state.graph.source_digest.slice(0, 16)}</span>
              <span className="app__url">{state.url}</span>
            </>
          ) : null}
        </div>
        <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
          重新加载
        </button>
      </header>

      <main className="app__main">
        {state.status === "loading" ? <div className="app__placeholder">正在加载 node_graph.json…</div> : null}
        {state.status === "error" ? (
          <div className="app__error" role="alert">
            <h2>{state.message}</h2>
            {state.detail ? <p>{state.detail}</p> : null}
            <p>
              数据源：<code>{state.url}</code>
            </p>
            <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </button>
          </div>
        ) : null}
        {state.status === "ready" ? (
          <>
            <DataflowView graph={state.graph} onSelectNode={handleSelect} />
            <DetailDrawer node={selected} onClose={handleClose} />
          </>
        ) : null}
      </main>
    </div>
  );
}
