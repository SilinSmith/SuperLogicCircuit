import type { PluginViewProps } from "../registry";

/** plugins/cpu 注册的 Cache 视图：P4 先呈现静态配置，状态机动画留给后续。 */
export function CacheView({ graph }: PluginViewProps) {
  const caches = graph.nodes.filter(
    (node) => node.type === "p_cpu:cache_node" || node["x-cpu-cache"] !== undefined,
  );
  if (caches.length === 0) {
    return <div className="plugin-empty">该图没有 p_cpu:cache_node 节点。</div>;
  }
  return (
    <div className="cache-view" data-testid="cache-view">
      <table>
        <thead>
          <tr>
            <th>id</th>
            <th>标签</th>
            <th>模块</th>
            <th>路数</th>
            <th>组数</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {caches.map((node) => (
            <tr key={node.id}>
              <td>{node.id}</td>
              <td>{node.label}</td>
              <td>{node.module ?? "-"}</td>
              <td>{String(node["x-cpu-ways"] ?? "-")}</td>
              <td>{String(node["x-cpu-sets"] ?? "-")}</td>
              <td>{node.status ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
