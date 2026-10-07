import fs from "fs";
import path from "path";
import { Settings, Camera, Server, BrainCircuit, ScanLine, ShieldAlert, Activity, CheckSquare } from "lucide-react";
import SystemHealthClient from "./SystemHealthClient";

export default async function SettingsPage() {
  // Read CV Pipeline Config
  const cvEnvPath = path.join(process.cwd(), "..", "cv_pipeline", ".env");
  let cvEnv = "";
  try {
    cvEnv = fs.readFileSync(cvEnvPath, "utf-8");
  } catch (e) {
    console.error("Failed to read CV .env", e);
  }

  // Read Backend Config
  const backendEnvPath = path.join(process.cwd(), "..", "backend", ".env");
  let backendEnv = "";
  try {
    backendEnv = fs.readFileSync(backendEnvPath, "utf-8");
  } catch (e) {
    console.error("Failed to read Backend .env", e);
  }

  const parseEnv = (content: string) => {
    return content.split("\n").reduce((acc, line) => {
      const match = line.match(/^([^=]+)=(.*)$/);
      if (match) {
        acc[match[1].trim()] = match[2].trim();
      }
      return acc;
    }, {} as Record<string, string>);
  };

  const cvConfig = parseEnv(cvEnv);
  const backendConfig = parseEnv(backendEnv);

  const cameraSource = cvConfig.CAMERA_SOURCE || "Not set";
  const modelConfigured = !!cvConfig.YOLO_MODEL_PATH;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center">
          <Settings className="w-6 h-6 mr-2" />
          Settings
        </h1>
        <p className="text-sm text-slate-500 mt-1">System configuration and deployment parameters (Read-only).</p>
      </div>

      <SystemHealthClient 
        cameraConfigured={true} 
        modelConfigured={modelConfigured} 
        cameraSource={cameraSource}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Camera & Video */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          <div className="bg-slate-50 border-b border-gray-200 px-4 py-3 flex items-center font-medium text-slate-800">
            <Camera className="w-4 h-4 mr-2 text-slate-500" />
            Camera & Video
          </div>
          <div className="p-4 space-y-4 text-sm">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Camera Source</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                {cameraSource}
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Resolution (W x H)</label>
                <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                  1280x720 (Default)
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Target FPS</label>
                <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                  30 (Default)
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* AI Model Settings */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          <div className="bg-slate-50 border-b border-gray-200 px-4 py-3 flex items-center font-medium text-slate-800">
            <BrainCircuit className="w-4 h-4 mr-2 text-slate-500" />
            AI Model
          </div>
          <div className="p-4 space-y-4 text-sm">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">YOLO Model Path</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100 break-all">
                {cvConfig.YOLO_MODEL_PATH || "Not set"}
              </div>
            </div>
            
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Confidence Threshold</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                {cvConfig.YOLO_CONFIDENCE_THRESHOLD || "0.5"}
              </div>
            </div>
          </div>
        </div>

        {/* Counting Logic Settings */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          <div className="bg-slate-50 border-b border-gray-200 px-4 py-3 flex items-center font-medium text-slate-800">
            <CheckSquare className="w-4 h-4 mr-2 text-slate-500" />
            Counting Logic
          </div>
          <div className="p-4 space-y-4 text-sm">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Counting Line (X, Y) to (X, Y)</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                ({cvConfig.LINE_START_X || 0}, {cvConfig.LINE_START_Y || 400}) to ({cvConfig.LINE_END_X || 1280}, {cvConfig.LINE_END_Y || 400})
              </div>
            </div>
            
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Direction</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                Top-to-Bottom
              </div>
            </div>
          </div>
        </div>

        {/* QR Scanning Settings */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          <div className="bg-slate-50 border-b border-gray-200 px-4 py-3 flex items-center font-medium text-slate-800">
            <ScanLine className="w-4 h-4 mr-2 text-slate-500" />
            QR Scanning
          </div>
          <div className="p-4 space-y-4 text-sm">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">QR Decoder</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                BoofCV / ZXing (Hybrid)
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Validation Backend</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                Connected via Backend API
              </div>
            </div>
          </div>
        </div>

        {/* Alerts Settings */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden md:col-span-2">
          <div className="bg-slate-50 border-b border-gray-200 px-4 py-3 flex items-center font-medium text-slate-800">
            <ShieldAlert className="w-4 h-4 mr-2 text-slate-500" />
            Alerts Configuration
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">QR Exception Threshold</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                {backendConfig.ALERT_EXCEPTION_THRESHOLD || "5"} events
              </div>
              <p className="text-xs text-slate-500 mt-1">Number of exceptions required to trigger a spike alert.</p>
            </div>
            
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Evaluation Window</label>
              <div className="text-slate-900 font-mono bg-slate-50 px-3 py-2 rounded border border-gray-100">
                {backendConfig.ALERT_EXCEPTION_WINDOW_MINUTES || "10"} minutes
              </div>
              <p className="text-xs text-slate-500 mt-1">Timeframe for evaluating the exception threshold.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
