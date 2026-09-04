"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface CheckoutState {
  order_id: string;
  razorpay_order_id: string;
  razorpay_key_id: string;
  amount_paise: number;
  currency: string;
  product_name: string;
  unit_price: string;
  total_amount: string;
  quantity: number;
  merchant_name: string;
  status: string;
  environment: string;
}

interface PaymentResult {
  order_id: string;
  status: string;
  razorpay_payment_id: string | null;
  total_amount: string | null;
  idempotent: boolean;
}

declare global {
  interface Window {
    Razorpay: new (options: Record<string, unknown>) => {
      open: () => void;
      on: (event: string, handler: (response: Record<string, unknown>) => void) => void;
    };
  }
}

function CheckoutContent() {
  const searchParams = useSearchParams();
  const productId = searchParams.get("product_id") || "";
  const merchantId = searchParams.get("merchant_id") || "";
  const productName = searchParams.get("product_name") || "";
  const quantity = parseInt(searchParams.get("quantity") || "1", 10);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [checkoutData, setCheckoutData] = useState<CheckoutState | null>(null);
  const [paymentResult, setPaymentResult] = useState<PaymentResult | null>(null);
  const [paymentLoading, setPaymentLoading] = useState(false);

  const initiateCheckout = useCallback(async () => {
    if (!merchantId || !productId) {
      setError("Missing merchant or product information.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError("");

      const response = await fetch(`${API_BASE_URL}/api/v1/buyer/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          merchant_id: merchantId,
          product_id: productId,
          quantity,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.detail ?? `Checkout failed (HTTP ${response.status})`
        );
      }

      const data = (await response.json()) as CheckoutState;
      setCheckoutData(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Something went wrong during checkout."
      );
    } finally {
      setLoading(false);
    }
  }, [merchantId, productId, quantity]);

  useEffect(() => {
    initiateCheckout();
  }, [initiateCheckout]);

  const handlePayment = async () => {
    if (!checkoutData) return;

    setPaymentLoading(true);

    try {
      // Load Razorpay script if not already loaded
      if (!window.Razorpay) {
        const script = document.createElement("script");
        script.src = "https://checkout.razorpay.com/v1/checkout.js";
        script.async = true;
        await new Promise<void>((resolve, reject) => {
          script.onload = () => resolve();
          script.onerror = () => reject(new Error("Failed to load Razorpay SDK"));
          document.body.appendChild(script);
        });
      }

      const options = {
        key: checkoutData.razorpay_key_id,
        amount: checkoutData.amount_paise,
        currency: checkoutData.currency,
        name: checkoutData.merchant_name,
        description: `Purchase: ${checkoutData.product_name}`,
        order_id: checkoutData.razorpay_order_id,
        handler: async function (response: Record<string, unknown>) {
          // Payment successful - verify server-side
          try {
            const verifyResponse = await fetch(
              `${API_BASE_URL}/api/v1/buyer/verify-payment`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  order_id: checkoutData.order_id,
                  razorpay_order_id: response.razorpay_order_id,
                  razorpay_payment_id: response.razorpay_payment_id,
                  razorpay_signature: response.razorpay_signature,
                }),
              }
            );

            if (!verifyResponse.ok) {
              const body = await verifyResponse.json().catch(() => null);
              throw new Error(
                body?.detail ?? `Payment verification failed (HTTP ${verifyResponse.status})`
              );
            }

            const result = (await verifyResponse.json()) as PaymentResult;
            setPaymentResult(result);
          } catch (err) {
            setError(
              err instanceof Error
                ? err.message
                : "Payment verification failed. Please contact support."
            );
          }
        },
        prefill: {
          contact: "",
          email: "",
        },
        notes: {
          environment: "TEST_MODE",
        },
        theme: {
          color: "#4f46e5",
        },
        modal: {
          ondismiss: function () {
            setPaymentLoading(false);
          },
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.on("payment.failed", function (response: Record<string, unknown>) {
        const errorResponse = response.error as Record<string, string> | undefined;
        setError(
          errorResponse?.description ?? "Payment failed. Please try again."
        );
        setPaymentLoading(false);
      });
      rzp.open();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to initialize payment."
      );
      setPaymentLoading(false);
    }
  };

  const formattedPrice = checkoutData
    ? new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: checkoutData.currency,
      }).format(parseFloat(checkoutData.total_amount))
    : "";

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-2xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <p className="text-sm font-semibold uppercase tracking-wider text-indigo-600">
            Checkout
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900">
            Complete Your Purchase
          </h1>
          <div className="mt-3 inline-block rounded-full bg-amber-100 px-4 py-1.5">
            <p className="text-sm font-bold text-amber-800">
              TEST MODE — No real money will be charged
            </p>
          </div>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
            <p className="text-sm font-medium text-slate-500">
              Creating your order...
            </p>
          </div>
        )}

        {/* Error state */}
        {!loading && error && !paymentResult && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
            <p className="font-semibold text-red-900">Checkout Error</p>
            <p className="mt-2 text-sm text-red-700">{error}</p>
            <Link
              href="/buyer/chat"
              className="mt-4 inline-block rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
            >
              Return to Chat
            </Link>
          </div>
        )}

        {/* Payment success */}
        {paymentResult && (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-8 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
              <svg
                className="h-6 w-6 text-emerald-600"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4.5 12.75l6 6 9-13.5"
                />
              </svg>
            </div>
            <p className="font-semibold text-emerald-900">
              Payment Successful!
            </p>
            <p className="mt-2 text-sm text-emerald-700">
              Your order has been confirmed. Thank you for your purchase!
            </p>
            {paymentResult.total_amount && (
              <p className="mt-3 text-lg font-bold text-emerald-800">
                Amount: {paymentResult.total_amount}
              </p>
            )}
            {paymentResult.idempotent && (
              <p className="mt-2 text-xs text-emerald-600">
                (This was a duplicate verification — no additional charge)
              </p>
            )}
            <p className="mt-2 text-xs text-emerald-600">
              Payment ID: {paymentResult.razorpay_payment_id}
            </p>
            <Link
              href="/buyer/chat"
              className="mt-6 inline-block rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
            >
              Continue Shopping
            </Link>
          </div>
        )}

        {/* Order details */}
        {!loading && checkoutData && !paymentResult && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900">Order Summary</h2>

            <div className="mt-4 space-y-3">
              <div className="flex justify-between border-b border-slate-100 pb-3">
                <span className="text-sm text-slate-600">Product</span>
                <span className="text-sm font-semibold text-slate-900">
                  {checkoutData.product_name}
                </span>
              </div>

              <div className="flex justify-between border-b border-slate-100 pb-3">
                <span className="text-sm text-slate-600">Merchant</span>
                <span className="text-sm font-semibold text-slate-900">
                  {checkoutData.merchant_name}
                </span>
              </div>

              <div className="flex justify-between border-b border-slate-100 pb-3">
                <span className="text-sm text-slate-600">Quantity</span>
                <span className="text-sm font-semibold text-slate-900">
                  {checkoutData.quantity}
                </span>
              </div>

              <div className="flex justify-between border-b border-slate-100 pb-3">
                <span className="text-sm text-slate-600">Unit Price</span>
                <span className="text-sm font-semibold text-slate-900">
                  {new Intl.NumberFormat("en-IN", {
                    style: "currency",
                    currency: checkoutData.currency,
                  }).format(parseFloat(checkoutData.unit_price))}
                </span>
              </div>

              <div className="flex justify-between pt-1">
                <span className="text-base font-bold text-slate-900">
                  Total
                </span>
                <span className="text-base font-bold text-indigo-600">
                  {formattedPrice}
                </span>
              </div>
            </div>

            <div className="mt-4 rounded-xl bg-slate-50 p-3">
              <p className="text-xs text-slate-500">
                Order ID: {checkoutData.order_id}
              </p>
              <p className="text-xs text-slate-500">
                Razorpay Order: {checkoutData.razorpay_order_id}
              </p>
              <p className="text-xs text-slate-500">
                Environment: {checkoutData.environment}
              </p>
            </div>

            {/* Payment button */}
            <button
              onClick={handlePayment}
              disabled={paymentLoading}
              className="mt-6 w-full rounded-xl bg-indigo-600 px-5 py-3.5 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {paymentLoading
                ? "Processing Payment..."
                : `Pay ${formattedPrice} (Test Mode)`}
            </button>

            <p className="mt-3 text-center text-xs text-slate-500">
              You will be redirected to Razorpay test mode payment.
              <br />
              Use test card: 4111 1111 1111 1111
            </p>

            <Link
              href="/buyer/chat"
              className="mt-4 block text-center text-sm font-semibold text-slate-600 hover:text-slate-800"
            >
              Cancel and return to chat
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}

function CheckoutLoading() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-2xl text-center">
        <div className="rounded-2xl border border-slate-200 bg-white p-10 shadow-sm">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
          <p className="text-sm font-medium text-slate-500">Loading checkout...</p>
        </div>
      </div>
    </main>
  );
}

export default function BuyerCheckoutPage() {
  return (
    <Suspense fallback={<CheckoutLoading />}>
      <CheckoutContent />
    </Suspense>
  );
}
