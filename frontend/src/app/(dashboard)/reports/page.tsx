"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchWithAuth, getAuthToken } from "@/lib/api";
import { Box, CheckCircle, AlertTriangle, PackagePlus, AlertCircle, Download, Search, X } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

interface Summary {
  overall_boxes: number;
  valid_qr: number;
  no_qr: number;
  unreadable_qr: number;
  invalid_qr: number;
  qr_exceptions: number;
  inventory_added: number;
}

interface EventItem {
  event_id: string;
  timestamp: string;
  track_id: number;
  qr_status: string;
  qr_payload?: string;
  count_direction: string;
  sku?: string;
  status: string;
}

interface ReportData {
  summary: Summary;
  events: EventItem[];
}

export default function ReportsPage() {
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // Filters
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [qrStatus, setQrStatus] = useState("ALL");
  const [sku, setSku] = useState("");
  
  // Track active filters for rendering
  const [activeFilters, setActiveFilters] = useState({
    start_date: "",
    end_date: "",
    qr_status: "ALL",
    sku: ""
  });

  const loadReport = useCallback(async (filters = activeFilters) => {
    try {
      setLoading(true);
      setError(null);
      setExportError(null);
      
      const params = new URLSearchParams();
      if (filters.start_date) params.append("start_date", filters.start_date);
      if (filters.end_date) params.append("end_date", filters.end_date);
      if (filters.qr_status && filters.qr_status !== "ALL") params.append("qr_status", filters.qr_status);
      if (filters.sku) params.append("sku", filters.sku);

      const res = await fetchWithAuth(`/dashboard/reports?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Failed to load reports");
      }
      
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  }, [activeFilters]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const handleApplyFilters = () => {
    const newFilters = { start_date: startDate, end_date: endDate, qr_status: qrStatus, sku: sku };
    setActiveFilters(newFilters);
  };

  const handleClearFilters = () => {
    setStartDate("");
    setEndDate("");
    setQrStatus("ALL");
    setSku("");
    setActiveFilters({ start_date: "", end_date: "", qr_status: "ALL", sku: "" });
  };

  const handleExportCSV = async () => {
    try {
      setExportLoading(true);
      setExportError(null);
      
      const params = new URLSearchParams();
      if (activeFilters.start_date) params.append("start_date", activeFilters.start_date);
      if (activeFilters.end_date) params.append("end_date", activeFilters.end_date);
      if (activeFilters.qr_status && activeFilters.qr_status !== "ALL") params.append("qr_status", activeFilters.qr_status);
      if (activeFilters.sku) params.append("sku", activeFilters.sku);

      const token = getAuthToken();
      const res = await fetch(`${API_BASE_URL}/dashboard/reports/export.csv?${params.toString()}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!res.ok) {
        throw new Error("Failed to export CSV");
      }
      
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      
      // Get filename from header if possible
      let filename = `inventory-report-${new Date().toISOString().split('T')[0]}.csv`;
      const disposition = res.headers.get('content-disposition');
      if (disposition && disposition.indexOf('attachment') !== -1) {
        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
        const matches = filenameRegex.exec(disposition);
        if (matches != null && matches[1]) { 
          filename = matches[1].replace(/['"]/g, '');
        }
      }
      
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setExportError(err.message || "Failed to export CSV");
    } finally {
      setExportLoading(false);
    }
  };

  const handleExportPDF = async () => {
    try {
      setPdfLoading(true);
      setExportError(null);
      
      const params = new URLSearchParams();
      if (activeFilters.start_date) params.append("start_date", activeFilters.start_date);
      if (activeFilters.end_date) params.append("end_date", activeFilters.end_date);
      if (activeFilters.qr_status && activeFilters.qr_status !== "ALL") params.append("qr_status", activeFilters.qr_status);
      if (activeFilters.sku) params.append("sku", activeFilters.sku);

      const token = getAuthToken();
      const res = await fetch(`${API_BASE_URL}/dashboard/reports/export.pdf?${params.toString()}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!res.ok) {
        throw new Error("Failed to export PDF");
      }
      
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      
      let filename = `inventory-report-${new Date().toISOString().split('T')[0]}.pdf`;
      const disposition = res.headers.get('content-disposition');
      if (disposition && disposition.indexOf('attachment') !== -1) {
        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
        const matches = filenameRegex.exec(disposition);
        if (matches != null && matches[1]) { 
          filename = matches[1].replace(/['"]/g, '');
        }
      }
      
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setExportError(err.message || "Failed to export PDF");
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Reports</h2>
        <p className="text-slate-500 mt-1">Inventory processing and QR validation history.</p>
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
        <div className="flex flex-col md:flex-row flex-wrap gap-4 items-stretch md:items-end">
          <div className="flex-1 min-w-[150px]">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">From Date</label>
            <input 
              type="date" 
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
            />
          </div>
          <div className="flex-1 min-w-[150px]">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">To Date</label>
            <input 
              type="date" 
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
            />
          </div>
          <div className="flex-1 min-w-[150px]">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">QR Status</label>
            <select 
              value={qrStatus}
              onChange={(e) => setQrStatus(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer bg-white"
            >
              <option value="ALL">All</option>
              <option value="VALID_QR">Valid QR</option>
              <option value="NO_QR">No QR</option>
              <option value="UNREADABLE_QR">Unreadable QR</option>
              <option value="INVALID_QR">Invalid QR</option>
            </select>
          </div>
          <div className="flex-1 min-w-[150px]">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">SKU</label>
            <input 
              type="text" 
              placeholder="e.g. ADP-001"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <div className="flex flex-wrap gap-2 w-full lg:w-auto mt-2 md:mt-0">
            <button 
              onClick={handleApplyFilters}
              className="flex-1 md:flex-none flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer disabled:opacity-50"
              disabled={loading}
            >
              <Search className="w-4 h-4 mr-2" />
              Apply Filters
            </button>
            <button 
              onClick={handleClearFilters}
              className="flex-1 md:flex-none flex items-center justify-center bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded text-sm font-medium border border-slate-300 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-500 cursor-pointer disabled:opacity-50"
              disabled={loading}
            >
              <X className="w-4 h-4 mr-2" />
              Clear
            </button>
            <button 
              onClick={handleExportCSV}
              disabled={exportLoading || pdfLoading || loading || !data}
              className="flex-1 md:flex-none flex items-center justify-center bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download className="w-4 h-4 mr-2" />
              {exportLoading ? "Exporting..." : "Export CSV"}
            </button>
            <button 
              onClick={handleExportPDF}
              disabled={pdfLoading || exportLoading || loading || !data}
              className="flex-1 md:flex-none flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download className="w-4 h-4 mr-2" />
              {pdfLoading ? "Generating..." : "Export PDF"}
            </button>
          </div>
        </div>
        {exportError && (
          <div className="mt-3 text-sm text-red-600 flex items-center">
            <AlertCircle className="w-4 h-4 mr-1" />
            {exportError}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex py-20 items-center justify-center bg-white rounded-lg border border-slate-200 shadow-sm">
          <div className="text-slate-500 font-medium animate-pulse">Loading Report...</div>
        </div>
      ) : error ? (
        <div className="bg-red-50 text-red-600 p-4 rounded-md flex items-center border border-red-200">
          <AlertCircle className="w-5 h-5 mr-2" />
          {error}
        </div>
      ) : data ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-500 text-sm font-medium">Overall Boxes</span>
                <Box className="text-blue-500 w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800">{data.summary.overall_boxes}</span>
            </div>
            
            <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-500 text-sm font-medium">Valid QR</span>
                <CheckCircle className="text-emerald-500 w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800">{data.summary.valid_qr}</span>
            </div>

            <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-500 text-sm font-medium">QR Exceptions</span>
                <AlertTriangle className="text-amber-500 w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800">{data.summary.qr_exceptions}</span>
            </div>

            <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-500 text-sm font-medium">Inventory Added</span>
                <PackagePlus className="text-indigo-500 w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800">{data.summary.inventory_added}</span>
            </div>
          </div>

          {/* Events Table */}
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
              <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Filtered Events (Max 500)</h3>
              <span className="text-xs text-slate-500">Showing {data.events.length} records</span>
            </div>
            <div className="p-0 overflow-auto max-h-[600px]">
              {data.events.length === 0 ? (
                <div className="p-12 text-center text-slate-500 text-sm bg-white">
                  No records match your filters.
                </div>
              ) : (
                <table className="w-full min-w-[800px] text-left border-collapse">
                  <thead>
                    <tr className="bg-white border-b border-slate-200 text-xs uppercase text-slate-500 sticky top-0 z-10 shadow-sm">
                      <th className="px-4 py-3 font-semibold whitespace-nowrap">Time</th>
                      <th className="px-4 py-3 font-semibold">Track ID</th>
                      <th className="px-4 py-3 font-semibold">QR Status</th>
                      <th className="px-4 py-3 font-semibold">QR Payload</th>
                      <th className="px-4 py-3 font-semibold">SKU</th>
                      <th className="px-4 py-3 font-semibold">Direction</th>
                      <th className="px-4 py-3 font-semibold">Inventory</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-sm text-slate-700 bg-white">
                    {data.events.map((evt, idx) => {
                      const ts = evt.timestamp.endsWith('Z') || evt.timestamp.includes('+') ? evt.timestamp : `${evt.timestamp}Z`;
                      const time = new Date(ts).toLocaleString();
                      
                      return (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{time}</td>
                          <td className="px-4 py-3 font-mono text-xs">{evt.track_id}</td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`px-2 py-1 text-[10px] font-bold uppercase rounded ${
                              evt.qr_status === 'VALID_QR' ? 'bg-emerald-100 text-emerald-700' :
                              evt.qr_status === 'INVALID_QR' ? 'bg-red-100 text-red-700' :
                              'bg-amber-100 text-amber-700'
                            }`}>
                              {evt.qr_status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-500 font-mono truncate max-w-[150px]" title={evt.qr_payload || "-"}>
                            {evt.qr_payload || "-"}
                          </td>
                          <td className="px-4 py-3 text-xs font-mono font-medium text-slate-700">
                            {evt.sku || "-"}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-500">
                            {evt.count_direction}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`text-xs font-medium ${
                              evt.status === 'SUCCESS' ? 'text-emerald-600' : 'text-slate-500'
                            }`}>
                              {evt.status === 'SUCCESS' ? 'SUCCESS / +1' : `${evt.status} / 0`}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
