import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { PayPalScriptProvider, PayPalButtons } from "@paypal/react-paypal-js";
import { api, formatUSD, formatDate } from "../lib/api";
import InvoiceHeader from "../components/InvoiceHeader";
import StatusBadge from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { CheckCircle2, Printer, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const PayInvoice = () => {
    const { id } = useParams();
    const [invoice, setInvoice] = useState(null);
    const [paypalCfg, setPaypalCfg] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = async () => {
        try {
            const [inv, cfg] = await Promise.all([
                api.get(`/invoices/${id}`),
                api.get(`/config/paypal`),
            ]);
            setInvoice(inv.data);
            setPaypalCfg(cfg.data);
        } catch (e) {
            setError(e?.response?.data?.detail || "Invoice not found");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, [id]);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center text-slate-500" data-testid="pay-loading">
                Loading invoice…
            </div>
        );
    }

    if (error || !invoice) {
        return (
            <div className="min-h-screen flex items-center justify-center" data-testid="pay-error">
                <div className="text-center max-w-md">
                    <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
                    <h1 className="font-heading text-2xl font-bold text-slate-900 mb-2">Invoice Not Found</h1>
                    <p className="text-slate-600 mb-6">{error || "This invoice does not exist."}</p>
                    <Link to="/" className="text-slate-900 underline font-medium">Back to Dashboard</Link>
                </div>
            </div>
        );
    }

    const isPaid = invoice.status === "paid";
    const paypalReady = paypalCfg?.configured && paypalCfg?.client_id;

    return (
        <div className="min-h-screen bg-[#FAFAFA] py-8 sm:py-16 px-4">
            <div className="max-w-4xl mx-auto">
                <div className="no-print mb-6 flex items-center justify-between">
                    <Link
                        to="/"
                        className="text-sm text-slate-500 hover:text-slate-900"
                        data-testid="pay-back-link"
                    >
                        ← Dashboard
                    </Link>
                    <button
                        onClick={() => window.print()}
                        className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
                        data-testid="print-button"
                    >
                        <Printer className="w-4 h-4" /> Print
                    </button>
                </div>

                <div className="bg-white border border-slate-200 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-xl p-8 sm:p-16">
                    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-6 mb-12 pb-10 border-b border-slate-200">
                        <InvoiceHeader size="large" />
                        <div className="text-right shrink-0">
                            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-1">
                                Invoice
                            </div>
                            <div className="font-mono text-lg font-bold text-slate-900" data-testid="pay-invoice-number">
                                {invoice.invoice_number}
                            </div>
                            <div className="mt-3">
                                <StatusBadge status={invoice.status} />
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-8 mb-12">
                        <InfoBlock label="Bill To">
                            <div className="text-base font-semibold text-slate-900" data-testid="pay-customer-name">
                                {invoice.customer_name}
                            </div>
                            {invoice.customer_email && (
                                <div className="text-sm text-slate-600">{invoice.customer_email}</div>
                            )}
                            {invoice.customer_address && (
                                <div className="text-sm text-slate-600 whitespace-pre-line mt-1">
                                    {invoice.customer_address}
                                </div>
                            )}
                        </InfoBlock>
                        <div className="grid grid-cols-2 gap-6">
                            <InfoBlock label="Issue Date">
                                <div className="text-sm font-medium text-slate-900">{formatDate(invoice.issue_date)}</div>
                            </InfoBlock>
                            <InfoBlock label="Due Date">
                                <div className="text-sm font-medium text-slate-900">{formatDate(invoice.due_date)}</div>
                            </InfoBlock>
                            <InfoBlock label="Amount Due">
                                <div className="font-heading text-2xl font-black text-slate-900" data-testid="pay-amount-due">
                                    {formatUSD(invoice.total)}
                                </div>
                            </InfoBlock>
                            <InfoBlock label="Currency">
                                <div className="text-sm font-medium text-slate-900">{invoice.currency || "USD"}</div>
                            </InfoBlock>
                        </div>
                    </div>

                    <div className="mb-12">
                        <table className="w-full" data-testid="pay-items-table">
                            <thead>
                                <tr className="border-b-2 border-slate-900">
                                    <th className="text-[10px] font-bold tracking-[0.12em] uppercase text-slate-700 py-3 text-left">Description</th>
                                    <th className="text-[10px] font-bold tracking-[0.12em] uppercase text-slate-700 py-3 text-right w-20">Qty</th>
                                    <th className="text-[10px] font-bold tracking-[0.12em] uppercase text-slate-700 py-3 text-right w-32">Rate</th>
                                    <th className="text-[10px] font-bold tracking-[0.12em] uppercase text-slate-700 py-3 text-right w-32">Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                                {invoice.items.map((it, i) => (
                                    <tr key={i} className="border-b border-slate-100">
                                        <td className="py-4 text-slate-800">{it.description || "—"}</td>
                                        <td className="py-4 text-right text-slate-600 font-mono text-sm">{it.quantity}</td>
                                        <td className="py-4 text-right text-slate-600 font-mono text-sm">{formatUSD(it.rate)}</td>
                                        <td className="py-4 text-right text-slate-900 font-mono text-sm font-semibold">
                                            {formatUSD(Number(it.quantity || 0) * Number(it.rate || 0))}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        <div className="flex justify-end mt-6">
                            <div className="w-full sm:w-80 space-y-2">
                                <Line label="Subtotal" value={formatUSD(invoice.subtotal)} />
                                {invoice.tax_rate > 0 && (
                                    <Line label={`Tax (${invoice.tax_rate}%)`} value={formatUSD(invoice.tax)} />
                                )}
                                {invoice.discount > 0 && (
                                    <Line label="Discount" value={`- ${formatUSD(invoice.discount)}`} />
                                )}
                                <div className="border-t-2 border-slate-900 mt-3 pt-3 flex items-center justify-between">
                                    <div className="font-heading text-base font-bold uppercase tracking-wider text-slate-900">Total</div>
                                    <div className="font-heading text-3xl font-black text-slate-900" data-testid="pay-total">
                                        {formatUSD(invoice.total)}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {(invoice.notes || invoice.terms) && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-8 mb-12 pb-10 border-b border-slate-200">
                            {invoice.notes && (
                                <InfoBlock label="Notes">
                                    <p className="text-sm text-slate-600 whitespace-pre-line">{invoice.notes}</p>
                                </InfoBlock>
                            )}
                            {invoice.terms && (
                                <InfoBlock label="Terms">
                                    <p className="text-sm text-slate-600 whitespace-pre-line">{invoice.terms}</p>
                                </InfoBlock>
                            )}
                        </div>
                    )}

                    <div className="no-print" data-testid="payment-section">
                        {isPaid ? (
                            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-8 text-center" data-testid="paid-banner">
                                <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto mb-3" />
                                <div className="font-heading text-2xl font-bold text-emerald-900 mb-1">Payment Received</div>
                                <p className="text-sm text-emerald-700">
                                    Paid on {formatDate(invoice.paid_at)} — Thank you for your business.
                                </p>
                            </div>
                        ) : (
                            <div>
                                <div className="text-center mb-6">
                                    <div className="text-xs font-bold tracking-[0.18em] uppercase text-slate-500 mb-2">
                                        Pay Now
                                    </div>
                                    <div className="font-heading text-4xl sm:text-5xl font-black text-slate-900 mb-1" data-testid="pay-now-amount">
                                        {formatUSD(invoice.total)}
                                    </div>
                                    <p className="text-sm text-slate-500">Secure checkout via PayPal</p>
                                </div>

                                {paypalReady ? (
                                    <div className="max-w-md mx-auto" data-testid="paypal-button-container">
                                        <PayPalScriptProvider
                                            options={{
                                                clientId: paypalCfg.client_id,
                                                currency: invoice.currency || "USD",
                                                intent: "capture",
                                            }}
                                        >
                                            <PayPalButtons
                                                style={{ layout: "vertical", color: "gold", shape: "rect", label: "pay" }}
                                                createOrder={async () => {
                                                    const { data } = await api.post(
                                                        `/invoices/${invoice.id}/paypal/create-order`,
                                                    );
                                                    return data.id;
                                                }}
                                                onApprove={async (data) => {
                                                    try {
                                                        await api.post(
                                                            `/invoices/${invoice.id}/paypal/capture/${data.orderID}`,
                                                        );
                                                        toast.success("Payment successful!");
                                                        await load();
                                                    } catch (e) {
                                                        toast.error("Capture failed");
                                                    }
                                                }}
                                                onError={() => toast.error("PayPal error — please try again")}
                                            />
                                        </PayPalScriptProvider>
                                    </div>
                                ) : (
                                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 max-w-md mx-auto text-center" data-testid="paypal-not-configured">
                                        <AlertTriangle className="w-8 h-8 text-amber-600 mx-auto mb-3" />
                                        <p className="font-semibold text-amber-900 mb-1">PayPal not configured</p>
                                        <p className="text-sm text-amber-700">
                                            Add PAYPAL_CLIENT_ID and PAYPAL_SECRET to backend/.env, then restart backend.
                                        </p>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

const InfoBlock = ({ label, children }) => (
    <div>
        <div className="text-[10px] font-bold tracking-[0.18em] uppercase text-slate-500 mb-2">
            {label}
        </div>
        {children}
    </div>
);

const Line = ({ label, value }) => (
    <div className="flex items-center justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-mono font-semibold text-slate-900">{value}</span>
    </div>
);

export default PayInvoice;
