"use client";

import Link from "next/link";

const opportunities = [
  {
    title: "High-intent buyers are abandoning Laptop Pro",
    description:
      "Many shoppers reach the offer stage but leave before checkout. Delivery visibility may be a conversion blocker.",
    impact: "+8–12% conversion opportunity",
  },
  {
    title: "Prepaid negotiation offers are performing better",
    description:
      "Buyers asking for discounts appear more likely to complete purchases when offered a prepaid incentive.",
    impact: "Potential revenue improvement",
  },
  {
    title: "Product information can be more AI-readable",
    description:
      "Some products are missing structured information that helps AI buyers understand their strongest use cases.",
    impact: "+AI discoverability",
  },
];

const metrics = [
  {
    label: "AI Growth Score",
    value: "82",
    suffix: "/100",
  },
  {
    label: "AI Commerce Readiness",
    value: "91",
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

            <button className="block w-full rounded-xl px-4 py-3 text-left text-slate-600 hover:bg-slate-50">
              Growth Opportunities
            </button>

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

            {/* Metrics */}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {metrics.map((metric) => (
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
                  Recommendations generated from buyer behavior and commerce
                  signals.
                </p>
              </div>

              <div className="space-y-4">
                {opportunities.map((opportunity) => (
                  <div
                    key={opportunity.title}
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
                  >
                    <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                      <div className="max-w-3xl">
                        <h3 className="text-base font-semibold text-slate-900">
                          {opportunity.title}
                        </h3>

                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          {opportunity.description}
                        </p>

                        <p className="mt-3 text-sm font-semibold text-emerald-600">
                          {opportunity.impact}
                        </p>
                      </div>

                      <button className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                        View Opportunity
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Readiness */}
            <section className="mt-10 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-sm font-medium text-indigo-600">
                    AI Commerce Readiness
                  </p>

                  <h2 className="mt-2 text-2xl font-bold text-slate-900">
                    91 / 100
                  </h2>

                  <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
                    Your catalog is well prepared for AI-driven product
                    discovery. A few improvements could make products easier
                    for AI buyers to understand.
                  </p>
                </div>

                <div className="min-w-56">
                  <div className="mb-2 flex justify-between text-sm">
                    <span className="text-slate-500">Readiness</span>
                    <span className="font-semibold text-slate-900">
                      91%
                    </span>
                  </div>

                  <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-indigo-600"
                      style={{ width: "91%" }}
                    />
                  </div>
                </div>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}