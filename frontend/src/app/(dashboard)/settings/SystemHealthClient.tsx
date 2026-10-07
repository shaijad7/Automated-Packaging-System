"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import { Server, Database, Camera, BrainCircuit, Activity } from "lucide-react";

interface SystemHealthClientProps {
  cameraConfigured: boolean;
  modelConfigured: boolean;
  cameraSource: string;
}

export default function SystemHealthClient({ cameraConfigured, modelConfigured, cameraSource }: SystemHealthClientProps) {
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [mongoUp, setMongoUp] = useState<boolean | null>(null);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/health`);
        if (res.ok) {
          const data = await res.json();
          setBackendUp(true);
          setMongoUp(data.database === "connected");
        } else {
          setBackendUp(false);
          setMongoUp(false);
        }
      } catch (err) {
        setBackendUp(false);
        setMongoUp(false);
      }
    };
    checkHealth();
  }, []);

  const StatusIndicator = ({ up, label, icon: Icon, detail }: any) => (
    <div className="flex items-center justify-between p-3 bg-white border border-slate-200 rounded-lg shadow-sm">
      <div className="flex items-center">
        <div className={`p-2 rounded-full mr-3 ${up === true ? 'bg-emerald-100 text-emerald-600' : up === false ? 'bg-red-100 text-red-600' : 'bg-slate-100 text-slate-500'}`}>
          <Icon className="w-4 h-4" />
        </div>
        <div>
          <p className="text-sm font-medium text-slate-800">{label}</p>
          {detail && <p className="text-xs text-slate-500">{detail}</p>}
        </div>
      </div>
      <div className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${
        up === true ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 
        up === false ? 'bg-red-50 text-red-700 border border-red-200' : 
        'bg-slate-50 text-slate-600 border border-slate-200'
      }`}>
        {up === true ? 'UP' : up === false ? 'DOWN' : 'CHECKING'}
      </div>
    </div>
  );

  return (
    <div className="bg-slate-50 border border-gray-200 rounded-lg shadow-sm overflow-hidden mb-6">
      <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center font-medium text-slate-800">
        <Activity className="w-4 h-4 mr-2 text-slate-500" />
        System Status
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatusIndicator 
          up={backendUp} 
          label="Backend API" 
          icon={Server} 
          detail={backendUp ? "Connected" : "Disconnected"}
        />
        <StatusIndicator 
          up={mongoUp} 
          label="MongoDB" 
          icon={Database} 
          detail={mongoUp ? "Connected" : "Disconnected"}
        />
        <StatusIndicator 
          up={cameraConfigured} 
          label="Camera Stream" 
          icon={Camera} 
          detail={cameraSource.startsWith("mock") || cameraSource.endsWith(".mp4") ? "Mock Video" : "Live Stream"}
        />
        <StatusIndicator 
          up={modelConfigured} 
          label="AI Model" 
          icon={BrainCircuit} 
          detail={modelConfigured ? "Configured" : "Missing Model"}
        />
      </div>
    </div>
  );
}
