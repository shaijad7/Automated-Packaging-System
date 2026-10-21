"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import {
  Copy,
  Layers,
  Info,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  AlertTriangle,
  Boxes,
} from "lucide-react";

interface DuplicateSummary {
  repeated_scans_count: number;
  id_conflicts_count: number;
  same_sku_groups_count: number;
  has_serialized_box_ids: boolean;
  schema_notice: string;
}

interface DuplicateItem {
  box_id: string;
  sku: string;
  product_name?: string | null;
  category: string;
  reason: string;
  first_seen: string;
  last_seen: string;
  review_status: string;
  details?: string;
}

interface SameSkuGroup {
  sku: string;
  product_name?: string | null;
  box_count: number;
  sample_event_ids: string[];
  box_ids?: string[] | null;
  has_distinct_box_ids: boolean;
  first_seen: string;
  last_seen: string;
  review_status: string;
  reason: string;
}

interface DuplicateBoxesData {
  summary: DuplicateSummary;
  repeated_scans_and_conflicts: DuplicateItem[];
  same_sku_groups: SameSkuGroup[];
}

export default function DuplicateBoxesPage() {
  const [duplicateData, setDuplicateData] = useState<DuplicateBoxesData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDuplicateBoxes = async (isBackground = false) => {
    try {
      if (!isBackground) {
        setLoading(true);
        setError(null);
      }
      const res = await fetchWithAuth("/dashboard/duplicate-boxes");
      if (!res.ok) throw new Error("Failed to load duplicate boxes data");
      const data: DuplicateBoxesData = await res.json();
      setDuplicateData(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An error occurred";
      if (!isBackground) setError(msg);
      else console.error("Background duplicate boxes refresh failed", err);
    } finally {
      if (!isBackground) setLoading(false);
    }
  };

  useEffect(() => {
    const run = async () => {
      await fetchDuplicateBoxes();
    };
    void run();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchDuplicateBoxes(true);
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Copy className="w-6 h-6 text-indigo-600" />
            <h2 className="text-2xl font-bold text-slate-800">Duplicate Boxes</h2>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Inspection of repeated scan events, Box ID conflicts, and multi-box SKU inventory groups.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchDuplicateBoxes(false)}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 shadow-sm transition-colors disabled:opacity-50 cursor-pointer"
            title="Refresh duplicate analysis"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-indigo-600" : "text-slate-500"}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider">
              Repeated Scans
            </span>
            <AlertTriangle className="text-amber-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">
            {duplicateData?.summary?.repeated_scans_count ?? 0}
          </span>
          <span className="text-xs text-slate-400 mt-2">Identical event retries</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider">
              ID Conflicts
            </span>
            <AlertCircle className="text-red-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">
            {duplicateData?.summary?.id_conflicts_count ?? 0}
          </span>
          <span className="text-xs text-slate-400 mt-2">Conflicting SKUs for same Box ID</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider">
              Same-SKU Groups
            </span>
            <Boxes className="text-blue-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">
            {duplicateData?.summary?.same_sku_groups_count ?? 0}
          </span>
          <span className="text-xs text-slate-400 mt-2">Distinct physical box multi-packs</span>
        </div>
      </div>

      {/* Schema Notice Banner */}
      {duplicateData?.summary?.schema_notice && (
        <div className="flex items-start gap-2.5 p-4 bg-blue-50/80 border border-blue-200 rounded-lg text-xs text-blue-900 leading-relaxed shadow-xs">
          <Info className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
          <div>
            <span className="font-semibold text-blue-950">Current Schema Contract: </span>
            {duplicateData.summary.schema_notice}
          </div>
        </div>
      )}

      {/* Error Alert with Retry Action */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between text-sm text-red-700">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => fetchDuplicateBoxes(false)}
            className="px-3.5 py-1.5 text-xs font-semibold bg-white text-red-700 border border-red-300 rounded-md hover:bg-red-50 shadow-xs cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Content Area: Loading / Tables */}
      {loading && !duplicateData ? (
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm py-16 flex flex-col items-center justify-center text-slate-400 gap-3">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
          <span className="text-sm font-medium">Analyzing event spools and SKU groups...</span>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Section 1: Repeated Scans & ID Conflicts */}
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Copy className="w-4 h-4 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider">
                  1. Repeated Scans &amp; ID Conflicts
                </h3>
              </div>
              <span
                className={`px-2.5 py-0.5 text-xs font-bold rounded-full ${
                  (duplicateData?.summary?.repeated_scans_count || 0) +
                    (duplicateData?.summary?.id_conflicts_count || 0) >
                  0
                    ? "bg-amber-100 text-amber-800 border border-amber-200"
                    : "bg-emerald-100 text-emerald-800 border border-emerald-200"
                }`}
              >
                {(duplicateData?.summary?.repeated_scans_count || 0) +
                  (duplicateData?.summary?.id_conflicts_count || 0)}{" "}
                issues detected
              </span>
            </div>

            {duplicateData?.repeated_scans_and_conflicts.length === 0 ? (
              <div className="p-4 bg-slate-50 border border-slate-100 rounded-lg flex items-center gap-3 text-sm text-slate-600">
                <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
                <div>
                  <p className="font-medium text-slate-700">No repeated scans or ID conflicts detected</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    All processed events have unique IDs and consistent SKU associations.
                  </p>
                </div>
              </div>
            ) : (
              <div className="overflow-auto max-h-[400px] border border-slate-200 rounded-lg">
                <table className="w-full text-left border-collapse min-w-[700px]">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500 sticky top-0 z-10">
                      <th className="px-4 py-2.5 font-semibold">Box / Event ID</th>
                      <th className="px-4 py-2.5 font-semibold">SKU</th>
                      <th className="px-4 py-2.5 font-semibold">Product Name</th>
                      <th className="px-4 py-2.5 font-semibold">Category / Reason</th>
                      <th className="px-4 py-2.5 font-semibold">First Seen</th>
                      <th className="px-4 py-2.5 font-semibold">Last Seen</th>
                      <th className="px-4 py-2.5 font-semibold">Review Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-xs text-slate-700">
                    {duplicateData?.repeated_scans_and_conflicts.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/70">
                        <td className="px-4 py-2.5 font-mono text-[11px] text-slate-900 font-medium">{item.box_id}</td>
                        <td className="px-4 py-2.5 font-mono text-[11px] text-slate-600">{item.sku}</td>
                        <td className="px-4 py-2.5 font-medium">{item.product_name || "-"}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                              item.category === "ID_CONFLICT"
                                ? "bg-red-100 text-red-700 border border-red-200"
                                : "bg-amber-100 text-amber-700 border border-amber-200"
                            }`}
                          >
                            {item.category}
                          </span>
                          <span className="block text-[11px] text-slate-500 mt-0.5">{item.reason}</span>
                        </td>
                        <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{item.first_seen}</td>
                        <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{item.last_seen}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                              item.review_status === "NEEDS_REVIEW"
                                ? "bg-red-100 text-red-800 border border-red-200"
                                : item.review_status === "REVIEW_CANDIDATE"
                                ? "bg-amber-100 text-amber-800 border border-amber-200"
                                : "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {item.review_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Section 2: Same-SKU Groups */}
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider">
                  2. Same-SKU Groups (Distinct Box Observations)
                </h3>
              </div>
              <span className="px-2.5 py-0.5 text-xs font-bold rounded-full bg-blue-100 text-blue-800 border border-blue-200 self-start sm:self-auto">
                {duplicateData?.same_sku_groups.length || 0} product groups
              </span>
            </div>

            <p className="text-xs text-slate-500">
              Multiple distinct physical boxes sharing the same product SKU are valid inventory additions, not duplicate inventory records.
            </p>

            {duplicateData?.same_sku_groups.length === 0 ? (
              <div className="p-4 bg-slate-50 border border-slate-100 rounded-lg text-sm text-slate-500">
                No multi-box groups found for any SKU.
              </div>
            ) : (
              <div className="overflow-auto max-h-[400px] border border-slate-200 rounded-lg">
                <table className="w-full text-left border-collapse min-w-[700px]">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500 sticky top-0 z-10">
                      <th className="px-4 py-2.5 font-semibold">SKU</th>
                      <th className="px-4 py-2.5 font-semibold">Product Name</th>
                      <th className="px-4 py-2.5 font-semibold">Physical Box Observations</th>
                      <th className="px-4 py-2.5 font-semibold">Sample Event IDs</th>
                      <th className="px-4 py-2.5 font-semibold">First Seen</th>
                      <th className="px-4 py-2.5 font-semibold">Last Seen</th>
                      <th className="px-4 py-2.5 font-semibold">Classification</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-xs text-slate-700">
                    {duplicateData?.same_sku_groups.map((group, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/70">
                        <td className="px-4 py-2.5 font-mono text-[11px] font-bold text-slate-800">{group.sku}</td>
                        <td className="px-4 py-2.5 font-medium">{group.product_name || "Unregistered Product"}</td>
                        <td className="px-4 py-2.5">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                            {group.box_count} boxes counted
                          </span>
                        </td>
                        <td
                          className="px-4 py-2.5 font-mono text-[10px] text-slate-500 max-w-[200px] truncate"
                          title={group.sample_event_ids.join(", ")}
                        >
                          {group.sample_event_ids.map((id) => id.slice(0, 8)).join(", ")}
                          {group.sample_event_ids.length > 5 ? "..." : ""}
                        </td>
                        <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{group.first_seen}</td>
                        <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{group.last_seen}</td>
                        <td className="px-4 py-2.5">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Valid Inventory Group
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
