"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle, Clock, X, ExternalLink, Package, MessageSquare } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import Link from "next/link";

type Alert = {
  alert_id: string;
  alert_type: string;
  severity: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
  exception_count: number;
  no_qr_count: number;
  unreadable_qr_count: number;
  invalid_qr_count: number;
  window_start: string;
  window_end: string;
  created_at: string;
  updated_at: string;
  resolved_by?: string;
  resolved_at?: string;
  resolution_note?: string;
  resolution_reason?: string;
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  // Resolve dialog state
  const [isResolveDialogOpen, setIsResolveDialogOpen] = useState(false);
  const [resolveReason, setResolveReason] = useState("FALSE_ALARM");
  const [resolveNote, setResolveNote] = useState("");

  // Affected products state
  const [affectedProductsLoading, setAffectedProductsLoading] = useState(false);
  const [affectedProducts, setAffectedProducts] = useState<string[] | null>(null);

  const fetchAlerts = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth("/alerts");
      if (!res.ok) {
        throw new Error("Unable to load alerts.");
      }
      const data = await res.json();
      setAlerts(data);
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  const handleAcknowledge = async (alertId: string) => {
    setMutatingId(alertId);
    setMutationError(null);
    try {
      const res = await fetchWithAuth(`/alerts/${alertId}/acknowledge`, {
        method: "PATCH",
      });

      if (!res.ok) {
        throw new Error("Could not acknowledge the alert.");
      }

      await fetchAlerts();
      if (selectedAlert && selectedAlert.alert_id === alertId) {
        const updatedRes = await fetchWithAuth(`/alerts`);
        if (updatedRes.ok) {
           const updatedData = await updatedRes.json();
           const updatedAlert = updatedData.find((a: Alert) => a.alert_id === alertId);
           if (updatedAlert) setSelectedAlert(updatedAlert);
        }
      }
    } catch (err: any) {
      setMutationError(err.message || "An error occurred");
    } finally {
      setMutatingId(null);
    }
  };

  const submitResolve = async () => {
    if (!selectedAlert) return;
    setMutatingId(selectedAlert.alert_id);
    setMutationError(null);
    try {
      const res = await fetchWithAuth(`/alerts/${selectedAlert.alert_id}/resolve`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resolution_reason: resolveReason,
          resolution_note: resolveNote || undefined
        })
      });

      if (!res.ok) {
        throw new Error("Could not resolve the alert.");
      }

      await fetchAlerts();
      const updatedRes = await fetchWithAuth(`/alerts`);
      if (updatedRes.ok) {
         const updatedData = await updatedRes.json();
         const updatedAlert = updatedData.find((a: Alert) => a.alert_id === selectedAlert.alert_id);
         if (updatedAlert) setSelectedAlert(updatedAlert);
      }
      setIsResolveDialogOpen(false);
    } catch (err: any) {
      setMutationError(err.message || "An error occurred");
    } finally {
      setMutatingId(null);
    }
  };

  const fetchAffectedProducts = async (alert: Alert) => {
    setAffectedProductsLoading(true);
    try {
      const params = new URLSearchParams({
         start_date: alert.window_start.split("T")[0],
         end_date: new Date(new Date(alert.window_end).getTime() + 86400000).toISOString().split("T")[0]
      });
      const res = await fetchWithAuth(`/dashboard/reports?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        const skus = new Set<string>();
        const wStart = new Date(alert.window_start).getTime();
        const wEnd = new Date(alert.window_end).getTime();
        
        data.events.forEach((e: any) => {
          const ts = new Date(e.timestamp.endsWith('Z') || e.timestamp.includes('+') ? e.timestamp : `${e.timestamp}Z`).getTime();
          if (ts >= wStart && ts <= wEnd) {
             if (e.qr_status !== 'VALID_QR' && e.sku) {
               skus.add(e.sku);
             }
          }
        });
        setAffectedProducts(Array.from(skus));
      }
    } catch (err) {
      console.error(err);
      setAffectedProducts([]);
    } finally {
      setAffectedProductsLoading(false);
    }
  };

  const openDetail = (alert: Alert) => {
    setSelectedAlert(alert);
    setIsDetailOpen(true);
    setMutationError(null);
    setIsResolveDialogOpen(false);
    setAffectedProducts(null);
  };

  const closeDetail = () => {
    setIsDetailOpen(false);
    setSelectedAlert(null);
    setMutationError(null);
    setIsResolveDialogOpen(false);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200"><AlertTriangle className="w-3 h-3 mr-1" /> Open</span>;
      case "ACKNOWLEDGED":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200"><Clock className="w-3 h-3 mr-1" /> Acknowledged</span>;
      case "RESOLVED":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 border border-gray-200"><CheckCircle className="w-3 h-3 mr-1" /> Resolved</span>;
      default:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 border border-gray-200">{status}</span>;
    }
  };

  const getSeverityBadge = (severity: string) => {
    if (severity === "WARNING") {
      return <span className="text-amber-600 font-semibold text-xs tracking-wider uppercase">Warning</span>;
    }
    return <span className="text-slate-600 font-semibold text-xs tracking-wider uppercase">{severity}</span>;
  };

  const formatTime = (isoString: string | undefined) => {
    if (!isoString) return "-";
    return new Date(isoString).toLocaleString();
  };

  const openAlertsCount = alerts.filter((a) => a.status === "OPEN").length;

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Alerts</h1>
          <p className="text-sm text-slate-500 mt-1">Monitor QR-related inventory exceptions and operational anomalies.</p>
        </div>
        {!loading && (
          <div className="bg-white border border-gray-200 shadow-sm px-4 py-2 rounded-md flex items-center">
             <span className="text-sm font-medium text-slate-600 mr-2">Open alerts:</span>
             <span className={`text-lg font-bold ${openAlertsCount > 0 ? 'text-amber-600' : 'text-slate-700'}`}>{openAlertsCount}</span>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-md mb-6 border border-red-200 flex flex-col sm:flex-row items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchAlerts} className="mt-2 sm:mt-0 text-red-800 hover:text-red-900 underline text-sm font-medium">Try again</button>
        </div>
      )}

      {/* Main Table Container */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-slate-50 border-b border-gray-200 text-slate-600 font-semibold uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-4">Alert</th>
                <th className="px-6 py-4">Severity</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Exceptions</th>
                <th className="px-6 py-4">Window</th>
                <th className="px-6 py-4">Created</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 text-slate-800">
              {(() => {
                if (loading) {
                  return (
                    <tr>
                      <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                        <div className="animate-pulse flex flex-col items-center">
                          <div className="h-4 w-32 bg-slate-200 rounded mb-2"></div>
                          <div className="h-3 w-48 bg-slate-100 rounded"></div>
                        </div>
                      </td>
                    </tr>
                  );
                }

                if (alerts.length === 0) {
                  return (
                    <tr>
                      <td colSpan={7} className="px-6 py-16 text-center">
                        <div className="inline-flex flex-col items-center">
                          <Activity className="w-12 h-12 text-slate-300 mb-3" />
                          <p className="text-slate-600 font-medium">No alerts</p>
                          <p className="text-slate-400 text-sm mt-1">There are currently no QR exception alerts.</p>
                        </div>
                      </td>
                    </tr>
                  );
                }

                return alerts.map((alert) => (
                  <tr key={alert.alert_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-medium cursor-pointer" onClick={() => openDetail(alert)}>
                      {alert.alert_type === "QR_EXCEPTION_SPIKE" ? "QR Exception Spike" : alert.alert_type}
                    </td>
                    <td className="px-6 py-4">
                      {getSeverityBadge(alert.severity)}
                    </td>
                    <td className="px-6 py-4">
                      {getStatusBadge(alert.status)}
                    </td>
                    <td className="px-6 py-4 font-bold text-slate-700">
                      {alert.exception_count}
                    </td>
                    <td className="px-6 py-4 text-slate-500 text-xs">
                      {new Date(alert.window_start).toLocaleTimeString()} &rarr; {new Date(alert.window_end).toLocaleTimeString()}
                    </td>
                    <td className="px-6 py-4 text-slate-500 text-xs">
                       {formatTime(alert.created_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => openDetail(alert)}
                        className="text-blue-600 hover:text-blue-800 font-medium transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 rounded px-2 py-1"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ));
              })()}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail Modal/Drawer */}
      {isDetailOpen && selectedAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center sm:justify-end p-0 sm:p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white w-full sm:w-[450px] h-full sm:h-auto sm:max-h-[90vh] sm:rounded-lg shadow-xl overflow-hidden flex flex-col transform transition-transform">
            <div className="flex justify-between items-center p-5 border-b border-gray-200 bg-slate-50">
              <h2 className="text-lg font-bold text-slate-800">Alert Details</h2>
              <button onClick={closeDetail} aria-label="Close details" className="text-gray-400 hover:text-gray-600 cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 rounded p-1">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-5 overflow-y-auto flex-1">
               {mutationError && (
                  <div className="mb-4 p-3 text-sm text-red-700 bg-red-50 rounded border border-red-200">
                    {mutationError}
                  </div>
               )}

               <div className="space-y-4">
                  <div>
                     <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Alert Type</p>
                     <p className="font-medium text-slate-900">
                       {selectedAlert.alert_type === "QR_EXCEPTION_SPIKE" ? "QR Exception Spike" : selectedAlert.alert_type}
                     </p>
                  </div>
                  
                  {/* Why this alert? */}
                  <div className="bg-blue-50 border border-blue-100 rounded-md p-3">
                     <p className="text-xs font-semibold text-blue-800 uppercase tracking-wider mb-1 flex items-center">
                        <MessageSquare className="w-3 h-3 mr-1"/> Why this alert?
                     </p>
                     <p className="text-sm text-blue-900">
                        This alert was triggered because <b>{selectedAlert.exception_count}</b> QR exceptions (Unreadable, No QR, or Invalid) were detected between {formatTime(selectedAlert.window_start)} and {formatTime(selectedAlert.window_end)}. This exceeds the configured threshold for this time window.
                     </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-4">
                     <div>
                       <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Severity</p>
                       <div>{getSeverityBadge(selectedAlert.severity)}</div>
                     </div>
                     <div>
                       <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Status</p>
                       <div>{getStatusBadge(selectedAlert.status)}</div>
                     </div>
                  </div>

                  <div className="border-t border-slate-100 pt-4">
                     <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Exceptions Breakdown</p>
                     <div className="bg-slate-50 rounded-md p-3 border border-slate-200 space-y-2">
                        <div className="flex justify-between items-center text-sm">
                           <span className="text-slate-600">NO_QR</span>
                           <span className="font-semibold text-slate-900">{selectedAlert.no_qr_count}</span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                           <span className="text-slate-600">UNREADABLE_QR</span>
                           <span className="font-semibold text-slate-900">{selectedAlert.unreadable_qr_count}</span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                           <span className="text-slate-600">INVALID_QR</span>
                           <span className="font-semibold text-slate-900">{selectedAlert.invalid_qr_count}</span>
                        </div>
                     </div>
                  </div>

                  {/* Useful Actions */}
                  <div className="border-t border-slate-100 pt-4">
                     <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Investigation Actions</p>
                     <div className="space-y-2">
                        <Link 
                           href={`/reports?start_date=${selectedAlert.window_start.split('T')[0]}&end_date=${new Date(new Date(selectedAlert.window_end).getTime() + 86400000).toISOString().split('T')[0]}`} 
                           className="flex items-center text-sm text-blue-600 hover:text-blue-800 font-medium"
                        >
                           <ExternalLink className="w-4 h-4 mr-2"/> View Related Events (Reports)
                        </Link>
                        
                        <button 
                           onClick={() => fetchAffectedProducts(selectedAlert)}
                           className="flex items-center text-sm text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
                        >
                           <Package className="w-4 h-4 mr-2"/> View Affected Products
                        </button>
                     </div>
                     
                     {affectedProductsLoading && <p className="text-xs text-slate-500 mt-2">Loading products...</p>}
                     
                     {affectedProducts && (
                        <div className="mt-2 bg-slate-50 p-2 rounded border border-slate-200">
                           <p className="text-xs font-semibold text-slate-700 mb-1">SKUs with exceptions in this window:</p>
                           {affectedProducts.length > 0 ? (
                              <ul className="list-disc list-inside text-sm text-slate-600">
                                 {affectedProducts.map(sku => <li key={sku}>{sku}</li>)}
                              </ul>
                           ) : (
                              <p className="text-sm text-slate-500">No specific SKUs could be extracted (they might be unknown/unreadable).</p>
                           )}
                        </div>
                     )}
                  </div>

                  {/* Resolution Info */}
                  {selectedAlert.status === "RESOLVED" && (
                     <div className="border-t border-slate-100 pt-4 bg-emerald-50 p-3 rounded-md">
                        <p className="text-xs font-semibold text-emerald-800 uppercase tracking-wider mb-2">Resolution Details</p>
                        <div className="space-y-1 text-sm text-emerald-900">
                           <p><b>Resolved By:</b> {selectedAlert.resolved_by || 'System'}</p>
                           <p><b>Resolved At:</b> {formatTime(selectedAlert.resolved_at)}</p>
                           <p><b>Reason:</b> {selectedAlert.resolution_reason || 'N/A'}</p>
                           {selectedAlert.resolution_note && (
                              <p><b>Note:</b> {selectedAlert.resolution_note}</p>
                           )}
                        </div>
                     </div>
                  )}

                  <div className="border-t border-slate-100 pt-4 space-y-3">
                     <div>
                       <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Alert ID</p>
                       <p className="text-xs font-mono text-slate-500 break-all">{selectedAlert.alert_id}</p>
                     </div>
                  </div>
               </div>
               
               {/* Resolve Dialog Inline */}
               {isResolveDialogOpen && (
                  <div className="mt-4 border border-blue-200 bg-blue-50 p-4 rounded-md">
                     <h3 className="text-sm font-bold text-blue-900 mb-3">Resolve Alert</h3>
                     <div className="space-y-3">
                        <div>
                           <label className="block text-xs font-medium text-blue-800 mb-1">Reason</label>
                           <select 
                              value={resolveReason}
                              onChange={(e) => setResolveReason(e.target.value)}
                              className="w-full p-2 text-sm border border-blue-200 rounded focus:ring-blue-500"
                           >
                              <option value="FALSE_ALARM">False Alarm / Glitch</option>
                              <option value="FIXED_CAMERA">Camera/Lighting Adjusted</option>
                              <option value="REPRINTED_LABELS">Labels Reprinted/Fixed</option>
                              <option value="OTHER">Other</option>
                           </select>
                        </div>
                        <div>
                           <label className="block text-xs font-medium text-blue-800 mb-1">Note (Optional)</label>
                           <textarea 
                              value={resolveNote}
                              onChange={(e) => setResolveNote(e.target.value)}
                              placeholder="Add details..."
                              className="w-full p-2 text-sm border border-blue-200 rounded focus:ring-blue-500 h-20"
                           ></textarea>
                        </div>
                        <div className="flex justify-end space-x-2 pt-2">
                           <button 
                              onClick={() => setIsResolveDialogOpen(false)}
                              className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-gray-300 rounded hover:bg-gray-50"
                           >
                              Cancel
                           </button>
                           <button 
                              onClick={submitResolve}
                              disabled={mutatingId === selectedAlert.alert_id}
                              className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
                           >
                              {mutatingId === selectedAlert.alert_id ? "Saving..." : "Confirm Resolve"}
                           </button>
                        </div>
                     </div>
                  </div>
               )}
            </div>

            <div className="p-4 border-t border-gray-200 bg-slate-50 flex justify-end space-x-3">
              {selectedAlert.status === "OPEN" && (
                <button
                  onClick={() => handleAcknowledge(selectedAlert.alert_id)}
                  disabled={mutatingId === selectedAlert.alert_id || isResolveDialogOpen}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 disabled:opacity-50"
                >
                  {mutatingId === selectedAlert.alert_id ? "Loading..." : "Acknowledge"}
                </button>
              )}
              
              {(selectedAlert.status === "OPEN" || selectedAlert.status === "ACKNOWLEDGED") && !isResolveDialogOpen && (
                <button
                  onClick={() => setIsResolveDialogOpen(true)}
                  disabled={mutatingId === selectedAlert.alert_id}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 transition-colors shadow-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:bg-blue-400"
                >
                  Resolve Alert
                </button>
              )}
              
              {(!isResolveDialogOpen) && (
                <button
                  onClick={closeDetail}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2"
                >
                  Close
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
