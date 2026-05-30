import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatUSD, computeTotals } from "../lib/api";
import Layout from "../components/Layout";
import InvoiceHeader from "../components/InvoiceHeader";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Label } from "../components/ui/label";
import { Plus, Trash2, Save, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

const today = () => new Date().toISOString().split("T")[0];
const plusDays = (n) => {
    const d = new Date();
    d.setDate(d.getDate() + n);
    return d.toISOString().split("T")[0];
};

const blankItem = () => ({ description: "", quantity: 1, rate: 0 });

const defaultInvoice = () => ({
    invoice_number: `INV-${Date.now().toString().slice(-6)}`,
    issue_date: today(),
    due_date: plusDays(14),
    customer_name: "",
    customer_email: "",
    customer_address: "",
    items: [blankItem()],
    tax_rate: 0,
    discount: 0,
    notes: "",
    terms: "Payment due within 14 days. Late payments are subject to a 2% monthly fee.",
});

const InvoiceForm = ({ mode = "create" }) => {
    const navigate = useNavigate();
    const { id } = useParams();
    const [data, setData] = useState(defaultInvoice());
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(mode === "edit");

    useEffect(() => {
        if (mode === "edit" && id) {
            api.get(`/invoices/${id}`)
                .then(({ data }) => {
                    setData({
                        ...data,
                        items: data.items?.length ? data.items : [blankItem()],
                    });
                })
                .catch(() => toast.error("Failed to load invoice"))
                .finally(() => setLoading(false));
        }
    }, [mode, id]);

    const set = (field, val) => setData((d) => ({ ...d, [field]: val }));

    const setItem = (idx, field, val) => {
        setData((d) => {
            const items = [...d.items];
            items[idx] = { ...items[idx], [field]: val };
            return { ...d, items };
        });
    };

    const addItem = () => setData((d) => ({ ...d, items: [...d.items, blankItem()] }));
    const removeItem = (idx) =>
        setData((d) => ({
            ...d,
            items: d.items.length > 1 ? d.items.filter((_, i) => i !== idx) : d.items,
        }));

    const totals = computeTotals(data.items, data.tax_rate, data.discount);

    const handleSave = async () => {
        if (!data.customer_name.trim()) {
            toast.error("Customer name is required");
            return;
        }
        if (!data.invoice_number.trim()) {
            toast.error("Invoice number is required");
            return;
        }
        setSaving(true);
        try {
            const payload = {
                ...data,
                tax_rate: Number(data.tax_rate || 0),
                discount: Number(data.discount || 0),
                items: data.items.map((i) => ({
                    description: i.description,
                    quantity: Number(i.quantity || 0),
                    rate: Number(i.rate || 0),
                })),
            };
            let res;
            if (mode === "edit") {
                res = await api.patch(`/invoices/${id}`, payload);
                toast.success("Invoice updated");
            } else {
                res = await api.post("/invoices", payload);
                toast.success("Invoice created");
            }
            navigate(`/pay/${res.data.id}`);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Save failed");
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <Layout>
                <div className="text-center py-20 text-slate-500">Loading invoice…</div>
            </Layout>
        );
    }

    return (
        <Layout>
            <button
                onClick={() => navigate(-1)}
                className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 mb-6"
                data-testid="back-button"
            >
                <ArrowLeft className="w-4 h-4" /> Back
            </button>

            <div className="bg-white border border-slate-200 rounded-xl p-8 sm:p-12 mb-8">
                <div className="mb-10">
                    <InvoiceHeader />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10">
                    <Section title="Invoice Details">
                        <Field label="Invoice Number">
                            <Input
                                value={data.invoice_number}
                                onChange={(e) => set("invoice_number", e.target.value)}
                                data-testid="invoice-number-input"
                            />
                        </Field>
                        <div className="grid grid-cols-2 gap-4">
                            <Field label="Issue Date">
                                <Input
                                    type="date"
                                    value={data.issue_date}
                                    onChange={(e) => set("issue_date", e.target.value)}
                                    data-testid="issue-date-input"
                                />
                            </Field>
                            <Field label="Due Date">
                                <Input
                                    type="date"
                                    value={data.due_date}
                                    onChange={(e) => set("due_date", e.target.value)}
                                    data-testid="due-date-input"
                                />
                            </Field>
                        </div>
                    </Section>

                    <Section title="Bill To">
                        <Field label="Customer Name">
                            <Input
                                value={data.customer_name}
                                onChange={(e) => set("customer_name", e.target.value)}
                                placeholder="Acme Corp."
                                data-testid="customer-name-input"
                            />
                        </Field>
                        <Field label="Customer Email">
                            <Input
                                type="email"
                                value={data.customer_email}
                                onChange={(e) => set("customer_email", e.target.value)}
                                placeholder="billing@acme.com"
                                data-testid="customer-email-input"
                            />
                        </Field>
                        <Field label="Customer Address">
                            <Textarea
                                value={data.customer_address}
                                onChange={(e) => set("customer_address", e.target.value)}
                                rows={2}
                                placeholder="123 Main St, Suite 400&#10;New York, NY 10001"
                                data-testid="customer-address-input"
                            />
                        </Field>
                    </Section>
                </div>

                <Section title="Line Items">
                    <div className="overflow-x-auto">
                        <table className="w-full" data-testid="line-items-table">
                            <thead>
                                <tr>
                                    <Th className="w-1/2">Description</Th>
                                    <Th className="w-24">Qty</Th>
                                    <Th className="w-32">Rate (USD)</Th>
                                    <Th className="w-32 text-right">Amount</Th>
                                    <Th className="w-12" />
                                </tr>
                            </thead>
                            <tbody>
                                {data.items.map((item, idx) => (
                                    <tr key={idx} data-testid={`line-item-${idx}`} className="border-b border-slate-100">
                                        <td className="py-3 pr-3">
                                            <Input
                                                value={item.description}
                                                onChange={(e) => setItem(idx, "description", e.target.value)}
                                                placeholder="Description of work or product"
                                                data-testid={`item-description-${idx}`}
                                            />
                                        </td>
                                        <td className="py-3 pr-3">
                                            <Input
                                                type="number"
                                                step="0.01"
                                                min="0"
                                                value={item.quantity}
                                                onChange={(e) => setItem(idx, "quantity", e.target.value)}
                                                data-testid={`item-quantity-${idx}`}
                                            />
                                        </td>
                                        <td className="py-3 pr-3">
                                            <Input
                                                type="number"
                                                step="0.01"
                                                min="0"
                                                value={item.rate}
                                                onChange={(e) => setItem(idx, "rate", e.target.value)}
                                                data-testid={`item-rate-${idx}`}
                                            />
                                        </td>
                                        <td className="py-3 pr-3 text-right font-mono text-sm font-semibold text-slate-900" data-testid={`item-amount-${idx}`}>
                                            {formatUSD(Number(item.quantity || 0) * Number(item.rate || 0))}
                                        </td>
                                        <td className="py-3 text-right">
                                            <button
                                                onClick={() => removeItem(idx)}
                                                className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                                                data-testid={`remove-item-${idx}`}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={addItem}
                        className="mt-4 text-slate-600 hover:text-slate-900"
                        data-testid="add-item-button"
                    >
                        <Plus className="w-4 h-4 mr-1.5" /> Add Line Item
                    </Button>
                </Section>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-10">
                    <Section title="Notes & Terms">
                        <Field label="Notes (visible to customer)">
                            <Textarea
                                value={data.notes}
                                onChange={(e) => set("notes", e.target.value)}
                                rows={3}
                                placeholder="Thank you for your business."
                                data-testid="notes-input"
                            />
                        </Field>
                        <Field label="Terms & Conditions">
                            <Textarea
                                value={data.terms}
                                onChange={(e) => set("terms", e.target.value)}
                                rows={3}
                                data-testid="terms-input"
                            />
                        </Field>
                    </Section>

                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-6">
                        <div className="text-xs font-bold tracking-[0.12em] uppercase text-slate-500 mb-4">
                            Totals
                        </div>
                        <Row label="Subtotal" value={formatUSD(totals.subtotal)} testid="totals-subtotal" />
                        <div className="grid grid-cols-2 gap-4 my-4">
                            <Field label="Tax Rate (%)">
                                <Input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    value={data.tax_rate}
                                    onChange={(e) => set("tax_rate", e.target.value)}
                                    data-testid="tax-rate-input"
                                />
                            </Field>
                            <Field label="Discount ($)">
                                <Input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    value={data.discount}
                                    onChange={(e) => set("discount", e.target.value)}
                                    data-testid="discount-input"
                                />
                            </Field>
                        </div>
                        <Row label="Tax" value={formatUSD(totals.tax)} testid="totals-tax" />
                        <Row label="Discount" value={`- ${formatUSD(totals.discount)}`} testid="totals-discount" />
                        <div className="border-t border-slate-300 mt-4 pt-4 flex items-center justify-between">
                            <div className="font-heading text-lg font-bold uppercase tracking-wider text-slate-900">Total Due</div>
                            <div className="font-heading text-3xl font-black text-slate-900" data-testid="totals-total">
                                {formatUSD(totals.total)}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="flex items-center justify-end gap-3">
                <Button
                    variant="ghost"
                    onClick={() => navigate("/")}
                    className="text-slate-600 hover:text-slate-900"
                    data-testid="cancel-button"
                >
                    Cancel
                </Button>
                <Button
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-slate-900 text-white hover:bg-slate-800 rounded-md px-6 py-3 font-medium"
                    data-testid="save-invoice-button"
                >
                    <Save className="w-4 h-4 mr-2" />
                    {saving ? "Saving…" : mode === "edit" ? "Update Invoice" : "Save & Get Pay Link"}
                </Button>
            </div>
        </Layout>
    );
};

const Section = ({ title, children }) => (
    <div>
        <div className="text-xs font-bold tracking-[0.12em] uppercase text-slate-500 mb-4">{title}</div>
        <div className="space-y-4">{children}</div>
    </div>
);

const Field = ({ label, children }) => (
    <div>
        <Label className="text-xs font-semibold text-slate-600 mb-1.5 block">{label}</Label>
        {children}
    </div>
);

const Th = ({ children, className = "" }) => (
    <th className={`text-[10px] font-bold tracking-[0.12em] uppercase text-slate-500 pb-3 border-b border-slate-200 text-left ${className}`}>
        {children}
    </th>
);

const Row = ({ label, value, testid }) => (
    <div className="flex items-center justify-between text-sm py-1" data-testid={testid}>
        <span className="text-slate-600">{label}</span>
        <span className="font-mono font-semibold text-slate-900">{value}</span>
    </div>
);

export default InvoiceForm;
