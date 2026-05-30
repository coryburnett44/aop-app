import React from "react";
import { Link, useLocation } from "react-router-dom";
import { LayoutDashboard, FilePlus2, Receipt } from "lucide-react";

export const Layout = ({ children }) => {
    const location = useLocation();
    const navItems = [
        { to: "/", label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard" },
        { to: "/invoices/new", label: "New Invoice", icon: FilePlus2, testid: "nav-new-invoice" },
    ];

    return (
        <div className="min-h-screen bg-[#FAFAFA] text-slate-900">
            <header className="border-b border-slate-200 bg-white sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-6 md:px-10 py-4 flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-3" data-testid="nav-logo">
                        <Receipt className="w-6 h-6 text-slate-900" strokeWidth={2.25} />
                        <div className="leading-tight">
                            <div className="font-heading font-black uppercase tracking-tight text-slate-900 text-sm">
                                Cory Burnett
                            </div>
                            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                                Overflow Investment Legacy
                            </div>
                        </div>
                    </Link>

                    <nav className="flex items-center gap-1">
                        {navItems.map((item) => {
                            const Icon = item.icon;
                            const active = location.pathname === item.to;
                            return (
                                <Link
                                    key={item.to}
                                    to={item.to}
                                    data-testid={item.testid}
                                    className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                        active
                                            ? "bg-slate-900 text-white"
                                            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                                    }`}
                                >
                                    <Icon className="w-4 h-4" strokeWidth={2.25} />
                                    <span className="hidden sm:inline">{item.label}</span>
                                </Link>
                            );
                        })}
                    </nav>
                </div>
            </header>
            <main className="max-w-7xl mx-auto px-6 md:px-10 py-10">{children}</main>
        </div>
    );
};

export default Layout;
