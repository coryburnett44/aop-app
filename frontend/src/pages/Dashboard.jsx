import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatUSD, formatDate } from "../lib/api";
import Layout from "../components/Layout";
import StatusBadge from "../components/StatusBadge";
import InvoiceHeader from "../components/InvoiceHeader";
import { Button } from "../components/ui/button";
import { Plus, ExternalLink, Trash2, Pencil, Copy, Check } from "lucide-react";
import { toast } from "sonner";

const Dashboard = () => {
    const [invoices, setInvoices] = useState([]);
    const [loading, setLoading] = useState(true);
    const [copiedId, setCopiedId] = useState(null);
    const navigate = useNavigate();

    const load = async () => {
        try {
            const { data } = await api.get("/invoices");
            setInvoices(data);
        } catch (e) {
            toast.error("Failed to load invoices");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    const handleDelete = async (id) => {
        if (!window.confirm("Delete this invoice? This cannot be undone.")) return;
        try {
            await api.delete(`/invoices/${id}`);
            toast.success("Invoice deleted");
            setInvoices((prev) => prev.filter((i) => i.id !== id));
        } catch (e) {
            toast.error("Delete failed");
        }
    };

    const copyPayLink = async (id) => {
        const url = `${window.location.origin}/pay/${id}`;
        await navigator.clipboard.writeText(url);
        setCopiedId(id);
        toast.success("Payment link copied");
        setTimeout(() => setCopiedId(null), 2000);
    };

    const totals = invoices.reduce(
        (acc, i) => {
            acc.total += Number(i.total || 0);
            if (i.status === "paid") acc.paid += Number(i.total || 0);
            else acc.outstanding += Number(i.total || 0);
            return acc;
        },
        { total: 0, paid: 0, outstanding: 0 },
    );

    return (
        <Layout>
            <div className="mb-12" data-testid="dashboard-header">
                <InvoiceHeader />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
                <StatCard label="Total Invoiced" value={formatUSD(totals.total)} testid="stat-total" />
                <StatCard label="Paid" value={formatUSD(totals.paid)} accent="emerald" testid="stat-paid" />
                <StatCard label="Outstanding" value={formatUSD(totals.outstanding)} accent="amber" testid="stat-outstanding" />
            </div>

            <div className="flex items-center justify-between mb-8">
                <h2 className="font-heading text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
                    Invoices
                </h2>
                <Button
                    onClick={() => navigate("/invoices/new")}
                    data-testid="create-invoice-button"
                    className="bg-slate-900 text-white hover:bg-slate-800 rounded-md px-5 py-2.5 font-medium"
                >
                    <Plus className="w-4 h-4 mr-1.5" strokeWidth={2.5} />
                    New Invoice
                </Button>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                {loading ? (
                    <div className="p-12 text-center text-slate-500" data-testid="loading-state">Loading…</div>
                ) : invoices.length === 0 ? (
                    <div className="p-16 text-center" data-testid="empty-state">
                        <p className="font-heading text-xl font-bold text-slate-900 mb-2">No invoices yet</p>
                        <p className="text-slate-500 mb-6">Create your first invoice to get paid.</p>
                        <Button
                            onClick={() => navigate("/invoices/new")}
                            data-testid="empty-create-button"
                            className="bg-slate-900 text-white hover:bg-slate-800"
                        >
                            <Plus className="w-4 h-4 mr-1.5" /> Create Invoice
                        </Button>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left" data-testid="invoices-table">
                            <thead>
                                <tr className="border-b border-slate-200">
                                    <Th>Invoice #</Th>
                                    <Th>Customer</Th>
                                    <Th>Issue Date</Th>
                                    <Th>Due Date</Th>
                                    <Th>Amount</Th>
                                    <Th>Status</Th>
                                    <Th className="text-right">Actions</Th>
                                </tr>
                            </thead>
                            <tbody>
                                {invoices.map((inv) => (
                                    <tr
                                        key={inv.id}
                                        data-testid={`invoice-row-${inv.invoice_number}`}
                                        className="border-b border-slate-100 hover:bg-slate-50/60 transition-colors"
                                    >
                                        <Td>
                                            <Link
                                                to={`/pay/${inv.id}`}
                                                className="font-mono text-sm font-semibold text-slate-900 hover:underline"
                                                data-testid={`invoice-link-${inv.invoice_number}`}
                                            >
                                                {inv.invoice_number}
                                            </Link>
                                        </Td>
                                        <Td>
                                            <div className="text-sm font-medium text-slate-900">{inv.customer_name}</div>
                                            <div className="text-xs text-slate-500">{inv.customer_email}</div>
                                        </Td>
                                        <Td className="text-sm text-slate-600">{formatDate(inv.issue_date)}</Td>
                                        <Td className="text-sm text-slate-600">{formatDate(inv.due_date)}</Td>
                                        <Td className="text-sm font-semibold text-slate-900">{formatUSD(inv.total)}</Td>
                                        <Td><StatusBadge status={inv.status} /></Td>
                                        <Td>
                                            <div className="flex items-center justify-end gap-1">
                                                <IconBtn
                                                    title="Copy pay link"
                                                    onClick={() => copyPayLink(inv.id)}
                                                    testid={`copy-link-${inv.invoice_number}`}
                                                >
                                                    {copiedId === inv.id ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                                                </IconBtn>
                                                <IconBtn
                                                    title="Open pay page"
                                                    onClick={() => window.open(`/pay/${inv.id}`, "_blank")}
                                                    testid={`open-pay-${inv.invoice_number}`}
                                                >
                                                    <ExternalLink className="w-4 h-4" />
                                                </IconBtn>
                                                <IconBtn
                                                    title="Edit"
                                                    onClick={() => navigate(`/invoices/${inv.id}/edit`)}
                                                    testid={`edit-${inv.invoice_number}`}
                                                >
                                                    <Pencil className="w-4 h-4" />
                                                </IconBtn>
                                                <IconBtn
                                                    title="Delete"
                                                    onClick={() => handleDelete(inv.id)}
                                                    danger
                                                    testid={`delete-${inv.invoice_number}`}
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </IconBtn>
                                            </div>
                                        </Td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </Layout>
    );
};

const StatCard = ({ label, value, accent, testid }) => (
    <div
        data-testid={testid}
        className="bg-white border border-slate-200 rounded-xl p-6 hover:shadow-sm transition-shadow"
    >
        <div className="text-xs font-bold tracking-[0.12em] uppercase text-slate-500 mb-3">
            {label}
        </div>
        <div
            className={`font-heading text-3xl sm:text-4xl font-black tracking-tight ${
                accent === "emerald"
                    ? "text-emerald-600"
                    : accent === "amber"
                      ? "text-amber-600"
                      : "text-slate-900"
            }`}
        >
            {value}
        </div>
    </div>
);

const Th = ({ children, className = "" }) => (
    <th className={`text-xs font-bold tracking-[0.12em] uppercase text-slate-500 py-4 px-6 ${className}`}>{children}</th>
);
const Td = ({ children, className = "" }) => (
    <td className={`py-4 px-6 ${className}`}>{children}</td>
);
const IconBtn = ({ children, onClick, title, danger, testid }) => (
    <button
        onClick={onClick}
        title={title}
        data-testid={testid}
        className={`p-2 rounded-md transition-colors ${
            danger
                ? "text-slate-400 hover:bg-red-50 hover:text-red-600"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        }`}
    >
        {children}
    </button>
);

export default Dashboard;
