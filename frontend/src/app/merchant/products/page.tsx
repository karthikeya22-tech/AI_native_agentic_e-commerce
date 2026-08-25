"use client";

const products = [
  {
    name: "TechKart Laptop 1",
    category: "Laptop",
    price: "₹64,999",
    inventory: 24,
    status: "Active",
  },
  {
    name: "TechKart Smartphone 1",
    category: "Smartphone",
    price: "₹39,999",
    inventory: 42,
    status: "Active",
  },
  {
    name: "TechKart Tablet 1",
    category: "Tablet",
    price: "₹29,999",
    inventory: 18,
    status: "Active",
  },
  {
    name: "TechKart Wireless Headphones 1",
    category: "Audio",
    price: "₹8,999",
    inventory: 31,
    status: "Active",
  },
  {
    name: "TechKart Smartwatch 1",
    category: "Wearable",
    price: "₹12,999",
    inventory: 16,
    status: "Active",
  },
];

export default function MerchantProductsPage() {
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
            className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700"
          >
            Add Product
          </button>
        </div>

        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">Total Products</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">30</p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">Active Products</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">28</p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">AI Readiness</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">91%</p>
          </div>
        </div>

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
                    key={product.name}
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
                      {product.price}
                    </td>

                    <td className="px-6 py-4 text-slate-600">
                      {product.inventory}
                    </td>

                    <td className="px-6 py-4">
                      <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                        {product.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  );
}