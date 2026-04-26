import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  ArrowDownToLine,
  Banknote,
  Building2,
  CheckCircle2,
  Clock3,
  Landmark,
  RefreshCcw,
  Search,
  Send,
  ShieldCheck,
  TimerReset,
  WalletCards,
  XCircle,
} from "lucide-react";
import "./main.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";
const STATUS_ORDER = ["all", "pending", "processing", "completed", "failed"];

function formatMoney(paise) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format((paise || 0) / 100);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function timeAgo(value) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function statusClass(status) {
  return {
    pending: "bg-gold/15 text-gold",
    processing: "bg-sky-100 text-sky-700",
    completed: "bg-emerald-100 text-emerald-700",
    failed: "bg-coral/15 text-coral",
  }[status] || "bg-slate-100 text-slate-700";
}

function statusIcon(status) {
  return {
    pending: <Clock3 size={14} />,
    processing: <TimerReset size={14} />,
    completed: <CheckCircle2 size={14} />,
    failed: <XCircle size={14} />,
  }[status];
}

function buildClientSummary(dashboard) {
  const status = {
    pending: { count: 0, amount_paise: 0 },
    processing: { count: 0, amount_paise: 0 },
    completed: { count: 0, amount_paise: 0 },
    failed: { count: 0, amount_paise: 0 },
  };
  let largestPayout = 0;
  dashboard.payouts.forEach((payout) => {
    status[payout.status].count += 1;
    status[payout.status].amount_paise += payout.amount_paise;
    largestPayout = Math.max(largestPayout, payout.amount_paise);
  });
  const finalCount = status.completed.count + status.failed.count;
  return {
    status,
    total_payouts: dashboard.payouts.length,
    total_completed_paise: status.completed.amount_paise,
    total_failed_paise: status.failed.amount_paise,
    success_rate_percent: finalCount ? Math.round((status.completed.count * 100) / finalCount) : null,
    largest_payout_paise: largestPayout,
    bank_account_count: dashboard.merchant.bank_accounts.length,
  };
}

