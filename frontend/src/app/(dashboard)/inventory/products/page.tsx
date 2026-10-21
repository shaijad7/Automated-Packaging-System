"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Plus, Trash2, QrCode, X, Package, Pencil } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";

type InventoryRecord = {
  sku: string;
  quantity: number;
};

type Product = {
  sku: string;
  name: string;
  description: string | null;
  is_active: boolean;
  qr_code: string;
  quantity?: number;
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isLabelModalOpen, setIsLabelModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  
  // Add Product Form state
  const [newName, setNewName] = useState("");
  const [newSku, setNewSku] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newActive, setNewActive] = useState(true);
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // Edit Product Form state
  const [editSku, setEditSku] = useState("");
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [editError, setEditError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  // Label Modal state
  const [labelUrl, setLabelUrl] = useState<string | null>(null);
  const [labelLoading, setLabelLoading] = useState(false);
  const [labelSku, setLabelSku] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");

  const fetchProducts = async () => {
    setLoading(true);
    setError(null);
    try {
      const [prodRes, invRes] = await Promise.all([
        fetchWithAuth("/products/"),
        fetchWithAuth("/dashboard/inventory")
      ]);

      if (!prodRes.ok) throw new Error("Failed to fetch products");
      if (!invRes.ok) throw new Error("Failed to fetch inventory");

      const prodData = await prodRes.json();
      const invData = await invRes.json();

      const invMap = new Map<string, number>();
      invData.forEach((item: InventoryRecord) => {
        invMap.set(item.sku, item.quantity);
      });

      const merged = prodData.map((p: Product) => ({
        ...p,
        quantity: invMap.has(p.sku) ? invMap.get(p.sku) : 0
      }));

      setProducts(merged);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An error occurred";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const run = async () => {
      await fetchProducts();
    };
    void run();
  }, []);

  const handleAddProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);
    setAdding(true);

    try {
      const res = await fetchWithAuth("/products/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName,
          sku: newSku,
          description: newDesc || null,
          is_active: newActive,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to create product");
      }

      await fetchProducts();
      setIsAddModalOpen(false);
      setNewName("");
      setNewSku("");
      setNewDesc("");
      setNewActive(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An error occurred";
      setAddError(msg);
    } finally {
      setAdding(false);
    }
  };

  const handleOpenEditModal = (product: Product) => {
    setEditSku(product.sku);
    setEditName(product.name);
    setEditDesc(product.description || "");
    setEditActive(product.is_active);
    setEditError(null);
    setIsEditModalOpen(true);
  };

  const handleEditProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setEditError(null);

    const trimmedName = editName.trim();
    if (!trimmedName) {
      setEditError("Product name cannot be empty");
      return;
    }

    setEditing(true);

    try {
      const res = await fetchWithAuth(`/products/${editSku}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: trimmedName,
          description: editDesc ? editDesc.trim() : null,
          is_active: editActive,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        let message = "Failed to update product";
        if (typeof errData.detail === "string") {
          message = errData.detail;
        } else if (Array.isArray(errData.detail) && errData.detail.length > 0) {
          message = errData.detail[0].msg || JSON.stringify(errData.detail);
        }
        throw new Error(message);
      }

      await fetchProducts();
      setIsEditModalOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An error occurred updating the product";
      setEditError(msg);
    } finally {
      setEditing(false);
    }
  };

  const handleDelete = async (sku: string) => {
    const confirmationMessage =
      `Warning: Deleting product "${sku}" will permanently remove this item from the catalog and delete its associated inventory count.\n\n` +
      `• Historical events in the audit log will be retained.\n` +
      `• Future scans matching this QR code will no longer be recognized as valid products.\n` +
      `• For temporary discontinuation without data removal, use "Edit" to deactivate the product instead.\n\n` +
      `Are you sure you want to permanently delete "${sku}"?`;

    if (!confirm(confirmationMessage)) return;
    try {
      const res = await fetchWithAuth(`/products/${sku}`, { method: "DELETE" });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to delete product");
      }
      await fetchProducts();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An error occurred deleting the product";
      alert(msg);
    }
  };


  const handleViewLabel = async (sku: string) => {
    setIsLabelModalOpen(true);
    setLabelSku(sku);
    setLabelLoading(true);
    setLabelUrl(null);

    try {
      const res = await fetchWithAuth(`/products/${sku}/label`);

      if (!res.ok) {
        throw new Error("Failed to fetch label");
      }

      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      setLabelUrl(objectUrl);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "An error occurred loading the label";
      alert(message);
      setIsLabelModalOpen(false);
    } finally {
      setLabelLoading(false);
    }
  };

  const closeLabelModal = () => {
    setIsLabelModalOpen(false);
    if (labelUrl) {
      URL.revokeObjectURL(labelUrl);
      setLabelUrl(null);
    }
    setLabelSku(null);
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Products</h1>
          <p className="text-sm text-slate-500 mt-1">Manage physical inventory definitions and QR labels.</p>
        </div>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md font-medium text-sm flex items-center transition-colors shadow-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 w-full sm:w-auto justify-center"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Product
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-md mb-6 border border-red-200">
          {error}
        </div>
      )}

      {/* Search Bar */}
      <div className="mb-6">
        <input
          type="text"
          placeholder="Search by Product Name or SKU..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full md:w-1/3 px-4 py-2 border border-gray-300 rounded-md text-slate-900 bg-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
        />
      </div>

      {/* Main Table Container */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-slate-50 border-b border-gray-200 text-slate-600 font-semibold uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-4">Product Name</th>
                <th className="px-6 py-4">SKU</th>
                <th className="px-6 py-4">Description</th>
                <th className="px-6 py-4">Quantity</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">QR Label</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 text-slate-800">
              {(() => {
                if (loading) {
                  return (
                    <tr>
                      <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                        Loading products...
                      </td>
                    </tr>
                  );
                }

                if (products.length === 0) {
                  return (
                    <tr>
                      <td colSpan={7} className="px-6 py-16 text-center">
                        <div className="inline-flex flex-col items-center">
                          <Package className="w-12 h-12 text-slate-300 mb-3" />
                          <p className="text-slate-600 font-medium">No products registered</p>
                          <p className="text-slate-400 text-sm mt-1">Click &quot;Add Product&quot; to get started.</p>
                        </div>
                      </td>
                    </tr>
                  );
                }

                const filteredProducts = products.filter(
                  (p) =>
                    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    p.sku.toLowerCase().includes(searchQuery.toLowerCase())
                );

                if (filteredProducts.length === 0) {
                  return (
                    <tr>
                      <td colSpan={7} className="px-6 py-16 text-center">
                        <div className="inline-flex flex-col items-center">
                          <p className="text-slate-600 font-medium">No products match your search.</p>
                        </div>
                      </td>
                    </tr>
                  );
                }

                return filteredProducts.map((product) => (
                  <tr key={product.sku} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-medium">{product.name}</td>
                    <td className="px-6 py-4 font-mono text-slate-600">{product.sku}</td>
                    <td className="px-6 py-4 text-slate-500 truncate max-w-xs">{product.description || "-"}</td>
                    <td className="px-6 py-4 font-bold">{product.quantity}</td>
                    <td className="px-6 py-4">
                      {product.is_active ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 border border-gray-200">
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => handleViewLabel(product.sku)}
                        className="text-blue-600 hover:text-blue-800 flex items-center font-medium transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 rounded px-1 -ml-1"
                      >
                        <QrCode className="w-4 h-4 mr-1.5" />
                        View
                      </button>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="inline-flex items-center space-x-2">
                        <button
                          onClick={() => handleOpenEditModal(product)}
                          className="text-slate-400 hover:text-blue-600 transition-colors inline-flex items-center cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 rounded p-1"
                          title="Edit Product"
                          aria-label={`Edit ${product.sku}`}
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(product.sku)}
                          className="text-slate-400 hover:text-red-600 transition-colors inline-flex items-center cursor-pointer focus:outline-none focus:ring-2 focus:ring-red-500 rounded p-1"
                          title="Delete Product"
                          aria-label={`Delete ${product.sku}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ));
              })()}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Product Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden">
            <div className="flex justify-between items-center p-5 border-b border-gray-200">
              <h2 className="text-lg font-bold text-slate-800">Register Product</h2>
              <button onClick={() => setIsAddModalOpen(false)} className="text-gray-400 hover:text-gray-600 cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 rounded">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <form onSubmit={handleAddProduct} className="p-5 space-y-4">
              {addError && (
                <div className="p-3 text-sm text-red-700 bg-red-50 rounded border border-red-200">
                  {addError}
                </div>
              )}
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Product Name *</label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 bg-white placeholder-slate-400"
                  placeholder="e.g. Type-C Adapter"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">SKU *</label>
                <input
                  type="text"
                  required
                  value={newSku}
                  onChange={(e) => setNewSku(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-slate-900 bg-white placeholder-slate-400"
                  placeholder="e.g. ADP-001"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 bg-white placeholder-slate-400"
                  placeholder="Optional details..."
                  rows={2}
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="isActive"
                  checked={newActive}
                  onChange={(e) => setNewActive(e.target.checked)}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded cursor-pointer"
                />
                <label htmlFor="isActive" className="ml-2 block text-sm text-slate-700 cursor-pointer">
                  Active Status
                </label>
              </div>

              <div className="pt-4 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={adding}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:bg-blue-400 transition-colors shadow-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                >
                  {adding ? "Saving..." : "Save Product"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* QR Label Modal */}
      {isLabelModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-sm overflow-hidden flex flex-col max-h-[90vh]">
            <div className="flex justify-between items-center p-4 border-b border-gray-200 bg-slate-50 shrink-0">
              <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider">Product Label</h2>
              <button onClick={closeLabelModal} className="text-gray-400 hover:text-gray-600 cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 rounded">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-8 flex flex-col items-center justify-center min-h-[300px] overflow-y-auto">
              {labelLoading ? (
                <div className="text-slate-500 animate-pulse">Generating label...</div>
              ) : labelUrl ? (
                <div className="flex flex-col items-center">
                  <div className="border border-gray-200 p-2 bg-white shadow-sm mb-4">
                    <Image unoptimized src={labelUrl} alt={`Label for ${labelSku}`} width={256} height={256} className="max-w-full h-auto" />
                  </div>
                  <p className="text-xs text-slate-500 text-center">
                    Standard Industrial QR Format<br/>Print on 2&quot;x2&quot; adhesive stock
                  </p>
                </div>
              ) : (
                <div className="text-red-500">Failed to load label.</div>
              )}
            </div>
            
            <div className="p-4 border-t border-gray-200 bg-slate-50 flex justify-end space-x-3 shrink-0">
              <button
                onClick={closeLabelModal}
                className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2"
              >
                Close
              </button>
              {labelUrl && labelSku && (
                <a
                  href={labelUrl}
                  download={`${labelSku}-qr-label.png`}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 inline-flex items-center"
                >
                  <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                  Download QR Label
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Edit Product Modal */}
      {isEditModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden">
            <div className="flex justify-between items-center p-5 border-b border-gray-200">
              <h2 className="text-lg font-bold text-slate-800">Edit Product</h2>
              <button
                onClick={() => setIsEditModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleEditProduct} className="p-5 space-y-4">
              {editError && (
                <div className="p-3 text-sm text-red-700 bg-red-50 rounded border border-red-200" role="alert">
                  {editError}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">SKU</label>
                <input
                  type="text"
                  disabled
                  readOnly
                  value={editSku}
                  className="w-full px-3 py-2 border border-gray-200 bg-gray-100 rounded-md font-mono text-slate-500 cursor-not-allowed select-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Product Name *</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 bg-white placeholder-slate-400"
                  placeholder="e.g. Type-C Adapter"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                <textarea
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 bg-white placeholder-slate-400"
                  placeholder="Optional details..."
                  rows={2}
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="editIsActive"
                  checked={editActive}
                  onChange={(e) => setEditActive(e.target.checked)}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded cursor-pointer"
                />
                <label htmlFor="editIsActive" className="ml-2 block text-sm text-slate-700 cursor-pointer">
                  Active Status
                </label>
              </div>

              <div className="pt-4 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editing}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:bg-blue-400 transition-colors shadow-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                >
                  {editing ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
