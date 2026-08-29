"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

/* ------------------------------------------------------------------ */
/*  Types — mirrors backend schemas                                    */
/* ------------------------------------------------------------------ */

interface OpportunityEvidence {
  source: string;
  issue_type: string;
  product_id: string;
  product_name: string;
  severity: "low" | "medium" | "high";
  description: string;
  suggested_action: string;
}

interface FinancialImpact {
  type: string;
  direction: string;
  estimate: string;
  assumptions: string[];
}

interface AuditInfo {
  timestamp: string;
  signal_source: string;
  products_analyzed: number;
  issues_evaluated: number;
  generation_method: string;
  rule_version: string;
  affected_product_ids: string[];
  category: string;
  highest_severity: "low" | "medium" | "high";
}

interface GrowthOpportunity {
  opportunity_id: string;
  merchant_id: string;
  title: string;
  problem: string;
  evidence: OpportunityEvidence[];
  financial_impact: FinancialImpact;
  proposed_action: string;
  guardrails: string[];
  approval_required: boolean;
  status: string;
  reasoning: string;
  audit: AuditInfo;
}

interface GrowthOpportunitiesResponse {
  merchant_id: string;
  opportunities: GrowthOpportunity[];
}

interface ApprovalResponse {
  opportunity_id: string;
  merchant_id: string;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  proposed_action: string;
  guardrails: string[];
}

interface SimulatedDiscountResult {
  discount_amount: string;
  final_price: string;
}

interface SimulatedExecutionResponse {
  execution_id: string;
  opportunity_id: string;
  merchant_id: string;
  action_type: string;
  original_value: string;
  requested_value: string;
  bounded_value: string;
  simulated_result: SimulatedDiscountResult;
  guardrails_checked: number;
  status: string;
  approval_required: boolean;
  timestamp: string;
  disclaimer: string;
}

interface AuditEvent {
  event_id: string;
  event_type: string;
  merchant_id: string;
  opportunity_id: string;
  timestamp: string;
  actor: "system" | "merchant" | "agent";
  status: string;
  reason: string;
  metadata: Record<string, unknown>;
}

