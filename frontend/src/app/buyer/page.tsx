"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface Merchant {
  id: string;
  name: string;
  category: string;
  description: string | null;
  status: "active" | "inactive";
}

interface MerchantCardProps {
  merchant: Merchant;
  onSelect: (merchant: Merchant) => void;
}

function MerchantCard({ merchant, onSelect }: MerchantCardProps) {
  return (
    <div className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:shadow-md">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
          {merchant.category}
        </p>

        <h2 className="mt-2 text-xl font-bold text-slate-900">
          {merchant.name}
        </h2>

        <p className="mt-2 text-sm leading-6 text-slate-600">
          {merchant.description ?? "No description available."}
        </p>
      </div>

      <button
        type="button"
        onClick={() => onSelect(merchant)}
        className="mt-6 w-full rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700"
      >
        Start Shopping
      </button>
    </div>
  );
}

export default function BuyerPage() {
  const router = useRouter();

  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchMerchants() {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(`${API_BASE_URL}/api/v1/merchants`);

        if (!response.ok) {
          throw new Error(
            `Unable to load stores (HTTP ${response.status}).`
          );
        }

        setMerchants((await response.json()) as Merchant[]);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading stores."
        );
      } finally {
        setLoading(false);
      }
    }

    fetchMerchants();
  }, []);

  function handleSelect(merchant: Merchant) {
    sessionStorage.setItem("buyer_merchant_id", merchant.id);
    sessionStorage.setItem("buyer_merchant_name", merchant.name);
    router.push("/buyer/chat");
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="mb-10 text-center">
          <p className="text-sm font-semibold uppercase tracking-wider text-indigo-600">
            AI Shopping Assistant
          </p>

          <h1 className="mt-3 text-4xl font-bold tracking-tight text-slate-900">
            Choose a store to shop from
          </h1>

          <p className="mx-auto mt-3 max-w-xl text-slate-600">
            Pick a merchant below and our AI assistant will help you find the
            right product.
          </p>
        </div>

        {loading && (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="text-sm font-medium text-slate-500">
              Loading stores...
            </p>
          </div>
        )}

        {!loading && error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
            <p className="font-semibold text-red-900">Failed to load stores</p>
            <p className="mt-2 text-sm text-red-700">{error}</p>
          </div>
        )}

        {!loading && !error && merchants.length === 0 && (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="font-semibold text-slate-900">No stores available</p>
            <p className="mt-2 text-sm text-slate-600">
              There are no active merchants right now. Please check back soon.
            </p>
          </div>
        )}

        {!loading && !error && merchants.length > 0 && (
          <div className="grid gap-6 md:grid-cols-3">
            {merchants.map((merchant) => (
              <MerchantCard
                key={merchant.id}
                merchant={merchant}
                onSelect={handleSelect}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