function App() {
  const [merchants, setMerchants] = useState([]);
  const [merchantId, setMerchantId] = useState("1");
  const [dashboard, setDashboard] = useState(null);
  const [amount, setAmount] = useState("");
  const [bankAccountId, setBankAccountId] = useState("");
  const [message, setMessage] = useState({ type: "idle", text: "" });
  const [statusFilter, setStatusFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  const [loadError, setLoadError] = useState("");

  const headers = useMemo(() => ({ "X-Merchant-ID": merchantId }), [merchantId]);
  const availablePaise = dashboard?.balance?.available_paise || 0;
  const amountPaise = Math.round(Number(amount || 0) * 100);
  const amountInvalid = amount && (amountPaise <= 0 || amountPaise > availablePaise);

  async function loadMerchants() {
    const res = await fetch(`${API_BASE}/merchants`);
    if (!res.ok) throw new Error("Could not load merchants.");
    const data = await res.json();
    setMerchants(data);
    if (data.length && !merchantId) setMerchantId(String(data[0].id));
  }

  async function loadDashboard(silent = false) {
    if (!silent) setIsRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/dashboard`, { headers });
      if (!res.ok) throw new Error("Could not load dashboard.");
      const data = await res.json();
      setDashboard(data);
      setLastSyncedAt(new Date());
      setLoadError("");
      if (!bankAccountId && data.merchant.bank_accounts[0]) {
        setBankAccountId(String(data.merchant.bank_accounts[0].id));
      }
    } catch (error) {
      setLoadError(error.message);
    } finally {
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadMerchants().catch((error) => setLoadError(error.message));
  }, []);

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(() => loadDashboard(true), 3000);
    return () => clearInterval(timer);
  }, [merchantId]);

  const filteredPayouts = useMemo(() => {
    if (!dashboard) return [];
    const normalizedQuery = query.trim().toLowerCase();
    return dashboard.payouts.filter((payout) => {
      const statusMatch = statusFilter === "all" || payout.status === statusFilter;
      const activeMatch = !showActiveOnly || ["pending", "processing"].includes(payout.status);
      const searchable = [
        `#${payout.id}`,
        payout.status,
        payout.bank_account.bank_name,
        payout.bank_account.account_last4,
        String(payout.amount_paise / 100),
      ]
        .join(" ")
        .toLowerCase();
      return statusMatch && activeMatch && (!normalizedQuery || searchable.includes(normalizedQuery));
    });
  }, [dashboard, query, showActiveOnly, statusFilter]);

  async function submitPayout(event) {
    event.preventDefault();
    if (amountInvalid || !amountPaise) {
      setMessage({ type: "error", text: "Enter an amount within the available balance." });
      return;
    }

    setIsSubmitting(true);
    setMessage({ type: "idle", text: "" });
    try {
      const res = await fetch(`${API_BASE}/payouts`, {
        method: "POST",
        headers: {
          ...headers,
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ amount_paise: amountPaise, bank_account_id: Number(bankAccountId) }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage({ type: "error", text: data.detail || "Payout could not be created." });
        return;
      }
      setAmount("");
      setMessage({ type: "success", text: `Payout #${data.id} queued and funds held.` });
      loadDashboard(true);
    } finally {
      setIsSubmitting(false);
    }
  }

  function selectMerchant(nextMerchantId) {
    setMerchantId(nextMerchantId);
    setBankAccountId("");
    setStatusFilter("all");
    setQuery("");
    setMessage({ type: "idle", text: "" });
  }

  if (!dashboard) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f7f9f6] px-5">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-md bg-mist text-leaf">
            <RefreshCcw className="animate-spin" size={20} />
          </div>
          <p className="text-lg font-semibold">Loading Playto Pay</p>
          {loadError && <p className="mt-2 text-sm text-coral">{loadError}</p>}
        </div>
      </main>
    );
  }

  const summary = dashboard.summary || buildClientSummary(dashboard);
  const statusSummary = summary.status || {};
  const worker = dashboard.worker || {
    work_ready_count: (statusSummary.pending?.count || 0) + (statusSummary.processing?.count || 0),
    retry_after_seconds: 30,
  };
  const workerReady = worker.work_ready_count || 0;
  const ledgerOk = dashboard.integrity
    ? dashboard.integrity.ledger_matches_balance
    : dashboard.ledger_available_paise === availablePaise;

  return (
    <main className="min-h-screen bg-[#f7f9f6]">
      <section className="border-b border-ink/10 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">Playto Pay</h1>
            <p className="text-sm text-ink/60">{dashboard.merchant.name} operations console</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <select
              className="h-11 min-w-[230px] rounded-md border border-ink/15 bg-white px-3"
              value={merchantId}
              onChange={(event) => selectMerchant(event.target.value)}
            >
              {merchants.map((merchant) => (
                <option key={merchant.id} value={merchant.id}>
                  {merchant.name}
                </option>
              ))}
            </select>
            <button
              className="flex h-11 items-center justify-center gap-2 rounded-md border border-ink/15 bg-white px-4 text-sm font-medium hover:bg-mist"
              onClick={() => loadDashboard()}
              type="button"
            >
              <RefreshCcw className={isRefreshing ? "animate-spin" : ""} size={16} />
              Refresh
            </button>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-6 px-5 py-6">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <StatusStrip
            icon={ledgerOk ? <ShieldCheck size={17} /> : <AlertTriangle size={17} />}
            tone={ledgerOk ? "good" : "bad"}
            title={ledgerOk ? "Ledger reconciled" : "Ledger mismatch"}
            detail={`Last sync ${lastSyncedAt ? timeAgo(lastSyncedAt) : "pending"}`}
          />
          <StatusStrip
            icon={<TimerReset size={17} />}
            tone={workerReady ? "warn" : "good"}
            title={workerReady ? `${workerReady} payout${workerReady === 1 ? "" : "s"} ready` : "Worker caught up"}
            detail={`${worker.retry_after_seconds || 30}s retry window`}
          />
        </div>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,390px)]">
          <div className="order-2 min-w-0 space-y-6 lg:order-1">
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              <Metric label="Available" value={formatMoney(availablePaise)} icon={<ArrowDownToLine />} />
              <Metric label="Held" value={formatMoney(dashboard.balance.held_paise)} icon={<Landmark />} />
              <Metric label="Completed" value={formatMoney(summary.total_completed_paise)} icon={<CheckCircle2 />} />
              <Metric
                label="Success rate"
                value={summary.success_rate_percent === null ? "No finals" : `${summary.success_rate_percent || 0}%`}
                icon={<ShieldCheck />}
              />
              <Metric label="Bank accounts" value={summary.bank_account_count || 0} icon={<WalletCards />} />
            </section>

            <Panel title="Payout History">
              <div className="mb-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <div className="flex flex-wrap gap-2">
                  {STATUS_ORDER.map((status) => (
                    <button
                      className={`h-9 rounded-md border px-3 text-sm font-medium ${
                        statusFilter === status
                          ? "border-leaf bg-leaf text-white"
                          : "border-ink/10 bg-white text-ink/70 hover:bg-mist"
                      }`}
                      key={status}
                      onClick={() => setStatusFilter(status)}
                      type="button"
                    >
                      {status === "all" ? "All" : status}
                      <span className="ml-2 text-xs opacity-80">
                        {status === "all" ? summary.total_payouts || 0 : statusSummary[status]?.count || 0}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <label className="relative block">
                    <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={16} />
                    <input
                      className="h-9 w-full rounded-md border border-ink/15 bg-white pl-9 pr-3 text-sm sm:w-64"
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Search payouts"
                      value={query}
                    />
                  </label>
                  <label className="flex h-9 items-center gap-2 rounded-md border border-ink/15 bg-white px-3 text-sm">
                    <input
                      checked={showActiveOnly}
                      onChange={(event) => setShowActiveOnly(event.target.checked)}
                      type="checkbox"
                    />
                    Active only
                  </label>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] text-left text-sm">
                  <thead className="border-b border-ink/10 text-ink/55">
                    <tr>
                      <th className="py-3 font-medium">ID</th>
                      <th className="py-3 font-medium">Amount</th>
                      <th className="py-3 font-medium">Bank</th>
                      <th className="py-3 font-medium">Status</th>
                      <th className="py-3 font-medium">Attempts</th>
                      <th className="py-3 font-medium">Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPayouts.map((payout) => (
                      <tr key={payout.id} className="border-b border-ink/5 align-top">
                        <td className="py-3 font-medium">#{payout.id}</td>
                        <td className="py-3">{formatMoney(payout.amount_paise)}</td>
                        <td className="py-3">
                          <p>{payout.bank_account.bank_name} ****{payout.bank_account.account_last4}</p>
                          <p className="text-xs text-ink/45">{payout.bank_account.ifsc}</p>
                        </td>
                        <td className="py-3">
                          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${statusClass(payout.status)}`}>
                            {statusIcon(payout.status)}
                            {payout.status}
                          </span>
                          {payout.failure_reason && <p className="mt-1 max-w-[220px] text-xs text-coral">{payout.failure_reason}</p>}
                        </td>
                        <td className="py-3">{payout.attempts}</td>
                        <td className="py-3">
                          <p>{formatDate(payout.created_at)}</p>
                          <p className="text-xs text-ink/45">{timeAgo(payout.created_at)}</p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!filteredPayouts.length && (
                  <div className="grid min-h-40 place-items-center text-sm text-ink/55">
                    No payouts match the current filters.
                  </div>
                )}
              </div>
            </Panel>

            <Panel title="Merchant Snapshot">
              <div className="space-y-4 text-sm">
                <SnapshotRow icon={<Building2 size={16} />} label="Merchant" value={dashboard.merchant.name} />
                <SnapshotRow icon={<Banknote size={16} />} label="Largest payout" value={formatMoney(summary.largest_payout_paise)} />
                <SnapshotRow icon={<Clock3 size={16} />} label="Pending amount" value={formatMoney(statusSummary.pending?.amount_paise || 0)} />
                <SnapshotRow icon={<Landmark size={16} />} label="Processing amount" value={formatMoney(statusSummary.processing?.amount_paise || 0)} />
              </div>
            </Panel>

            <Panel title="Recent Ledger">
              <div className="grid gap-3 md:grid-cols-2">
                {dashboard.recent_ledger.slice(0, 10).map((entry) => (
                  <div key={entry.id} className="flex items-start justify-between gap-4 rounded-md border border-ink/10 bg-white px-4 py-3 text-sm">
                    <div>
                      <p className="font-medium capitalize">{entry.kind.replaceAll("_", " ")}</p>
                      <p className="mt-1 text-ink/55">{entry.description}</p>
                    </div>
                    <span className={`shrink-0 font-semibold ${entry.amount_paise < 0 ? "text-coral" : "text-leaf"}`}>
                      {formatMoney(entry.amount_paise)}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          <aside className="order-1 space-y-6 self-start lg:sticky lg:top-4 lg:order-2">
            <Panel title="Request Payout">
              <form className="space-y-4" onSubmit={submitPayout}>
                <div className="rounded-md bg-mist px-4 py-3">
                  <p className="text-sm text-ink/55">Available to withdraw</p>
                  <p className="mt-1 text-2xl font-semibold">{formatMoney(availablePaise)}</p>
                </div>

                <div>
                  <label className="block text-sm font-medium" htmlFor="amount">
                    Amount in INR
                  </label>
                  <input
                    className={`mt-2 h-11 w-full rounded-md border px-3 ${amountInvalid ? "border-coral" : "border-ink/15"}`}
                    id="amount"
                    min="1"
                    onChange={(event) => setAmount(event.target.value)}
                    step="0.01"
                    type="number"
                    value={amount}
                    required
                  />
                  {amountInvalid && <p className="mt-2 text-xs text-coral">Amount must be above zero and within available balance.</p>}
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {[1000, 5000, 10000, 50000].map((preset) => (
                    <button
                      className="h-9 rounded-md border border-ink/10 bg-white text-sm font-medium hover:bg-mist disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={preset * 100 > availablePaise}
                      key={preset}
                      onClick={() => setAmount(String(preset))}
                      type="button"
                    >
                      {formatMoney(preset * 100)}
                    </button>
                  ))}
                </div>

                <button
                  className="h-9 w-full rounded-md border border-ink/10 bg-white text-sm font-medium hover:bg-mist"
                  onClick={() => setAmount(String(Math.floor(availablePaise / 100)))}
                  type="button"
                >
                  Use full available balance
                </button>

                <label className="block text-sm font-medium">
                  Bank account
                  <select
                    className="mt-2 h-11 w-full rounded-md border border-ink/15 bg-white px-3"
                    onChange={(event) => setBankAccountId(event.target.value)}
                    value={bankAccountId}
                    required
                  >
                    {dashboard.merchant.bank_accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.bank_name} ****{account.account_last4}
                      </option>
                    ))}
                  </select>
                </label>

                <button
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-leaf px-4 font-medium text-white hover:bg-leaf/90 disabled:cursor-not-allowed disabled:bg-ink/25"
                  disabled={isSubmitting || amountInvalid || !amountPaise}
                >
                  <Send size={17} />
                  {isSubmitting ? "Creating payout" : "Request payout"}
                </button>

                {message.text && (
                  <p className={`rounded-md px-3 py-2 text-sm ${message.type === "error" ? "bg-coral/10 text-coral" : "bg-emerald-100 text-emerald-700"}`}>
                    {message.text}
                  </p>
                )}
              </form>
            </Panel>
          </aside>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value, icon }) {
  return (
    <div className="rounded-md border border-ink/10 bg-white p-4">
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-mist text-leaf">{icon}</div>
      <p className="text-sm text-ink/55">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <div className="rounded-md border border-ink/10 bg-white p-5">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {children}
    </div>
  );
}

function StatusStrip({ detail, icon, title, tone }) {
  const toneClass = {
    good: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warn: "border-gold/30 bg-gold/10 text-gold",
    bad: "border-coral/30 bg-coral/10 text-coral",
  }[tone];
  return (
    <div className={`flex items-center gap-3 rounded-md border px-4 py-3 ${toneClass}`}>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white/70">{icon}</div>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs opacity-75">{detail}</p>
      </div>
    </div>
  );
}

function SnapshotRow({ icon, label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-ink/5 pb-3 last:border-0 last:pb-0">
      <div className="flex items-center gap-2 text-ink/55">
        {icon}
        <span>{label}</span>
      </div>
      <span className="text-right font-semibold">{value}</span>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
