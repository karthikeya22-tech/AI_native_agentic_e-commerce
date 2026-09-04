"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Product = {
  id: string;
  name: string;
  description: string;
  category: string;
  price: number | string;
  currency: string;
  inventory_quantity: number;
  delivery_info: Record<string, unknown> | null;
  return_policy: string | null;
  is_active: boolean;
  created_at: string;
};

type ProductFormState = {
  name: string;
  description: string;
  category: string;
  price: string;
  currency: string;
  inventory_quantity: string;
  delivery_days: string;
  return_policy: string;
};

const EMPTY_FORM: ProductFormState = {
  name: "",
  description: "",
  category: "",
  price: "",
  currency: "INR",
  inventory_quantity: "0",
  delivery_days: "",
  return_policy: "",
};

function formatPrice(price: number | string, currency: string): string {
  const value = typeof price === "string" ? parseFloat(price) : price;

  if (Number.isNaN(value)) {
    return `${currency} —`;
  }

  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

export default function MerchantProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missingMerchant, setMissingMerchant] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<ProductFormState>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  const fetchProducts = useCallback(async () => {
    const merchantId = sessionStorage.getItem("merchant_id");

    if (!merchantId) {
      setMissingMerchant(true);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        `${API_BASE_URL}/api/v1/merchants/${merchantId}/products`
      );

      if (!response.ok) {
        throw new Error(
          `Unable to load products (HTTP ${response.status}).`
        );
      }

      const data = (await response.json()) as Product[];
      setProducts(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong while loading your products."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  function updateForm<K extends keyof ProductFormState>(
    key: K,
    value: string
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function validateForm(): string[] {
    const errors: string[] = [];

    if (!form.name.trim()) errors.push("Product name is required.");
    if (!form.description.trim()) errors.push("Description is required.");
    if (!form.category.trim()) errors.push("Category is required.");

    const price = Number(form.price);
    if (!form.price.trim()) {
      errors.push("Price is required.");
    } else if (Number.isNaN(price) || price < 0) {
      errors.push("Price must be a number greater than or equal to 0.");
    }

    const inventory = Number(form.inventory_quantity);
    if (
      !form.inventory_quantity.trim() ||
      !Number.isInteger(inventory) ||
      inventory < 0
    ) {
      errors.push(
        "Inventory quantity must be a whole number greater than or equal to 0."
      );
    }

    if (form.delivery_days.trim()) {
      const days = Number(form.delivery_days);
      if (!Number.isInteger(days) || days < 0) {
        errors.push(
          "Delivery days must be a whole number greater than or equal to 0."
        );
      }
    }

    return errors;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");

    const merchantId = sessionStorage.getItem("merchant_id");
    if (!merchantId) {
      setMissingMerchant(true);
      return;
    }

    const validationErrors = validateForm();
    if (validationErrors.length > 0) {
      setFormErrors(validationErrors);
      return;
    }
    setFormErrors([]);
    setSubmitting(true);

    const deliveryDays = form.delivery_days.trim();

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/merchants/${merchantId}/products`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: form.name.trim(),
            description: form.description.trim(),
            category: form.category.trim(),
            price: form.price.trim(),
            currency: form.currency.trim() || "INR",
            inventory_quantity: Number(form.inventory_quantity),
            delivery_info: deliveryDays ? { eta_days: Number(deliveryDays) } : null,
            return_policy: form.return_policy.trim() || null,
          }),
        }
      );

      if (!response.ok) {
        let detail = `Unable to create product (HTTP ${response.status}).`;
        try {
          const body = await response.json();
          if (typeof body?.detail === "string") {
            detail = body.detail;
          }
        } catch {
          // keep the generic message
        }
        throw new Error(detail);
      }

      setShowForm(false);
      setForm(EMPTY_FORM);
      setSuccessMessage(`"${form.name.trim()}" was added to your catalog.`);
      await fetchProducts();
    } catch (err) {
      setFormErrors([
        err instanceof Error
          ? err.message
          : "Something went wrong while creating the product.",
      ]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wider text-indigo-600">
              Merchant Console
            </p>

            <h1 className="mt-2 text-3xl font-bold text-slate-900">
              Products
            </h1>

            <p className="mt-2 text-slate-600">
              Manage your catalog and prepare products for AI buyers.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setSuccessMessage("");
              setFormErrors([]);
              setShowForm(true);
            }}
            className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700"
          >
            Add Product
          </button>
        </div>

        {successMessage && !showForm && (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
            {successMessage}
          </div>
        )}

        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
            <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-xl">
              <form onSubmit={handleSubmit} className="p-8">
                <h2 className="text-xl font-bold text-slate-900">
                  Add Product
                </h2>

                <p className="mt-1 text-sm text-slate-600">
                  Add a new product to your catalog.
                </p>

                {submitting && (
                  <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm font-medium text-indigo-700">
                    Creating product...
                  </div>
                )}

                {!submitting && formErrors.length > 0 && (
                  <ul className="mt-4 space-y-1 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {formErrors.map((message) => (
                      <li key={message}>{message}</li>
                    ))}
                  </ul>
                )}

                <div className="mt-6 grid gap-5 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label
                      htmlFor="productName"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Product Name *
                    </label>
                    <input
                      id="productName"
                      type="text"
                      required
                      value={form.name}
                      onChange={(e) => updateForm("name", e.target.value)}
                      placeholder="e.g. TechKart Wireless Mouse"
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label
                      htmlFor="productDescription"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Description *
                    </label>
                    <textarea
                      id="productDescription"
                      required
                      rows={3}
                      value={form.description}
                      onChange={(e) =>
                        updateForm("description", e.target.value)
                      }
                      placeholder="Describe the product for buyers and AI assistants..."
                      disabled={submitting}
                      className="w-full resize-none rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="productCategory"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Category *
                    </label>
                    <input
                      id="productCategory"
                      type="text"
                      required
                      value={form.category}
                      onChange={(e) => updateForm("category", e.target.value)}
                      placeholder="e.g. Electronics"
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="productPrice"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Price *
                    </label>
                    <input
                      id="productPrice"
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={form.price}
                      onChange={(e) => updateForm("price", e.target.value)}
                      placeholder="e.g. 1299.00"
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="productCurrency"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Currency
                    </label>
                    <select
                      id="productCurrency"
                      value={form.currency}
                      onChange={(e) => updateForm("currency", e.target.value)}
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    >
                      <option value="INR">INR</option>
                      <option value="USD">USD</option>
                    </select>
                  </div>

                  <div>
                    <label
                      htmlFor="productInventory"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Inventory Quantity
                    </label>
                    <input
                      id="productInventory"
                      type="number"
                      min="0"
                      step="1"
                      value={form.inventory_quantity}
                      onChange={(e) =>
                        updateForm("inventory_quantity", e.target.value)
                      }
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="productDeliveryDays"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Delivery Days
                    </label>
                    <input
                      id="productDeliveryDays"
                      type="number"
                      min="0"
                      step="1"
                      value={form.delivery_days}
                      onChange={(e) =>
                        updateForm("delivery_days", e.target.value)
                      }
                      placeholder="e.g. 3"
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label
                      htmlFor="productReturnPolicy"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Return Policy
                    </label>
                    <input
                      id="productReturnPolicy"
                      type="text"
                      value={form.return_policy}
                      onChange={(e) =>
                        updateForm("return_policy", e.target.value)
                      }
                      placeholder="e.g. 7-day returns"
                      disabled={submitting}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                    />
                  </div>
                </div>

                <div className="mt-8 flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    disabled={submitting}
                    className="rounded-xl border border-slate-300 px-5 py-3 font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {submitting ? "Creating..." : "Create Product"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {missingMerchant && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-8 text-center">
            <p className="font-semibold text-amber-900">
              No merchant account found
            </p>
            <p className="mt-2 text-sm text-amber-800">
              We couldn&apos;t find a merchant session. Please onboard your
              business first to view your products.
            </p>
            <Link
              href="/merchant"
              className="mt-4 inline-block rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700"
            >
              Go to Merchant Onboarding
            </Link>
          </div>
        )}

        {!missingMerchant && loading && (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="text-sm font-medium text-slate-500">
              Loading products...
            </p>
          </div>
        )}

        {!missingMerchant && !loading && error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
            <p className="font-semibold text-red-900">
              Failed to load products
            </p>
            <p className="mt-2 text-sm text-red-700">{error}</p>
          </div>
        )}

        {!missingMerchant && !loading && !error && products.length === 0 && (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="font-semibold text-slate-900">No products yet</p>
            <p className="mt-2 text-sm text-slate-600">
              Your catalog is empty. Add your first product to get started.
            </p>
          </div>
        )}

        {!missingMerchant && !loading && !error && products.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Product
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Category
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Price
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Inventory
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Status
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {products.map((product) => (
                    <tr
                      key={product.id}
                      className="transition hover:bg-slate-50"
                    >
                      <td className="px-6 py-4">
                        <p className="font-semibold text-slate-900">
                          {product.name}
                        </p>
                      </td>

                      <td className="px-6 py-4 text-slate-600">
                        {product.category}
                      </td>

                      <td className="px-6 py-4 font-medium text-slate-900">
                        {formatPrice(product.price, product.currency)}
                      </td>

                      <td className="px-6 py-4 text-slate-600">
                        {product.inventory_quantity}
                      </td>

                      <td className="px-6 py-4">
                        {product.is_active ? (
                          <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                            Active
                          </span>
                        ) : (
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                            Inactive
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
