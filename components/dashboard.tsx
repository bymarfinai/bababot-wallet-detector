"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  DashboardPayload,
  DashboardSymbol,
  WindowKey,
} from "../lib/dashboard-types";

const windowKeys: WindowKey[] = ["5m", "15m", "1h"];

function shortAddress(value: string) {
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}…${value.slice(-5)}`;
}

function compactNumber(value: string | number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat("en-US", {
    notation: Math.abs(numeric) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 2,
  }).format(numeric);
}

function usd(value: string | number) {
  const numeric = Number(value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(numeric) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(Number.isFinite(numeric) ? numeric : 0);
}

function timeAgo(timestamp: number | null) {
  if (!timestamp) return "—";
  const diff = Math.max(0, Math.floor(Date.now() / 1000) - timestamp);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function ModePill({ mode }: { mode: DashboardPayload["mode"] }) {
  return <span className={`mode-pill mode-${mode.toLowerCase()}`}>{mode}</span>;
}

function FlowPill({ state }: { state: DashboardSymbol["flowState"] }) {
  return (
    <span className={`flow-pill flow-${state.toLowerCase()}`}>
      <span className="flow-dot" />
      {state}
    </span>
  );
}

function StatCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

export default function Dashboard({
  initialData,
}: {
  initialData: DashboardPayload;
}) {
  const [data, setData] = useState(initialData);
  const [windowKey, setWindowKey] = useState<WindowKey>("5m");
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    setRefreshing(true);
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      if (response.ok) {
        const next: DashboardPayload = await response.json();
        setData(next);
      }
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const timer = window.setInterval(refresh, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  const activeWindow = data.windows[windowKey];
  const visibleSymbols = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return activeWindow.symbols;
    return activeWindow.symbols.filter(
      (row) =>
        row.symbol.toLowerCase().includes(normalized) ||
        row.baseAsset.toLowerCase().includes(normalized),
    );
  }, [activeWindow.symbols, query]);

  const accumulated = activeWindow.symbols.filter(
    (row) => row.flowState === "ACCUMULATION",
  ).length;
  const distributed = activeWindow.symbols.filter(
    (row) => row.flowState === "DISTRIBUTION",
  ).length;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow-row">
            <span className="brand-mark">WD</span>
            <span className="eyebrow">BABABOT / SMART MONEY INTELLIGENCE</span>
          </div>
          <h1>Wallet Detector</h1>
          <p className="subtitle">
            Qualified-wallet activity, rolling smart-money flow, and registry health.
          </p>
        </div>
        <div className="topbar-actions">
          <ModePill mode={data.mode} />
          <button className="refresh-button" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <section className={`runtime-banner runtime-${data.mode.toLowerCase()}`}>
        <div>
          <strong>{data.mode === "LIVE" ? "Runtime connected" : "Runtime activation pending"}</strong>
          <p>{data.sourceMessage}</p>
        </div>
        <div className="runtime-meta">
          <span>Snapshot</span>
          <code>{data.registry.snapshotId}</code>
        </div>
      </section>

      <section className="stat-grid">
        <StatCard
          label="Qualified wallets"
          value={compactNumber(data.registry.activeWalletCount)}
          detail={`${data.registry.segmentCounts.S1 ?? 0} S1 · ${data.registry.segmentCounts.S2 ?? 0} S2 · ${data.registry.segmentCounts.S3 ?? 0} S3`}
        />
        <StatCard
          label={`${windowKey} trade events`}
          value={compactNumber(activeWindow.tradeEventCount)}
          detail={`${activeWindow.symbolCount} active token mints`}
        />
        <StatCard
          label="Accumulation"
          value={String(accumulated)}
          detail={`${distributed} distribution · ${activeWindow.symbolCount - accumulated - distributed} balanced`}
        />
        <StatCard
          label="Monitor health"
          value={
            data.monitor.normalizationErrorCount === 0
              ? "Healthy"
              : `${data.monitor.normalizationErrorCount} errors`
          }
          detail={`${data.monitor.duplicateWalletEventCount} duplicate deliveries safely ignored`}
        />
      </section>

      <section className="workspace">
        <div className="panel flow-panel">
          <div className="panel-header">
            <div>
              <span className="section-kicker">SMART MONEY FLOW</span>
              <h2>Token activity</h2>
            </div>
            <div className="window-tabs" aria-label="Aggregation window">
              {windowKeys.map((key) => (
                <button
                  key={key}
                  className={key === windowKey ? "active" : ""}
                  onClick={() => setWindowKey(key)}
                >
                  {key}
                </button>
              ))}
            </div>
          </div>

          <div className="search-row">
            <input
              aria-label="Search token"
              placeholder="Search symbol or mint…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <span>{visibleSymbols.length} shown</span>
          </div>

          <div className="symbol-table">
            <div className="symbol-head">
              <span>Token</span>
              <span>Flow</span>
              <span>Wallets</span>
              <span>BUY / SELL</span>
              <span>Net USD</span>
            </div>
            {visibleSymbols.map((row) => {
              const buys = row.buyEventCount;
              const sells = row.sellEventCount;
              const total = Math.max(1, buys + sells);
              const buyShare = Math.round((buys / total) * 100);

              return (
                <article className="symbol-row" key={row.baseAsset}>
                  <div className="token-cell">
                    <strong>{row.symbol}</strong>
                    <code title={row.baseAsset}>{shortAddress(row.baseAsset)}</code>
                  </div>
                  <div>
                    <FlowPill state={row.flowState} />
                  </div>
                  <div className="wallet-count">
                    <strong>{row.uniqueWalletCount}</strong>
                    <span>{row.buyWalletCount}B · {row.sellWalletCount}S</span>
                  </div>
                  <div className="activity-cell">
                    <div className="activity-values">
                      <span>{buys} BUY</span>
                      <span>{sells} SELL</span>
                    </div>
                    <div className="flow-track">
                      <span style={{ width: `${buyShare}%` }} />
                    </div>
                  </div>
                  <div className={Number(row.usdNetNotional) >= 0 ? "positive" : "negative"}>
                    <strong>{usd(row.usdNetNotional)}</strong>
                    <span>{row.unpricedEventCount} unpriced</span>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <aside className="panel registry-panel">
          <div className="panel-header">
            <div>
              <span className="section-kicker">REGISTRY</span>
              <h2>Qualification mix</h2>
            </div>
          </div>

          <div className="registry-total">
            <strong>{data.registry.activeWalletCount}</strong>
            <span>ACTIVE wallets</span>
          </div>

          <div className="segment-stack">
            {(["S1", "S2", "S3"] as const).map((segment) => {
              const count = data.registry.segmentCounts[segment] ?? 0;
              const percentage = Math.min(
                100,
                Math.round((count / Math.max(1, data.registry.activeWalletCount)) * 100),
              );
              return (
                <div className="segment-row" key={segment}>
                  <div>
                    <strong>{segment}</strong>
                    <span>{count} wallets</span>
                  </div>
                  <div className="segment-track">
                    <span style={{ width: `${percentage}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="health-list">
            <div>
              <span>Stored trade events</span>
              <strong>{compactNumber(data.monitor.storedTradeEventCount)}</strong>
            </div>
            <div>
              <span>Duplicates rejected</span>
              <strong>{compactNumber(data.monitor.duplicateWalletEventCount)}</strong>
            </div>
            <div>
              <span>Normalization errors</span>
              <strong>{data.monitor.normalizationErrorCount}</strong>
            </div>
            <div>
              <span>Latest chain activity</span>
              <strong>{timeAgo(data.monitor.latestBlockTime)}</strong>
            </div>
          </div>
        </aside>
      </section>

      <section className="panel recent-panel">
        <div className="panel-header">
          <div>
            <span className="section-kicker">LIVE TAPE</span>
            <h2>Recent qualified-wallet activity</h2>
          </div>
          <span className="generated-at">
            Updated {new Date(data.generatedAt).toLocaleTimeString()}
          </span>
        </div>

        <div className="recent-list">
          {data.recentEvents.map((event) => (
            <article className="recent-row" key={event.id}>
              <div className={`side-badge side-${event.side.toLowerCase()}`}>{event.side}</div>
              <div className="recent-wallet">
                <strong>{shortAddress(event.wallet)}</strong>
                <span>{event.primarySegment ?? "—"} · {event.qualifyingSegments.join("/")}</span>
              </div>
              <div className="recent-token">
                <strong>{event.symbol}</strong>
                <code>{shortAddress(event.baseAsset)}</code>
              </div>
              <div className="recent-notional">
                <strong>{event.usdNotional ? usd(event.usdNotional) : "Unpriced"}</strong>
                <span>{timeAgo(event.blockTime)}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <footer>
        <span>Wallet Detector Stage 8.5</span>
        <span>WHO + WHAT smart wallets are buying / selling</span>
      </footer>
    </main>
  );
}