interface AuditTrailResponse {
  merchant_id: string;
  opportunity_id: string;
  events: AuditEvent[];
  total_events: number;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SEVERITY_STYLES: Record<
  string,
  { label: string; className: string }
> = {
  high: { label: "High", className: "bg-red-50 text-red-700" },
  medium: { label: "Medium", className: "bg-amber-50 text-amber-700" },
  low: { label: "Low", className: "bg-slate-100 text-slate-600" },
};

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  proposed: {
    label: "Proposed",
    className: "bg-indigo-50 text-indigo-700 border border-indigo-200",
  },
  approved: {
    label: "Approved",
    className: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  },
  executed: {
    label: "Executed",
    className: "bg-purple-50 text-purple-700 border border-purple-200",
  },
  denied: {
    label: "Denied",
    className: "bg-red-50 text-red-700 border border-red-200",
  },
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  opportunity_created: "Opportunity Created",
  approval_requested: "Approval Requested",
  approval_granted: "Approval Granted",
  approval_denied: "Approval Denied",
  execution_requested: "Execution Requested",
  execution_allowed: "Execution Allowed",
  execution_denied: "Execution Denied",
  simulated_action_completed: "Simulated Execution Completed",
  llm_failure: "LLM Failure",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  opportunity_created: "bg-blue-50 text-blue-700",
  approval_requested: "bg-amber-50 text-amber-700",
  approval_granted: "bg-emerald-50 text-emerald-700",
  approval_denied: "bg-red-50 text-red-700",
  execution_requested: "bg-purple-50 text-purple-700",
  execution_allowed: "bg-emerald-50 text-emerald-700",
  execution_denied: "bg-red-50 text-red-700",
  simulated_action_completed: "bg-violet-50 text-violet-700",
  llm_failure: "bg-red-100 text-red-800",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function MerchantGrowthPage() {
  /* ---------- merchant session ---------- */
  const [merchantName, setMerchantName] = useState("");
  const [missingMerchant, setMissingMerchant] = useState(false);

  /* ---------- opportunities ---------- */
  const [opportunities, setOpportunities] = useState<GrowthOpportunity[]>([]);
  const [loadingOpps, setLoadingOpps] = useState(true);
  const [oppsError, setOppsError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  /* ---------- approval per-opportunity ---------- */
  const [approvalLoading, setApprovalLoading] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  /* ---------- execution per-opportunity ---------- */
  const [execLoading, setExecLoading] = useState<string | null>(null);
  const [execError, setExecError] = useState<string | null>(null);
  const [execResults, setExecResults] = useState<
    Record<string, SimulatedExecutionResponse>
  >({});

  /* ---------- audit trail per-opportunity ---------- */
  const [auditTrail, setAuditTrail] = useState<
    Record<string, AuditEvent[]>
  >({});
  const [auditLoading, setAuditLoading] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [showAuditId, setShowAuditId] = useState<string | null>(null);

  /* ---------- generation ---------- */
  const [generating, setGenerating] = useState(false);

  /* ================================================================ */
  /*  Init: read merchant from session and fetch opportunities        */
  /* ================================================================ */

  useEffect(() => {
    const merchantId = sessionStorage.getItem("merchant_id");
    const name = sessionStorage.getItem("merchant_name") ?? "";

    if (!merchantId) {
      setMissingMerchant(true);
      setLoadingOpps(false);
      return;
    }

    setMerchantName(name);

    async function fetchOpportunities() {
      try {
        setLoadingOpps(true);
        setOppsError("");

        const response = await fetch(
          `${API_BASE_URL}/api/v1/merchants/${merchantId}/growth-opportunities`,
          { method: "POST" }
        );

        if (!response.ok) {
          throw new Error(
            `Unable to load growth opportunities (HTTP ${response.status}).`
          );
        }

        const data = (await response.json()) as GrowthOpportunitiesResponse;
        setOpportunities(data.opportunities);
      } catch (err) {
        setOppsError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading growth opportunities."
        );
      } finally {
        setLoadingOpps(false);
      }
    }

    fetchOpportunities();
  }, []);

  const handleRegenerate = async () => {
    const merchantId = sessionStorage.getItem("merchant_id");
    if (!merchantId) return;
    setGenerating(true);
    try {
      setLoadingOpps(true);
      setOppsError("");
      const response = await fetch(
        `${API_BASE_URL}/api/v1/merchants/${merchantId}/growth-opportunities`,
        { method: "POST" }
      );
      if (!response.ok) {
        throw new Error(
          `Unable to load growth opportunities (HTTP ${response.status}).`
        );
      }
      const data = (await response.json()) as GrowthOpportunitiesResponse;
      setOpportunities(data.opportunities);
    } catch (err) {
      setOppsError(
        err instanceof Error
          ? err.message
          : "Something went wrong while loading growth opportunities."
      );
    } finally {
      setLoadingOpps(false);
      setGenerating(false);
    }
  };

  /* ================================================================ */
  /*  Approval                                                         */
  /* ================================================================ */

  const handleApproval = async (
    opportunityId: string,
    approved: boolean
  ) => {
    const merchantId = sessionStorage.getItem("merchant_id");
    if (!merchantId) return;
    setApprovalLoading(opportunityId);
    setApprovalError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/merchants/${merchantId}/growth-opportunities/${opportunityId}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            approved,
            approved_by: merchantName || "merchant",
          }),
        }
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.detail ?? `Approval failed (HTTP ${response.status}).`
        );
      }

      const result = (await response.json()) as ApprovalResponse;

      setOpportunities((prev) =>
        prev.map((opp) =>
          opp.opportunity_id === opportunityId
            ? { ...opp, status: result.status }
            : opp
        )
      );
    } catch (err) {
      setApprovalError(
        err instanceof Error ? err.message : "Approval request failed."
      );
    } finally {
      setApprovalLoading(null);
    }
  };

  /* ================================================================ */
  /*  Simulated execution                                              */
  /* ================================================================ */

  const handleExecute = async (opportunityId: string) => {
    const merchantId = sessionStorage.getItem("merchant_id");
    if (!merchantId) return;
    setExecLoading(opportunityId);
    setExecError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/merchants/${merchantId}/growth-opportunities/${opportunityId}/execute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ discount_percent: 5 }),
        }
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.detail ?? `Execution failed (HTTP ${response.status}).`
        );
      }

      const result = (await response.json()) as SimulatedExecutionResponse;
      setExecResults((prev) => ({ ...prev, [opportunityId]: result }));
    } catch (err) {
      setExecError(
        err instanceof Error ? err.message : "Simulated execution failed."
      );
    } finally {
      setExecLoading(null);
    }
  };

  /* ================================================================ */
  /*  Audit trail                                                      */
  /* ================================================================ */

  const fetchAuditTrail = async (opportunityId: string) => {
    const merchantId = sessionStorage.getItem("merchant_id");
    if (!merchantId) return;
    setAuditLoading(opportunityId);
    setAuditError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/merchants/${merchantId}/growth-opportunities/${opportunityId}/audit-trail`
      );

      if (!response.ok) {
        throw new Error(
          `Unable to load audit trail (HTTP ${response.status}).`
        );
      }

      const data = (await response.json()) as AuditTrailResponse;
      setAuditTrail((prev) => ({ ...prev, [opportunityId]: data.events }));
    } catch (err) {
      setAuditError(
        err instanceof Error ? err.message : "Failed to load audit trail."
      );
    } finally {
      setAuditLoading(null);
    }
  };

  const toggleAuditTrail = (opportunityId: string) => {
    if (showAuditId === opportunityId) {
      setShowAuditId(null);
    } else {
      setShowAuditId(opportunityId);
      if (!auditTrail[opportunityId]) {
        fetchAuditTrail(opportunityId);
      }
    }
  };

  /* ================================================================ */
  /*  Render helpers                                                   */
  /* ================================================================ */

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  /* ================================================================ */
  /*  Page                                                             */
  /* ================================================================ */

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="hidden w-64 border-r border-slate-200 bg-white p-6 lg:block">
          <div className="mb-10">
            <p className="text-sm font-semibold uppercase tracking-wider text-indigo-600">
              AI Commerce
            </p>
            <h2 className="mt-2 text-xl font-bold text-slate-900">
              Merchant Console
            </h2>
          </div>

          <nav className="space-y-2">
            <Link
              href="/merchant/dashboard"
              className="block rounded-xl px-4 py-3 text-slate-600 hover:bg-slate-50"
            >
              Dashboard
            </Link>
            <Link
              href="/merchant/products"
              className="block rounded-xl px-4 py-3 text-slate-600 hover:bg-slate-50"
            >
              Products
            </Link>
            <Link
              href="/merchant/growth"
              className="block rounded-xl bg-indigo-50 px-4 py-3 font-medium text-indigo-700"
            >
              Growth Opportunities
            </Link>
          </nav>
        </aside>

        {/* Main content */}
        <section className="flex-1 p-6 lg:p-10">
          <div className="mx-auto max-w-7xl">
            {/* Header */}
            <div className="mb-10">
              <p className="text-sm font-medium text-indigo-600">
                Merchant Growth Console
              </p>
              <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
                {merchantName
                  ? `${merchantName} — Growth Dashboard`
                  : "Growth Dashboard"}
              </h1>
              <p className="mt-2 max-w-2xl text-slate-600">
                AI-identified growth opportunities with evidence, estimated
                impact, proposed actions, and audit trail. Every financial
                action requires your explicit approval.
              </p>
            </div>

            {/* Missing merchant */}
            {missingMerchant && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-8 text-center">
                <p className="font-semibold text-amber-900">
                  No merchant account found
                </p>
                <p className="mt-2 text-sm text-amber-800">
                  Please onboard your business first to view growth
                  opportunities.
                </p>
                <Link
                  href="/merchant"
                  className="mt-4 inline-block rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700"
                >
                  Go to Merchant Onboarding
                </Link>
              </div>
            )}

            {/* Content (only when merchant exists) */}
            {!missingMerchant && (
              <>
                {/* Controls */}
                <div className="mb-6 flex items-center gap-4">
                  <button
                    onClick={handleRegenerate}
                    disabled={generating}
                    className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {generating
                      ? "Generating..."
                      : "Regenerate Opportunities"}
                  </button>
                </div>

                {/* Loading state */}
                {loadingOpps && (
                  <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
                    <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
                    <p className="text-sm font-medium text-slate-500">
                      Analyzing your catalog and generating growth
                      opportunities...
                    </p>
                  </div>
                )}

                {/* Error state */}
                {!loadingOpps && oppsError && (
                  <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
                    <p className="font-semibold text-red-900">
                      Failed to load growth opportunities
                    </p>
                    <p className="mt-2 text-sm text-red-700">{oppsError}</p>
                    <button
                      onClick={handleRegenerate}
                      className="mt-4 rounded-xl bg-red-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700"
                    >
                      Try Again
                    </button>
                  </div>
                )}

                {/* Empty state */}
                {!loadingOpps && !oppsError && opportunities.length === 0 && (
                  <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
                    <p className="font-semibold text-slate-900">
                      No growth opportunities identified
                    </p>
                    <p className="mt-2 text-sm text-slate-600">
                      Your catalog looks well-optimized. Check back after
                      adding new products or updating existing ones.
                    </p>
                  </div>
                )}

                {/* Opportunity cards */}
                {!loadingOpps && !oppsError && opportunities.length > 0 && (
                  <div className="space-y-6">
                    {/* Approval-level error */}
                    {approvalError && (
                      <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-center">
                        <p className="text-sm font-medium text-red-700">
                          {approvalError}
                        </p>
                      </div>
                    )}

                    {/* Execution-level error */}
                    {execError && (
                      <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-center">
                        <p className="text-sm font-medium text-red-700">
                          {execError}
                        </p>
                      </div>
                    )}

                    {opportunities.map((opp) => {
                      const statusStyle =
                        STATUS_STYLES[opp.status] ?? STATUS_STYLES.proposed;
                      const isExpanded = expandedId === opp.opportunity_id;
                      const execution = execResults[opp.opportunity_id];
                      const trail = auditTrail[opp.opportunity_id];
                      const isAuditOpen =
                        showAuditId === opp.opportunity_id;

                      return (
                        <div
                          key={opp.opportunity_id}
                          className="rounded-2xl border border-slate-200 bg-white shadow-sm"
                        >
                          {/* Card header */}
                          <div className="p-6">
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                              <div className="max-w-4xl">
                                {/* Status + severity badges */}
                                <div className="flex flex-wrap items-center gap-3">
                                  <span
                                    className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyle.className}`}
                                  >
                                    {statusStyle.label}
                                  </span>
                                  <span
                                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                                      SEVERITY_STYLES[
                                        opp.audit.highest_severity
                                      ]?.className ?? ""
                                    }`}
                                  >
                                    {opp.audit.highest_severity} severity
                                  </span>
                                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                                    {opp.financial_impact.type}
                                  </span>
                                </div>

                                {/* Title */}
                                <h3 className="mt-3 text-lg font-bold text-slate-900">
                                  {opp.title}
                                </h3>

                                {/* Problem (observed fact) */}
                                <div className="mt-3">
                                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                    Observed Problem
                                  </p>
                                  <p className="mt-1 text-sm leading-6 text-slate-700">
                                    {opp.problem}
                                  </p>
                                </div>

                                {/* Reasoning (derived signal) */}
                                <div className="mt-3">
                                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                    AI Reasoning
                                  </p>
                                  <p className="mt-1 text-sm leading-6 text-slate-600 italic">
                                    {opp.reasoning}
                                  </p>
                                </div>
                              </div>
                            </div>

                            {/* Toggle details */}
                            <button
                              onClick={() =>
                                setExpandedId(
                                  isExpanded ? null : opp.opportunity_id
                                )
                              }
                              className="mt-4 text-sm font-semibold text-indigo-600 hover:text-indigo-800"
                            >
                              {isExpanded
                                ? "Hide Details"
                                : "Show Details & Actions"}
                            </button>
                          </div>

                          {/* Expanded section */}
                          {isExpanded && (
                            <div className="border-t border-slate-100 px-6 pb-6 pt-5">
                              {/* Evidence (observed facts) */}
                              <div className="mb-5">
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                  Evidence
                                </p>
                                <div className="mt-2 space-y-2">
                                  {opp.evidence.map((ev, idx) => (
                                    <div
                                      key={idx}
                                      className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                                    >
                                      <div className="flex items-center gap-2">
                                        <span
                                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                            SEVERITY_STYLES[ev.severity]
                                              ?.className ?? ""
                                          }`}
                                        >
                                          {ev.severity}
                                        </span>
                                        <span className="text-xs font-medium text-slate-700">
                                          {ev.product_name}
                                        </span>
                                        <span className="text-xs text-slate-400">
                                          ({ev.issue_type})
                                        </span>
                                      </div>
                                      <p className="mt-1 text-xs text-slate-600">
                                        {ev.description}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Financial Impact (estimated) */}
                              <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
                                <p className="text-xs font-semibold uppercase tracking-wider text-amber-700">
                                  Estimated Financial Impact
                                </p>
                                <p className="mt-1 text-sm font-semibold text-amber-900">
                                  {opp.financial_impact.estimate}
                                </p>
                                <p className="mt-2 text-xs font-medium text-amber-700">
                                  Direction: {opp.financial_impact.direction}
                                </p>
                                {opp.financial_impact.assumptions.length >
                                  0 && (
                                    <div className="mt-2">
                                      <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-600">
                                        Assumptions
                                      </p>
                                      <ul className="mt-1 list-disc pl-4">
                                        {opp.financial_impact.assumptions.map(
                                          (a, idx) => (
                                            <li
                                              key={idx}
                                              className="text-xs text-amber-800"
                                            >
                                              {a}
                                            </li>
                                          )
                                        )}
                                      </ul>
                                    </div>
                                  )}
                                <p className="mt-2 text-[10px] italic text-amber-600">
                                  This is an estimate based on assumptions —
                                  not a guaranteed result.
                                </p>
                              </div>

                              {/* Proposed Action */}
                              <div className="mb-5 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
                                <p className="text-xs font-semibold uppercase tracking-wider text-indigo-700">
                                  Proposed Action
                                </p>
                                <p className="mt-1 text-sm leading-6 text-indigo-900">
                                  {opp.proposed_action}
                                </p>
                              </div>

                              {/* Guardrails */}
                              <div className="mb-5">
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                  Guardrails & Limits
                                </p>
                                <ul className="mt-2 space-y-1">
                                  {opp.guardrails.map((g, idx) => (
                                    <li
                                      key={idx}
                                      className="flex items-start gap-2 text-sm text-slate-700"
                                    >
                                      <span className="mt-0.5 text-slate-400">
                                        &#9679;
                                      </span>
                                      {g}
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              {/* Audit metadata */}
                              <div className="mb-5 grid gap-3 sm:grid-cols-3">
                                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                                  <p className="text-[10px] font-semibold uppercase text-slate-500">
                                    Generation Method
                                  </p>
                                  <p className="mt-0.5 text-xs font-medium text-slate-700">
                                    {opp.audit.generation_method}
                                  </p>
                                </div>
                                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                                  <p className="text-[10px] font-semibold uppercase text-slate-500">
                                    Products Analyzed
                                  </p>
                                  <p className="mt-0.5 text-xs font-medium text-slate-700">
                                    {opp.audit.products_analyzed}
                                  </p>
                                </div>
                                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                                  <p className="text-[10px] font-semibold uppercase text-slate-500">
                                    Rule Version
                                  </p>
                                  <p className="mt-0.5 text-xs font-medium text-slate-700">
                                    {opp.audit.rule_version}
                                  </p>
                                </div>
                              </div>

                              {/* Approval controls */}
                              <div className="mb-5 border-t border-slate-100 pt-5">
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                  Merchant Approval
                                </p>
                                {opp.status === "proposed" && (
                                  <div className="mt-3">
                                    <p className="mb-2 text-sm text-slate-600">
                                      Review this opportunity. Approving will
                                      allow simulated execution only — no
                                      real financial changes will occur.
                                    </p>
                                    <div className="flex gap-3">
                                      <button
                                        onClick={() =>
                                          handleApproval(
                                            opp.opportunity_id,
                                            true
                                          )
                                        }
                                        disabled={
                                          approvalLoading ===
                                          opp.opportunity_id
                                        }
                                        className="rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                                      >
                                        {approvalLoading ===
                                        opp.opportunity_id
                                          ? "Processing..."
                                          : "Approve"}
                                      </button>
                                      <button
                                        onClick={() =>
                                          handleApproval(
                                            opp.opportunity_id,
                                            false
                                          )
                                        }
                                        disabled={
                                          approvalLoading ===
                                          opp.opportunity_id
                                        }
                                        className="rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                                      >
                                        Deny
                                      </button>
                                    </div>
                                  </div>
                                )}
                                {opp.status === "approved" && (
                                  <div className="mt-3">
                                    <p className="mb-3 text-sm font-medium text-emerald-700">
                                      Approved — Simulated execution available
                                    </p>
                                    {!execution && (
                                      <button
                                        onClick={() =>
                                          handleExecute(opp.opportunity_id)
                                        }
                                        disabled={
                                          execLoading === opp.opportunity_id
                                        }
                                        className="rounded-xl bg-purple-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-purple-700 disabled:opacity-50"
                                      >
                                        {execLoading === opp.opportunity_id
                                          ? "Executing..."
                                          : "Execute Simulated Discount"}
                                      </button>
                                    )}
                                  </div>
                                )}
                              </div>

                              {/* Simulated execution result */}
                              {execution && (
                                <div className="mb-5 rounded-2xl border-2 border-purple-200 bg-purple-50 p-5">
                                  <div className="mb-3 flex items-center gap-2">
                                    <span className="rounded-full bg-purple-600 px-3 py-1 text-xs font-bold text-white">
                                      SIMULATED
                                    </span>
                                    <span className="text-xs text-purple-700">
                                      No real financial transaction occurred
                                    </span>
                                  </div>
                                  <p className="mb-3 text-[10px] italic text-purple-600">
                                    {execution.disclaimer}
                                  </p>
                                  <div className="grid gap-3 sm:grid-cols-2">
                                    <div className="rounded-xl bg-white p-3">
                                      <p className="text-[10px] font-semibold uppercase text-slate-500">
                                        Original Price
                                      </p>
                                      <p className="mt-0.5 text-sm font-bold text-slate-900">
                                        {execution.original_value}
                                      </p>
                                    </div>
                                    <div className="rounded-xl bg-white p-3">
                                      <p className="text-[10px] font-semibold uppercase text-slate-500">
                                        Requested Discount
                                      </p>
                                      <p className="mt-0.5 text-sm font-bold text-slate-900">
                                        {execution.requested_value}
                                      </p>
                                    </div>
                                    <div className="rounded-xl bg-white p-3">
                                      <p className="text-[10px] font-semibold uppercase text-slate-500">
                                        Bounded Discount (Guardrail)
                                      </p>
                                      <p className="mt-0.5 text-sm font-bold text-slate-900">
                                        {execution.bounded_value}
                                      </p>
                                    </div>
                                    <div className="rounded-xl bg-white p-3">
                                      <p className="text-[10px] font-semibold uppercase text-slate-500">
                                        Guardrails Checked
                                      </p>
                                      <p className="mt-0.5 text-sm font-bold text-slate-900">
                                        {execution.guardrails_checked}
                                      </p>
                                    </div>
                                    <div className="rounded-xl bg-white p-3">
                                      <p className="text-[10px] font-semibold uppercase text-slate-500">
                                        Simulated Discount Amount
                                      </p>
                                      <p className="mt-0.5 text-sm font-bold text-emerald-700">
                                        {
                                          execution.simulated_result
                                            .discount_amount
                                        }
                                      </p>
                                    </div>
                                    <div className="rounded-xl bg-white p-3">
                                      <p className="text-[10px] font-semibold uppercase text-slate-500">
                                        Simulated Final Price
                                      </p>
                                      <p className="mt-0.5 text-sm font-bold text-emerald-700">
                                        {
                                          execution.simulated_result
                                            .final_price
                                        }
                                      </p>
                                    </div>
                                  </div>
                                  <p className="mt-3 text-[10px] font-medium text-purple-600">
                                    Product price was NOT changed. This is a
                                    simulation only.
                                  </p>
                                </div>
                              )}

                              {/* Audit trail */}
                              <div className="border-t border-slate-100 pt-5">
                                <button
                                  onClick={() =>
                                    toggleAuditTrail(opp.opportunity_id)
                                  }
                                  className="text-sm font-semibold text-slate-600 hover:text-slate-800"
                                >
                                  {isAuditOpen
                                    ? "Hide Audit Trail"
                                    : "View Audit Trail"}
                                </button>

                                {isAuditOpen && (
                                  <div className="mt-3">
                                    {auditLoading === opp.opportunity_id && (
                                      <p className="text-xs text-slate-500">
                                        Loading audit trail...
                                      </p>
                                    )}

                                    {auditError &&
                                      auditLoading !==
                                        opp.opportunity_id && (
                                        <p className="text-xs text-red-600">
                                          {auditError}
                                        </p>
                                      )}

                                    {trail &&
                                      auditLoading !== opp.opportunity_id &&
                                      !auditError && (
                                        <div className="mt-2 space-y-2">
                                          {trail.length === 0 && (
                                            <p className="text-xs text-slate-500">
                                              No audit events recorded yet.
                                            </p>
                                          )}
                                          {trail.map((event) => {
                                            const colorClass =
                                              EVENT_TYPE_COLORS[
                                                event.event_type
                                              ] ?? "bg-slate-50 text-slate-700";
                                            return (
                                              <div
                                                key={event.event_id}
                                                className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                                              >
                                                <div className="flex flex-wrap items-center gap-2">
                                                  <span
                                                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${colorClass}`}
                                                  >
                                                    {EVENT_TYPE_LABELS[
                                                      event.event_type
                                                    ] ?? event.event_type}
                                                  </span>
                                                  <span className="text-[10px] text-slate-500">
                                                    {formatTimestamp(
                                                      event.timestamp
                                                    )}
                                                  </span>
                                                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                                                    {event.actor}
                                                  </span>
                                                  {event.status && (
                                                    <span className="text-[10px] text-slate-600">
                                                      status: {event.status}
                                                    </span>
                                                  )}
                                                </div>
                                                {event.reason && (
                                                  <p className="mt-1 text-xs text-slate-600">
                                                    {event.reason}
                                                  </p>
                                                )}
                                                {Object.keys(event.metadata)
                                                  .length > 0 && (
                                                  <details className="mt-1">
                                                    <summary className="cursor-pointer text-[10px] text-slate-500 hover:text-slate-700">
                                                      Metadata
                                                    </summary>
                                                    <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-white p-2 text-[10px] text-slate-700">
                                                      {JSON.stringify(
                                                        event.metadata,
                                                        null,
                                                        2
                                                      )}
                                                    </pre>
                                                  </details>
                                                )}
                                              </div>
                                            );
                                          })}
                                        </div>
                                      )}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
