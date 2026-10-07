"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import { Box, CheckCircle, AlertTriangle, PackagePlus, AlertCircle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar } from "recharts";

interface Summary {
  overall_boxes: number;
  valid_qr: number;
  no_qr: number;
  unreadable_qr: number;
  invalid_qr: number;
  qr_exceptions: number;
  inventory_added: number;
}

interface InventoryItem {
  sku: string;
  quantity: number;
  product_name?: string;
  is_active?: boolean;
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

interface AnalyticsData {
  trend: { time: string; overall_boxes: number; valid_qr: number; exceptions: number }[];
  distribution: { name: string; value: number }[];
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d" | "all">("all");
  const [analyticsLoading, setAnalyticsLoading] = useState(true);

  const fetchDashboard = async (isBackground = false) => {
    try {
      if (!isBackground) {
        setLoading(true);
        setError(null);
      }
      const [sumRes, invRes, evtRes] = await Promise.all([
        fetchWithAuth("/dashboard/summary"),
        fetchWithAuth("/dashboard/inventory"),
        fetchWithAuth("/dashboard/events")
      ]);
      if (!sumRes.ok || !invRes.ok || !evtRes.ok) throw new Error("Failed to load dashboard data");
      setSummary(await sumRes.json());
      setInventory(await invRes.json());
      setEvents(await evtRes.json());
    } catch (err: any) {
      if (!isBackground) setError(err.message || "An error occurred");
      else console.error("Background refresh failed", err);
    } finally {
      if (!isBackground) setLoading(false);
    }
  };

