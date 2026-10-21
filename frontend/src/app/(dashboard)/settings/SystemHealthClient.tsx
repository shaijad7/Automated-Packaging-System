"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { API_BASE_URL, fetchWithAuth } from "@/lib/api";
import { Server, Database, Camera, BrainCircuit, Activity, RefreshCw } from "lucide-react";

type HealthStatus = "UP" | "DOWN" | "DEGRADED" | "UNKNOWN" | "CHECKING";

interface SystemHealthClientProps {
  cameraSource: string;
  modelPath: string;
}

interface StatusIndicatorProps {
  status: HealthStatus;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  detail: string;
  reason?: string;
  lastChecked?: string | null;
}

function StatusIndicator({
  status,
  label,
  icon: Icon,
  detail,
  reason,
  lastChecked,
}: StatusIndicatorProps) {
  const getBadgeStyle = (s: HealthStatus) => {
    switch (s) {
      case "UP":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "DOWN":
        return "bg-red-50 text-red-700 border-red-200";
      case "DEGRADED":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "UNKNOWN":
        return "bg-slate-100 text-slate-700 border-slate-300";
      case "CHECKING":
        return "bg-blue-50 text-blue-700 border-blue-200";
    }
  };

  const getIconStyle = (s: HealthStatus) => {
    switch (s) {
      case "UP":
        return "bg-emerald-100 text-emerald-600";
      case "DOWN":
        return "bg-red-100 text-red-600";
      case "DEGRADED":
        return "bg-amber-100 text-amber-600";
      case "UNKNOWN":
        return "bg-slate-100 text-slate-500";
      case "CHECKING":
        return "bg-blue-100 text-blue-600";
    }
  };

  return (
    <div className="flex flex-col justify-between p-4 bg-white border border-slate-200 rounded-lg shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`p-2.5 rounded-lg shrink-0 mt-0.5 ${getIconStyle(status)}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-800">{label}</p>
            <p className="text-xs text-slate-600 mt-0.5">{detail}</p>
            {reason && (
              <p className="text-[11px] text-slate-400 mt-1 italic">{reason}</p>
            )}
          </div>
        </div>
        <div
          className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border shrink-0 ${getBadgeStyle(
            status
          )}`}
        >
          {status}
        </div>
      </div>
      {lastChecked && (
        <div className="mt-3 pt-2 border-t border-slate-100 text-[10px] text-slate-400 flex justify-between">
          <span>Observed via live health probe</span>
          <span>Checked: {lastChecked}</span>
        </div>
      )}
    </div>
  );
}

export default function SystemHealthClient({ cameraSource, modelPath }: SystemHealthClientProps) {
  const [backendStatus, setBackendStatus] = useState<HealthStatus>("CHECKING");
  const [backendDetail, setBackendDetail] = useState<string>("Checking connectivity...");
  const [mongoStatus, setMongoStatus] = useState<HealthStatus>("CHECKING");
  const [mongoDetail, setMongoDetail] = useState<string>("Checking database status...");

  const [cameraStatus, setCameraStatus] = useState<HealthStatus>("CHECKING");
  const [cameraDetail, setCameraDetail] = useState<string>(`Source: ${cameraSource}`);
  const [cameraReason, setCameraReason] = useState<string | undefined>("Awaiting edge telemetry...");

  const [modelStatus, setModelStatus] = useState<HealthStatus>("CHECKING");
  const [modelDetail, setModelDetail] = useState<string>(`Model: ${modelPath}`);
  const [modelReason, setModelReason] = useState<string | undefined>("Awaiting edge telemetry...");

  const [lastChecked, setLastChecked] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const abortControllerRef = useRef<AbortController | null>(null);

  const checkHealth = useCallback(async () => {
    // Abort any ongoing check
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    // 1. Probe Backend API and MongoDB
    try {
      const res = await fetch(`${API_BASE_URL}/health`, {
        signal: controller.signal,
        cache: "no-store",
      });

      const now = new Date().toLocaleTimeString();
      setLastChecked(now);

      if (res.status === 200) {
        setBackendStatus("UP");
        setBackendDetail("Responding to requests (HTTP 200)");

        try {
          const data = await res.json();
          if (data.database === "connected") {
            setMongoStatus("UP");
            setMongoDetail("Connected and responding to ping");
          } else {
            setMongoStatus("DOWN");
            setMongoDetail("Database reporting disconnected");
          }
        } catch {
          setMongoStatus("UNKNOWN");
          setMongoDetail("Unable to parse database response");
        }
      } else if (res.status === 503) {
        setBackendStatus("UP");
        setBackendDetail("Responding to requests (HTTP 503)");
        setMongoStatus("DOWN");
        setMongoDetail("Database connection failed or disconnected");
      } else {
        setBackendStatus("DEGRADED");
        setBackendDetail(`Unexpected response status (HTTP ${res.status})`);
        setMongoStatus("UNKNOWN");
        setMongoDetail("Cannot verify database status");
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      const now = new Date().toLocaleTimeString();
      setLastChecked(now);
      setBackendStatus("DOWN");
      setBackendDetail("Unreachable — connection refused or network failure");
      setMongoStatus("UNKNOWN");
      setMongoDetail("Cannot verify database — backend API is unreachable");
    }

    // 2. Probe Edge Node Telemetry (ADMIN Protected)
    try {
      const edgeRes = await fetchWithAuth("/dashboard/system-health", {
        signal: controller.signal,
        cache: "no-store",
      });

      if (edgeRes.ok) {
        const edgeData = await edgeRes.json();
        const reportedCam = edgeData.camera_status as HealthStatus;
        const reportedModel = edgeData.model_status as HealthStatus;
        const isStale = Boolean(edgeData.is_stale);

        // Update Camera State
        setCameraStatus(reportedCam);
        if (edgeData.camera_details) {
          setCameraDetail(edgeData.camera_details);
        } else {
          setCameraDetail(`Source: ${cameraSource}`);
        }

        if (isStale) {
          setCameraReason(edgeData.camera_details || "Edge heartbeat expired");
        } else if (reportedCam === "UNKNOWN") {
          setCameraReason("No telemetry received — CV process offline or awaiting frame");
        } else if (reportedCam === "DOWN") {
          setCameraReason(edgeData.camera_details || "Camera acquisition offline");
        } else {
          setCameraReason(undefined);
        }

        // Update AI Model State
        setModelStatus(reportedModel);
        if (edgeData.model_details) {
          setModelDetail(edgeData.model_details);
        } else {
          setModelDetail(`Model: ${modelPath}`);
        }

        if (isStale) {
          setModelReason(edgeData.model_details || "Edge heartbeat expired");
        } else if (reportedModel === "UNKNOWN") {
          setModelReason("No inference telemetry received — CV process offline");
        } else if (reportedModel === "DOWN") {
          setModelReason(edgeData.model_details || "Model inference offline");
        } else {
          setModelReason(undefined);
        }
      } else if (edgeRes.status === 401 || edgeRes.status === 403) {
        setCameraStatus("UNKNOWN");
        setCameraDetail(`Source: ${cameraSource}`);
        setCameraReason("Admin authorization required to view live edge telemetry");

        setModelStatus("UNKNOWN");
        setModelDetail(`Model: ${modelPath}`);
        setModelReason("Admin authorization required to view live edge telemetry");
      } else {
        setCameraStatus("DOWN");
        setCameraDetail(`Source: ${cameraSource}`);
        setCameraReason(`Telemetry probe error (HTTP ${edgeRes.status})`);

        setModelStatus("DOWN");
        setModelDetail(`Model: ${modelPath}`);
        setModelReason(`Telemetry probe error (HTTP ${edgeRes.status})`);
      }
    } catch (edgeErr: unknown) {
      if (edgeErr instanceof Error && edgeErr.name === "AbortError") {
        return;
      }
      setCameraStatus("DOWN");
      setCameraDetail(`Source: ${cameraSource}`);
      setCameraReason("Cannot contact edge telemetry endpoint — connection failure");

      setModelStatus("DOWN");
      setModelDetail(`Model: ${modelPath}`);
      setModelReason("Cannot contact edge telemetry endpoint — connection failure");
    } finally {
      const now = new Date().toLocaleTimeString();
      setLastChecked(now);
    }
  }, [cameraSource, modelPath]);

  const handleManualRefresh = () => {
    setIsRefreshing(true);
    checkHealth().finally(() => setIsRefreshing(false));
  };

  useEffect(() => {
    const probe = async () => {
      await checkHealth();
    };
    void probe();
    const interval = setInterval(() => {
      void probe();
    }, 15000);

    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [checkHealth]);

  return (
    <div className="bg-slate-50 border border-gray-200 rounded-lg shadow-sm overflow-hidden mb-6">
      <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between font-medium text-slate-800">
        <div className="flex items-center">
          <Activity className="w-4 h-4 mr-2 text-slate-500" />
          <span>System Status</span>
        </div>
        <button
          onClick={handleManualRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors disabled:opacity-50 cursor-pointer"
          title="Refresh system health status"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-blue-600" : "text-slate-500"}`} />
          Refresh
        </button>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 1. Backend API */}
        <StatusIndicator
          status={backendStatus}
          label="Backend API"
          icon={Server}
          detail={backendDetail}
          lastChecked={lastChecked}
        />

        {/* 2. MongoDB */}
        <StatusIndicator
          status={mongoStatus}
          label="MongoDB"
          icon={Database}
          detail={mongoDetail}
          lastChecked={lastChecked}
        />

        {/* 3. Camera Stream */}
        <StatusIndicator
          status={cameraStatus}
          label="Camera Stream"
          icon={Camera}
          detail={cameraDetail}
          reason={cameraReason}
          lastChecked={lastChecked}
        />

        {/* 4. AI Model */}
        <StatusIndicator
          status={modelStatus}
          label="AI Model"
          icon={BrainCircuit}
          detail={modelDetail}
          reason={modelReason}
          lastChecked={lastChecked}
        />
      </div>
    </div>
  );
}
