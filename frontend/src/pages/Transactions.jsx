import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { format, parseISO } from "date-fns";
import { Download, Filter, Receipt } from "lucide-react";
import { Button } from "../components/ui/button";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";

const TYPE_LABEL = {
    dues: "Dues",
    donation: "Donation",
    gear: "Gear",
    other: "Other",
};

const STATUS_PILL = {
    completed: "bg-emerald-100 text-emerald-700",
    pending: "bg-amber-100 text-amber-800",
    refunded: "bg-slate-100 text-slate-600",
    failed: "bg-red-100 text-red-700",
};

function money(t) {
    const n = Number(t.amount || 0);
    return `$${n.toFixed(2)}`;
}

function rowsToCSV(rows) {
    const headers = ["Date", "Type", "Description", "Amount", "Status", "Provider", "Reference"];
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const out = [headers.map(esc).join(",")];
    rows.forEach((t) => {
        out.push([
            t.created_at?.slice(0, 10) || "",
            TYPE_LABEL[t.type] || t.type,
            t.note || t.description || "",
            money(t),
            t.status || "",
            t.provider || "",
            t.provider_ref || t.external_id || "",
        ].map(esc).join(","));
    });
    return out.join("\n");
}

export default function Transactions() {
    const [items, setItems] = useState([]);
    const [type, setType] = useState("all");
    const [status, setStatus] = useState("all");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/me/transactions")
            .then(({ data }) => setItems(data))
            .catch(() => toast.error("Couldn't load your transactions"))
            .finally(() => setLoading(false));
    }, []);

    const filtered = useMemo(() => {
        return items.filter((t) => {
            if (type !== "all" && t.type !== type) return false;
            if (status !== "all" && t.status !== status) return false;
            return true;
        });
    }, [items, type, status]);

    const totals = useMemo(() => {
        const sumBy = (preds) => filtered.filter(preds).reduce((acc, t) => acc + Number(t.amount || 0), 0);
        return {
            total: sumBy(() => true),
            donations: sumBy((t) => t.type === "donation"),
            gear: sumBy((t) => t.type === "gear"),
            dues: sumBy((t) => t.type === "dues"),
        };
    }, [filtered]);

    function exportCSV() {
        const csv = rowsToCSV(filtered);
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `my-transactions-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-10" data-testid="transactions-page">
            <div className="flex items-center justify-between gap-3 flex-wrap mb-6">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] font-bold text-primary mb-1">Profile</div>
                    <h1 className="font-heading text-3xl sm:text-4xl font-bold flex items-center gap-2"><Receipt className="h-7 w-7" />Transactions</h1>
                    <p className="text-sm text-muted-foreground mt-1">Every dues renewal, donation, and gear purchase you've made through Alpha Omega Phi.</p>
                </div>
                <Button onClick={exportCSV} variant="outline" className="rounded-full" disabled={!filtered.length} data-testid="transactions-csv-btn">
                    <Download className="h-4 w-4 mr-1.5" /> Export CSV
                </Button>
            </div>

            <div className="grid sm:grid-cols-4 gap-3 mb-6">
                <SummaryCard label="Total spent" value={`$${totals.total.toFixed(2)}`} testid="tx-total" />
                <SummaryCard label="Donations" value={`$${totals.donations.toFixed(2)}`} testid="tx-donations" />
                <SummaryCard label="Gear" value={`$${totals.gear.toFixed(2)}`} testid="tx-gear" />
                <SummaryCard label="Dues" value={`$${totals.dues.toFixed(2)}`} testid="tx-dues" />
            </div>

            <div className="bg-card rounded-2xl border border-border p-5 mb-4">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><Filter className="h-4 w-4" /> Filters</div>
                <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                        <label className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">Type</label>
                        <Select value={type} onValueChange={setType}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="tx-filter-type"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All types</SelectItem>
                                <SelectItem value="dues">Dues</SelectItem>
                                <SelectItem value="donation">Donations</SelectItem>
                                <SelectItem value="gear">Gear</SelectItem>
                                <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">Status</label>
                        <Select value={status} onValueChange={setStatus}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="tx-filter-status"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Any status</SelectItem>
                                <SelectItem value="completed">Completed</SelectItem>
                                <SelectItem value="pending">Pending</SelectItem>
                                <SelectItem value="refunded">Refunded</SelectItem>
                                <SelectItem value="failed">Failed</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </div>

            {loading ? (
                <div className="text-muted-foreground text-center py-12">Loading…</div>
            ) : filtered.length === 0 ? (
                <div className="bg-card rounded-2xl border border-dashed border-border p-12 text-center" data-testid="transactions-empty">
                    <Receipt className="h-10 w-10 mx-auto text-muted-foreground/40" />
                    <div className="mt-4 font-heading text-xl font-bold">Nothing here yet.</div>
                    <p className="text-sm text-muted-foreground mt-1.5">Your dues, donations, and gear orders will appear here as soon as you make them.</p>
                </div>
            ) : (
                <div className="bg-card rounded-2xl border border-border overflow-x-auto">
                    <table className="w-full text-sm min-w-[640px]">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-4 py-3">Date</th>
                                <th className="text-left px-4 py-3">Type</th>
                                <th className="text-left px-4 py-3">Description</th>
                                <th className="text-right px-4 py-3">Amount</th>
                                <th className="text-left px-4 py-3">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((t) => (
                                <tr key={t.id} className="border-t border-border align-top" data-testid={`tx-row-${t.id}`}>
                                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{t.created_at ? format(parseISO(t.created_at), "MMM d, yyyy") : "—"}</td>
                                    <td className="px-4 py-3"><span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary">{TYPE_LABEL[t.type] || t.type}</span></td>
                                    <td className="px-4 py-3">
                                        <div className="font-medium">{t.note || t.description || (TYPE_LABEL[t.type] || "Payment")}</div>
                                        {t.provider_ref && <div className="text-xs text-muted-foreground mt-0.5">Ref: {t.provider_ref}</div>}
                                    </td>
                                    <td className="px-4 py-3 text-right font-heading font-bold">{money(t)}</td>
                                    <td className="px-4 py-3">
                                        <span className={`text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 ${STATUS_PILL[t.status] || "bg-slate-100 text-slate-600"}`}>{t.status || "—"}</span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function SummaryCard({ label, value, testid }) {
    return (
        <div className="bg-card rounded-2xl border border-border p-4" data-testid={testid}>
            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">{label}</div>
            <div className="font-heading text-2xl font-black mt-1">{value}</div>
        </div>
    );
}
