"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useBuyerChat } from "@/hooks/useBuyerChat";
import type { ChatMessage, BuyerChatProduct } from "@/types/buyer-chat";

const FALLBACK_MERCHANT_NAME = "the store";

function ProductCard({
  product,
  merchantId,
}: {
  product: BuyerChatProduct;
  merchantId: string;
}) {
  const router = useRouter();
  const formattedPrice = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: product.currency,
  }).format(parseFloat(product.price));

  function handleBuyNow() {
    const params = new URLSearchParams({
      product_id: product.product_id,
      merchant_id: merchantId,
      product_name: product.name,
      quantity: "1",
    });
    router.push(`/buyer/checkout?${params.toString()}`);
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="font-semibold text-slate-900">{product.name}</p>
      <p className="mt-1 text-sm text-slate-600">{formattedPrice}</p>
      <p className="mt-1 text-xs text-slate-400">
        Relevance: {Math.round(product.similarity * 100)}%
      </p>
      <button
        type="button"
        onClick={handleBuyNow}
        className="mt-3 w-full rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-700"
      >
        Buy Now (Test Mode)
      </button>
    </div>
  );
}

function TypingIndicator() {
  return (
    <li className="flex justify-start">
      <span className="inline-flex items-center gap-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
      </span>
    </li>
  );
}

export default function BuyerChatPage() {
  const [merchantId, setMerchantId] = useState("");
  const [merchantName, setMerchantName] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { sendMessage, loading, error, resetError } = useBuyerChat();

  useEffect(() => {
    setMerchantId(sessionStorage.getItem("buyer_merchant_id") ?? "");
    setMerchantName(
      sessionStorage.getItem("buyer_merchant_name") ?? FALLBACK_MERCHANT_NAME
    );
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || loading || !merchantId) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "buyer", text },
    ]);
    setDraft("");

    try {
      const response = await sendMessage(merchantId, text);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.message,
          products: response.products,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "Sorry, something went wrong. Please try again.",
        },
      ]);
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
              AI Shopping Assistant
            </p>

            <h1 className="mt-1 text-lg font-bold text-slate-900">
              Shopping with {merchantName || "..."}
            </h1>
          </div>

          <Link
            href="/buyer"
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            Change Store
          </Link>
        </div>
      </header>

      {/* Messages */}
      <div className="flex flex-1 flex-col overflow-y-auto px-6 py-8">
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">
          {messages.length === 0 && !loading ? (
            <div className="m-auto max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
              <p className="font-semibold text-slate-900">
                Hi! How can I help you shop today?
              </p>

              <p className="mt-2 text-sm text-slate-600">
                Ask me about products, prices, or delivery options at{" "}
                {merchantName || FALLBACK_MERCHANT_NAME}.
              </p>
            </div>
          ) : (
            <ul className="space-y-3">
              {messages.map((message) => (
                <li
                  key={message.id}
                  className={`flex ${
                    message.role === "buyer" ? "justify-end" : "justify-start"
                  }`}
                >
                  <div
                    className={`max-w-sm rounded-2xl px-4 py-3 text-sm ${
                      message.role === "buyer"
                        ? "bg-indigo-600 text-white"
                        : "border border-slate-200 bg-white text-slate-700"
                    }`}
                  >
                    <p>{message.text}</p>

                    {message.products && message.products.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {message.products.map((product) => (
                          <ProductCard
                            key={product.product_id}
                            product={product}
                            merchantId={merchantId}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              ))}

              {loading && <TypingIndicator />}

              <div ref={messagesEndRef} />
            </ul>
          )}

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-center">
              <p className="text-sm text-red-700">{error}</p>
              <button
                type="button"
                onClick={resetError}
                className="mt-2 text-xs font-semibold text-red-600 underline hover:text-red-800"
              >
                Dismiss
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <footer className="border-t border-slate-200 bg-white px-6 py-4">
        <form onSubmit={handleSend} className="mx-auto flex max-w-3xl gap-3">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a message..."
            disabled={loading || !merchantId}
            className="flex-1 rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
          />

          <button
            type="submit"
            className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!draft.trim() || loading || !merchantId}
          >
            {loading ? "Sending..." : "Send"}
          </button>
        </form>
      </footer>
    </main>
  );
}
