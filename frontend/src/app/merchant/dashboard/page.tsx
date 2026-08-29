"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface ReadinessIssue {
  product_id: string;
  product_name: string;
  issue_type: string;
  description: string;
  severity: "low" | "medium" | "high";
  suggested_action: string;
}

interface ReadinessResponse {
  merchant_id: string;
  overall_score: number;
  products_analyzed: number;
  issues_count: number;
  issues: ReadinessIssue[];
}

type Priority = "low" | "medium" | "high";

interface GrowthRecommendation {
  title: string;
  explanation: string;
  suggested_action: string;
  expected_impact: string;
  priority: Priority;
}

interface GrowthRecommendationsResponse {
  merchant_id: string;
  recommendations: GrowthRecommendation[];
}

const SEVERITY_STYLES: Record<
  ReadinessIssue["severity"],
  { label: string; className: string }
> = {
  high: {
    label: "High",
    className: "bg-red-50 text-red-700",
  },
  medium: {
    label: "Medium",
    className: "bg-amber-50 text-amber-700",
  },
  low: {
    label: "Low",
    className: "bg-slate-100 text-slate-600",
  },
};

const PRIORITY_STYLES: Record<
  Priority,
  { label: string; className: string }
> = {
  high: {
    label: "High Priority",
    className: "bg-red-50 text-red-700",
  },
  medium: {
    label: "Medium Priority",
    className: "bg-amber-50 text-amber-700",
  },
  low: {
    label: "Low Priority",
    className: "bg-slate-100 text-slate-600",
  },
};

const metrics = [
  {
    label: "AI Growth Score",
    value: "82",
    suffix: "/100",
  },
  {
    label: "Total Products",
    value: "30",
    suffix: "",
  },
  {
    label: "AI Buyer Revenue",
    value: "₹1.1L",
    suffix: "",
  },
];

