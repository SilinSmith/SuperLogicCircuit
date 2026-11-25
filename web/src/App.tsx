import { useCallback, useEffect, useMemo, useState } from "react";
import type { GraphNode, NodeGraph } from "../contracts/node_graph";
import { connectEvents, eventsUrl } from "./api/events";
import { GraphLoadError, isLiveSource, loadGraph, resolveGraphUrl } from "./api/graph";
import { loadSummary, resolveSummaryUrl } from "./api/summary";
import {
  mergeLayoutFile,
  readLayout,
  recordPosition,
  writeLayout,
  type LayoutFile,
} from "./lib/layout";
import { DetailDrawer } from "./panels/DetailDrawer";
import { DataflowView } from "./views/DataflowView";
import { ClockTreeView } from "./views/ClockTreeView";
import { StatsView } from "./views/StatsView";
import { availablePluginViews } from "./plugins/registry";
import type { TraceSummary } from "./lib/stats";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; graph: NodeGraph; url: string }
  | { status: "error"; message: string; detail?: string; url: string };

const CORE_VIEWS = [
  { id: "dataflow", title: "数据流" },
  { id: "clock", title: "时钟树" },
  { id: "stats", title: "统计" },
] as const;

export function App() {
  const live = useMemo(() => isLiveSource(), []);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [view, setView] = useState<string>("dataflow");
  const [summary, setSummary] = useState<TraceSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutFile>(() => readLayout());
  const [staleCount, setStaleCount] = useState(0);
  const [eventStatus, setEventStatus] = useState<"off" | "connecting" | "live">("off");

  useEffect(() => {
    const controller = new AbortController();
    const url = resolveGraphUrl();
    setState({ status: "loading" });
    setSelected(null);
    loadGraph(url, controller.signal)
      .then((graph) => {
        setState({ status: "ready", graph, url });
        setLayout((previous) => {
          const next = mergeLayoutFile(graph, previous);
          writeLayout(next);
          return next;
        });
      })
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

  useEffect(() => {
    const controller = new AbortController();
    setSummary(null);
    setSummaryError(null);
    loadSummary(resolveSummaryUrl(), controller.signal)
      .then((loaded) => setSummary(loaded))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setSummaryError(error instanceof Error ? error.message : String(error));
      });
    return () => controller.abort();
  }, [reloadToken]);

  // SSE 只提示“源变了”；绝不自动覆写视图（方案 §7.2）。
  useEffect(() => {
    if (!live) return;
    setEventStatus("connecting");
    const disconnect = connectEvents(eventsUrl(), {
      onStale: () => setStaleCount((count) => count + 1),
      onResync: () => setStaleCount((count) => count + 1),
      onStatus: (status) => setEventStatus(status === "open" ? "live" : "connecting"),
    });
    return () => {
      disconnect();
      setEventStatus("off");
    };
  }, [live]);

  const handleReload = useCallback(() => {
    setStaleCount(0);
    setReloadToken((token) => token + 1);
  }, []);

  const handleNodeDragStop = useCallback(
    (id: string, position: { x: number; y: number }) => {
      setLayout((previous) => {
        const next = recordPosition(previous, id, position);
        writeLayout(next);
        return next;
      });
      if (!live) return;
      void fetch("/api/layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodes: { [id]: { x: position.x, y: position.y } } }),
      }).catch(() => undefined);
    },
    [live],
  );

  const graph = state.status === "ready" ? state.graph : null;
  const pluginViews = useMemo(() => (graph ? availablePluginViews(graph) : []), [graph]);

  useEffect(() => {
    if (!graph) return;
    const known = new Set<string>([...CORE_VIEWS.map((item) => item.id), ...pluginViews.map((item) => item.id)]);
    if (!known.has(view)) setView("dataflow");
  }, [graph, pluginViews, view]);

  const handleSelect = useCallback((node: GraphNode) => setSelected(node), []);
  const handleClose = useCallback(() => setSelected(null), []);

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__brand">
          <span className="app__logo">SuperLogicCircuit</span>
          <span className="app__subtitle">静态结构看板</span>
        </div>
        {graph ? (
          <nav className="app__tabs" aria-label="视图切换">
            {CORE_VIEWS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={view === item.id ? "app__tab app__tab--active" : "app__tab"}
                onClick={() => setView(item.id)}
                data-testid={`tab-${item.id}`}
              >
                {item.title}
              </button>
            ))}
            {pluginViews.map((item) => (
              <button
                key={item.id}
                type="button"
                className={view === item.id ? "app__tab app__tab--active" : "app__tab"}
                onClick={() => setView(item.id)}
                data-testid={`tab-${item.id}`}
                title={`plugin: ${item.plugin}`}
              >
                {item.title}
              </button>
            ))}
          </nav>
        ) : null}
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
        {live ? (
          <span
            className={eventStatus === "live" ? "app__live app__live--on" : "app__live"}
            data-testid="event-status"
            title="slc serve 事件流"
          >
            {eventStatus === "live" ? "实时" : "连接中"}
          </span>
        ) : null}
        {staleCount > 0 ? (
          <button
            type="button"
            className="app__reload-stale"
            onClick={handleReload}
            data-testid="reload-banner"
          >
            源已变更（{staleCount}）· 重新加载
          </button>
        ) : null}
        <button type="button" onClick={handleReload} data-testid="reload-button">
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
            <button type="button" onClick={handleReload}>
              重试
            </button>
          </div>
        ) : null}
        {graph ? (
          <>
            {view === "dataflow" ? (
              <DataflowView
                graph={graph}
                layout={layout}
                summary={summary}
                onSelectNode={handleSelect}
                onNodeDragStop={handleNodeDragStop}
              />
            ) : null}
            {view === "clock" ? <ClockTreeView graph={graph} onSelectNode={handleSelect} /> : null}
            {view === "stats" ? <StatsView graph={graph} summary={summary} summaryError={summaryError} /> : null}
            {pluginViews.map((item) =>
              view === item.id ? <item.Component key={item.id} graph={graph} /> : null,
            )}
            <DetailDrawer node={selected} onClose={handleClose} />
          </>
        ) : null}
      </main>
    </div>
  );
}