  const fetchAnalytics = async (range: string, isBackground = false) => {
    try {
      if (!isBackground) setAnalyticsLoading(true);
      const res = await fetchWithAuth(`/dashboard/analytics?range=${range}`);
      if (!res.ok) throw new Error("Failed to load analytics");
      setAnalytics(await res.json());
    } catch (err: any) {
      console.error(err);
    } finally {
      if (!isBackground) setAnalyticsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  useEffect(() => {
    fetchAnalytics(timeRange);
  }, [timeRange]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchDashboard(true);
      fetchAnalytics(timeRange, true);
    }, 10000);
    return () => clearInterval(interval);
  }, [timeRange]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-slate-500 font-medium animate-pulse">Loading Dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="bg-red-50 text-red-600 p-4 rounded-md flex items-center border border-red-200">
          <AlertCircle className="w-5 h-5 mr-2" />
          {error}
        </div>
      </div>
    );
  }

  if (!summary) return null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Overview</h2>
        <p className="text-slate-500 mt-1">Real-time inventory and event processing status.</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-sm font-medium">Overall Boxes</span>
            <Box className="text-blue-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">{summary.overall_boxes}</span>
          <span className="text-xs text-slate-400 mt-2">All boxes crossed line</span>
        </div>
        
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-sm font-medium">Valid QR</span>
            <CheckCircle className="text-emerald-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">{summary.valid_qr}</span>
          <span className="text-xs text-slate-400 mt-2">Successfully validated</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-sm font-medium">QR Exceptions</span>
            <AlertTriangle className="text-amber-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">{summary.qr_exceptions}</span>
          <span className="text-xs text-slate-400 mt-2">NO_QR, UNREADABLE, INVALID</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 text-sm font-medium">Inventory Added</span>
            <PackagePlus className="text-indigo-500 w-5 h-5" />
          </div>
          <span className="text-3xl font-bold text-slate-800">{summary.inventory_added}</span>
          <span className="text-xs text-slate-400 mt-2">Accepted additions</span>
        </div>
      </div>

      {/* Exception Breakdown */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">Exception Breakdown</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="flex justify-between items-center bg-slate-50 p-3 rounded border border-slate-100">
            <span className="text-sm text-slate-600 font-medium">VALID_QR</span>
            <span className="text-sm font-bold text-emerald-600">{summary.valid_qr}</span>
          </div>
          <div className="flex justify-between items-center bg-slate-50 p-3 rounded border border-slate-100">
            <span className="text-sm text-slate-600 font-medium">NO_QR</span>
            <span className="text-sm font-bold text-amber-600">{summary.no_qr}</span>
          </div>
          <div className="flex justify-between items-center bg-slate-50 p-3 rounded border border-slate-100">
            <span className="text-sm text-slate-600 font-medium">UNREADABLE</span>
            <span className="text-sm font-bold text-amber-600">{summary.unreadable_qr}</span>
          </div>
          <div className="flex justify-between items-center bg-slate-50 p-3 rounded border border-slate-100">
            <span className="text-sm text-slate-600 font-medium">INVALID_QR</span>
            <span className="text-sm font-bold text-red-600">{summary.invalid_qr}</span>
          </div>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mt-8 mb-4 gap-4 sm:gap-0">
        <h3 className="text-lg font-bold text-slate-800">Analytics</h3>
        <select 
          value={timeRange} 
          onChange={(e) => setTimeRange(e.target.value as any)}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer text-slate-700 bg-white"
        >
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="all">All time</option>
        </select>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Processing Trend */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 flex flex-col h-[350px]">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">Processing Trend</h3>
          <div className="flex-1 min-h-0 relative">
            {analyticsLoading ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">Loading...</div>
            ) : analytics?.trend.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">No events in this period</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analytics?.trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis 
                    dataKey="time" 
                    tickFormatter={(val: unknown) => {
                      if (typeof val !== 'string' && typeof val !== 'number') return "";
                      const strVal = String(val);
                      const isHourly = strVal.includes(":");
                      const ts = isHourly ? `${strVal.replace(" ", "T")}Z` : strVal;
                      if (isHourly) {
                        return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                      }
                      return new Date(ts).toLocaleDateString();
                    }}
                    tick={{ fontSize: 10, fill: '#64748b' }} 
                    axisLine={false} 
                    tickLine={false} 
                  />
                  <YAxis tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <RechartsTooltip 
                    contentStyle={{ borderRadius: '6px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)' }} 
                    itemStyle={{ fontSize: '12px' }} 
                    labelStyle={{ fontSize: '12px', color: '#64748b', marginBottom: '4px' }} 
                    labelFormatter={(val: unknown) => {
                      if (typeof val !== 'string' && typeof val !== 'number') return "";
                      const strVal = String(val);
                      const isHourly = strVal.includes(":");
                      const ts = isHourly ? `${strVal.replace(" ", "T")}Z` : strVal;
                      if (isHourly) {
                        return new Date(ts).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
                      }
                      return new Date(ts).toLocaleDateString();
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} iconType="circle" />
                  <Line type="monotone" dataKey="overall_boxes" name="Overall" stroke="#3b82f6" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                  <Line type="monotone" dataKey="valid_qr" name="Valid" stroke="#10b981" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="exceptions" name="Exceptions" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* QR Status Distribution */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 flex flex-col h-[350px]">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">QR Status Distribution</h3>
          <div className="flex-1 min-h-0 relative">
            {analyticsLoading ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">Loading...</div>
            ) : analytics?.distribution.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">No data in this period</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={analytics?.distribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {analytics?.distribution.map((entry, index) => {
                      let color = '#3b82f6';
                      if (entry.name === 'VALID_QR') color = '#10b981';
                      if (entry.name === 'NO_QR') color = '#f59e0b';
                      if (entry.name === 'UNREADABLE_QR') color = '#fbbf24';
                      if (entry.name === 'INVALID_QR') color = '#ef4444';
                      return <Cell key={`cell-${index}`} fill={color} />;
                    })}
                  </Pie>
                  <RechartsTooltip contentStyle={{ borderRadius: '6px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)' }} itemStyle={{ fontSize: '12px' }} />
                  <Legend wrapperStyle={{ fontSize: '12px' }} iconType="circle" />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        {/* Inventory by Product */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 flex flex-col h-[350px]">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">Inventory by Product</h3>
          <div className="flex-1 min-h-0 relative">
            {inventory.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">No inventory records found</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={inventory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="sku" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <RechartsTooltip contentStyle={{ borderRadius: '6px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)' }} cursor={{fill: '#f8fafc'}} />
                  <Bar dataKey="quantity" name="Quantity" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={50} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
        {/* Inventory Table */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-200 bg-slate-50">
            <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Current Inventory</h3>
          </div>
          <div className="flex-1 p-0 overflow-auto max-h-[400px]">
            {inventory.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No inventory records found.</div>
            ) : (
              <table className="w-full min-w-[500px] text-left border-collapse">
                <thead>
                  <tr className="bg-white border-b border-slate-200 text-xs uppercase text-slate-500 sticky top-0 z-10 shadow-sm">
                    <th className="px-4 py-3 font-semibold">Product</th>
                    <th className="px-4 py-3 font-semibold">SKU</th>
                    <th className="px-4 py-3 font-semibold">Quantity</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm text-slate-700">
                  {inventory.map((item, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-900">{item.product_name || "Unknown"}</td>
                      <td className="px-4 py-3 text-slate-500 font-mono text-xs">{item.sku}</td>
                      <td className="px-4 py-3 font-bold">{item.quantity}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${item.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                          {item.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Events Table */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-200 bg-slate-50">
            <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Recent Events</h3>
          </div>
          <div className="flex-1 p-0 overflow-auto max-h-[400px]">
            {events.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No recent events found.</div>
            ) : (
              <table className="w-full min-w-[600px] text-left border-collapse">
                <thead>
                  <tr className="bg-white border-b border-slate-200 text-xs uppercase text-slate-500 sticky top-0 z-10 shadow-sm">
                    <th className="px-4 py-3 font-semibold">Time</th>
                    <th className="px-4 py-3 font-semibold">Track ID</th>
                    <th className="px-4 py-3 font-semibold">QR Status</th>
                    <th className="px-4 py-3 font-semibold">QR/SKU</th>
                    <th className="px-4 py-3 font-semibold">Inventory Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm text-slate-700">
                  {events.map((evt, idx) => {
                    const ts = evt.timestamp.endsWith('Z') || evt.timestamp.includes('+') ? evt.timestamp : `${evt.timestamp}Z`;
                    const time = new Date(ts).toLocaleTimeString();
                    
                    let qrDisplay = "-";
                    if (evt.qr_status === "VALID_QR") {
                      qrDisplay = evt.sku || evt.qr_payload || "-";
                    } else if (evt.qr_status === "INVALID_QR") {
                      qrDisplay = evt.qr_payload || "-";
                    }

                    return (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{time}</td>
                        <td className="px-4 py-3 font-mono text-xs">{evt.track_id}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 text-[10px] font-bold uppercase rounded ${
                            evt.qr_status === 'VALID_QR' ? 'bg-emerald-100 text-emerald-700' :
                            evt.qr_status === 'INVALID_QR' ? 'bg-red-100 text-red-700' :
                            'bg-amber-100 text-amber-700'
                          }`}>
                            {evt.qr_status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500 font-mono truncate max-w-[150px]" title={qrDisplay}>
                          {qrDisplay}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs font-medium ${
                            evt.status === 'SUCCESS' ? 'text-emerald-600' : 'text-slate-500'
                          }`}>
                            {evt.status === 'SUCCESS' ? '+1 / Accepted' : '0 / Not added'}
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
      </div>
    </div>
  );
}
