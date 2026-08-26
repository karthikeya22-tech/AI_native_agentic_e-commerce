"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface ChatMessage {
  id: string;
  role: "buyer" | "merchant";
  text: string;
}

const FALLBACK_MERCHANT_NAME = "the store";

export default function BuyerChatPage() {
  const [merchantName, setMerchantName] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setMerchantName(
      sessionStorage.getItem("buyer_merchant_name") ??
        FALLBACK_MERCHANT_NAME
    );
  }, []);

  function handleSend() {
    const text = draft.trim();
    if (!text) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "buyer", text },
    ]);
    setDraft("");
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
          {messages.length === 0 ? (
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
                  <span
                    className={`max-w-sm rounded-2xl px-4 py-3 text-sm ${
                      message.role === "buyer"
                        ? "bg-indigo-600 text-white"
                        : "border border-slate-200 bg-white text-slate-700"
                    }`}
                  >
                    {message.text}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Composer */}
      <footer className="border-t border-slate-200 bg-white px-6 py-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="mx-auto flex max-w-3xl gap-3"
        >
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a message..."
            className="flex-1 rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />

          <button
            type="submit"
            className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!draft.trim()}
          >
            Send
          </button>
        </form>
      </footer>
    </main>
  );
}