export default function MerchantDashboardPage() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missingMerchant, setMissingMerchant] = useState(false);

  const [recommendations, setRecommendations] = useState<
    GrowthRecommendation[]
  >([]);
  const [recsLoading, setRecsLoading] = useState(true);
  const [recsError, setRecsError] = useState("");

  useEffect(() => {
    const merchantId = sessionStorage.getItem("merchant_id");

    if (!merchantId) {
      setMissingMerchant(true);
      setLoading(false);
      setRecsLoading(false);
      return;
    }

    async function fetchReadiness() {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(
          `${API_BASE_URL}/api/v1/merchants/${merchantId}/readiness`
        );

        if (!response.ok) {
          throw new Error(
            `Unable to load readiness score (HTTP ${response.status}).`
          );
        }

        setReadiness((await response.json()) as ReadinessResponse);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading your readiness score."
        );
      } finally {
        setLoading(false);
      }
    }

    async function fetchRecommendations() {
      try {
        setRecsLoading(true);
        setRecsError("");

        const response = await fetch(
          `${API_BASE_URL}/api/v1/merchants/${merchantId}/growth-recommendations`
        );

        if (!response.ok) {
          throw new Error(
            `Unable to load growth recommendations (HTTP ${response.status}).`
          );
        }

        const data =
          (await response.json()) as GrowthRecommendationsResponse;
        setRecommendations(data.recommendations);
      } catch (err) {
        setRecsError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading your growth recommendations."
        );
      } finally {
        setRecsLoading(false);
      }
    }

    fetchReadiness();
    fetchRecommendations();
  }, []);

  const overallScore = readiness?.overall_score ?? null;

  const readinessMetric = {
    label: "AI Commerce Readiness",
    value: overallScore === null ? "—" : String(overallScore),
    suffix: "/100",
  };

  const metricsWithReadiness = [
    metrics[0],
    readinessMetric,
    metrics[1],
    metrics[2],
  ];
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
              className="block rounded-xl bg-indigo-50 px-4 py-3 font-medium text-indigo-700"
            >
              Dashboard
            </Link>

            <Link
              href="/merchant/products"
              className="block rounded-xl px-4 py-3 text-slate-600 hover:bg-slate-50"
            >
              Products
            </Link>

            <button className="block w-full rounded-xl px-4 py-3 text-left text-slate-600 hover:bg-slate-50">
              AI Commerce Readiness
            </button>

            <Link
              href="/merchant/growth"
              className="block rounded-xl px-4 py-3 text-slate-600 hover:bg-slate-50"
            >
              Growth Opportunities
            </Link>

            <button className="block w-full rounded-xl px-4 py-3 text-left text-slate-600 hover:bg-slate-50">
              Settings
            </button>
          </nav>
        </aside>

        {/* Main content */}
        <section className="flex-1 p-6 lg:p-10">
          <div className="mx-auto max-w-7xl">
            <div className="mb-10">
              <p className="text-sm font-medium text-indigo-600">
                Merchant Growth Console
              </p>

              <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
                Good morning, TechKart
              </h1>

              <p className="mt-2 text-slate-600">
                Your AI commerce system has identified new opportunities to
                improve conversion and revenue.
              </p>
            </div>

            {missingMerchant && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-8 text-center">
                <p className="font-semibold text-amber-900">
                  No merchant account found
                </p>
                <p className="mt-2 text-sm text-amber-800">
                  We couldn&apos;t find a merchant session. Please onboard your
                  business first to view your dashboard.
                </p>
                <Link
                  href="/merchant"
                  className="mt-4 inline-block rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700"
                >
                  Go to Merchant Onboarding
                </Link>
              </div>
            )}

            {!missingMerchant && (
              <>
            {/* Metrics */}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {metricsWithReadiness.map((metric) => (
                <div
                  key={metric.label}
                  className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
                >
                  <p className="text-sm font-medium text-slate-500">
                    {metric.label}
                  </p>

                  <div className="mt-3 flex items-baseline gap-1">
                    <span className="text-3xl font-bold text-slate-900">
                      {metric.value}
                    </span>

                    {metric.suffix && (
                      <span className="text-sm text-slate-500">
                        {metric.suffix}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Opportunities */}
            <section className="mt-10">
              <div className="mb-5">
                <h2 className="text-xl font-bold text-slate-900">
                  AI Growth Opportunities
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  Recommendations generated from your catalog readiness
                  signals.
                </p>
              </div>

              {recsLoading && (
                <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
                  <p className="text-sm font-medium text-slate-500">
                    Generating AI recommendations...
                  </p>
                </div>
              )}

              {!recsLoading && recsError && (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
                  <p className="font-semibold text-red-900">
                    Failed to load recommendations
                  </p>
                  <p className="mt-2 text-sm text-red-700">{recsError}</p>
                </div>
              )}

              {!recsLoading && !recsError && recommendations.length === 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
                  <p className="font-semibold text-slate-900">
                    No growth opportunities right now
                  </p>
                  <p className="mt-2 text-sm text-slate-600">
                    Your catalog looks healthy. Check back after adding new
                    products.
                  </p>
                </div>
              )}

              {!recsLoading && !recsError && recommendations.length > 0 && (
                <div className="space-y-4">
                  {recommendations.map((recommendation, index) => {
                    const priority = PRIORITY_STYLES[recommendation.priority];
                    return (
                      <div
                        key={`${recommendation.title}-${index}`}
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
                      >
                        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                          <div className="max-w-3xl">
                            <div className="flex flex-wrap items-center gap-3">
                              <span
                                className={`rounded-full px-3 py-1 text-xs font-semibold ${priority.className}`}
                              >
                                {priority.label}
                              </span>

                              <h3 className="text-base font-semibold text-slate-900">
                                {recommendation.title}
                              </h3>
                            </div>

                            <p className="mt-2 text-sm leading-6 text-slate-600">
                              {recommendation.explanation}
                            </p>

                            <p className="mt-3 text-sm font-medium text-indigo-600">
                              Suggested action:{" "}
                              {recommendation.suggested_action}
                            </p>

                            <p className="mt-3 text-sm font-semibold text-emerald-600">
                              Expected impact: {recommendation.expected_impact}
                            </p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Readiness */}
            <section className="mt-10 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-sm font-medium text-indigo-600">
                    AI Commerce Readiness
                  </p>

                  {loading && (
                    <h2 className="mt-2 text-2xl font-bold text-slate-400">
                      Loading...
                    </h2>
                  )}

                  {!loading && error && (
                    <h2 className="mt-2 text-2xl font-bold text-red-600">
                      Unavailable
                    </h2>
                  )}

                  {!loading && !error && overallScore !== null && (
                    <h2 className="mt-2 text-2xl font-bold text-slate-900">
                      {overallScore} / 100
                    </h2>
                  )}

                  {!loading && !error && (
                    <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
                      {overallScore === null
                        ? "Add products to your catalog to see your AI commerce readiness score."
                        : overallScore >= 90
                        ? "Your catalog is well prepared for AI-driven product discovery. A few improvements could make products easier for AI buyers to understand."
                        : "Address the issues below to make your catalog easier for AI buyers to understand."}
                    </p>
                  )}
                </div>

                <div className="min-w-56">
                  <div className="mb-2 flex justify-between text-sm">
                    <span className="text-slate-500">Readiness</span>
                    <span className="font-semibold text-slate-900">
                      {overallScore === null ? "—%" : `${overallScore}%`}
                    </span>
                  </div>

                  <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-indigo-600 transition-all"
                      style={{ width: `${overallScore ?? 0}%` }}
                    />
                  </div>
                </div>
              </div>

              {loading && (
                <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-500">
                  Analyzing your catalog...
                </div>
              )}

              {!loading && error && (
                <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {!loading && !error && readiness && (
                <div className="mt-6 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm text-slate-500">Products Analyzed</p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">
                      {readiness.products_analyzed}
                    </p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm text-slate-500">Issues Found</p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">
                      {readiness.issues_count}
                    </p>
                  </div>
                </div>
              )}
            </section>

            {/* Issues */}
            {!loading && !error && readiness && readiness.issues.length > 0 && (
              <section className="mt-6">
                <h3 className="mb-4 text-lg font-bold text-slate-900">
                  Catalog Issues
                </h3>

                <div className="space-y-3">
                  {readiness.issues.map((issue) => {
                    const severity = SEVERITY_STYLES[issue.severity];
                    return (
                      <div
                        key={`${issue.product_id}-${issue.issue_type}`}
                        className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="max-w-3xl">
                          <div className="flex items-center gap-3">
                            <span
                              className={`rounded-full px-3 py-1 text-xs font-semibold ${severity.className}`}
                            >
                              {severity.label}
                            </span>

                            <p className="text-sm font-semibold text-slate-900">
                              {issue.product_name}
                            </p>
                          </div>

                          <p className="mt-2 text-sm text-slate-600">
                            {issue.description}
                          </p>

                          <p className="mt-2 text-sm font-medium text-indigo-600">
                            Suggested action: {issue.suggested_action}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}