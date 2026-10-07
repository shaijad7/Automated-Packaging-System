"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Package, Home, Settings, LogOut, Activity, FileText, Menu, X } from "lucide-react";
import { removeAuthToken } from "@/lib/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [isSidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    removeAuthToken();
    router.push("/login");
  };

  const navItems = [
    { name: "Dashboard", href: "/dashboard", icon: Home, disabled: false },
    { name: "Products", href: "/inventory/products", icon: Package, disabled: false },
    { name: "Alerts", href: "/alerts", icon: Activity, disabled: false },
    { name: "Reports", href: "/reports", icon: FileText, disabled: false },
    { name: "Settings", href: "/settings", icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Mobile/Tablet Overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 z-40 bg-slate-900/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 flex flex-col transform transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="h-16 flex items-center justify-between px-6 bg-slate-950 border-b border-slate-800">
          <h1 className="text-white font-bold text-lg tracking-wide uppercase">Smart Inventory</h1>
          <button className="md:hidden text-slate-400 hover:text-white" onClick={() => setSidebarOpen(false)}>
            <X className="h-6 w-6" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-6">
          <nav className="space-y-1 px-3">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 px-3">Inventory Control</div>
            {navItems.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              
              if (item.disabled) {
                return (
                  <div key={item.name} className="flex items-center px-3 py-2 text-slate-600 cursor-not-allowed text-sm font-medium rounded-md">
                    <Icon className="mr-3 h-5 w-5 opacity-50" />
                    {item.name}
                  </div>
                );
              }

              return (
                <Link
                  key={item.name}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-slate-300 hover:bg-slate-800 hover:text-white"
                  }`}
                >
                  <Icon className="mr-3 h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="p-4 border-t border-slate-800">
          <button
            onClick={handleLogout}
            className="flex items-center w-full px-3 py-2 text-sm font-medium text-slate-300 rounded-md hover:bg-slate-800 hover:text-white transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-500"
          >
            <LogOut className="mr-3 h-5 w-5" />
            Logout
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile/Tablet Header */}
        <div className="md:hidden flex items-center justify-between px-4 h-16 bg-white border-b border-gray-200">
          <div className="flex items-center">
            <button 
              onClick={() => setSidebarOpen(true)} 
              className="mr-3 p-2 -ml-2 text-slate-600 hover:text-slate-900 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <Menu className="h-6 w-6" />
            </button>
            <h1 className="font-bold text-lg text-slate-800 tracking-wide uppercase">Smart Inventory</h1>
          </div>
        </div>

        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
