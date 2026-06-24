/**
 * Member-side outstanding-balance card.
 *
 * Renders inside the member's Profile, just below the dues block. Three states:
 *   - no balance      → don't render (hidden completely)
 *   - balance > 0     → show line items, total, "Pay via Zeffy" CTA, receipt form
 *   - all paid (with paid history present) → also hidden by default; admin
 *                                            mirror shows the history
 *
 * The Zeffy URL is admin-set per-member (e.g. each member's payment plan link).
 * After paying on Zeffy, the member ticks the lines they paid and pastes the
 * Zeffy confirmation; we create a PENDING transaction and an admin approves it.
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { toast } from "sonner";
import { ExternalLink, Receipt, CheckCircle2 } from "lucide-react";
import { format, parseISO } from "date-fns";

export default function MyOutstandingBalance() {
    const [balance, setBalance] = useState(null);
    const [selectedLines, setSelectedLines] = useState([]);
    const [confirmation, setConfirmation] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function load() {
        try {
            const { data } = await api.get("/me/balance");
            setBalance(data);
        } catch {
            setBalance(null);
        }
    }
    useEffect(() => { load(); }, []);

    if (!balance) return null;
    const unpaid = balance.lines.filter((l) => !l.paid_at);
    // Lines tied to a pending receipt: lock them so member doesn't double-submit.
    const lockedLineIds = new Set();
    (balance.pending_receipts || []).forEach((r) => (r.line_ids || []).forEach((id) => lockedLineIds.add(id)));
    const selectable = unpaid.filter((l) => !lockedLineIds.has(l.id));

    if (unpaid.length === 0 && (balance.pending_receipts || []).length === 0) {
        return null;
    }

    function toggle(id) {
        setSelectedLines((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
    }

    const selectedTotal = selectable
        .filter((l) => selectedLines.includes(l.id))
        .reduce((s, l) => s + l.amount, 0);

    async function submitReceipt() {
        if (selectedLines.length === 0) {
            toast.error("Select at least one line you paid for.");
            return;
        }
        if (confirmation.trim().length < 2) {
            toast.error("Paste your Zeffy confirmation / receipt number.");
            return;
        }
        setSubmitting(true);
        try {
            const { data } = await api.post("/me/balance/submit-receipt", {
                confirmation: confirmation.trim(),
                line_ids: selectedLines,
            });
            toast.success(data.message || "Receipt submitted");
            setSelectedLines([]);
            setConfirmation("");
            await load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Submit failed");
        }
        setSubmitting(false);
    }

    return (
        <div className="rounded-2xl border-2 border-primary/30 bg-gradient-to-br from-primary/5 to-amber-50 p-5 shadow-warm mb-6" data-testid="my-outstanding-balance">
            <div className="flex items-baseline justify-between flex-wrap gap-2 mb-3">
                <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-bold text-primary">Outstanding balance</div>
                    <div className="font-heading text-2xl font-black text-foreground">
                        ${balance.total.toFixed(2)}
                        <span className="text-sm font-normal text-muted-foreground ml-2">due</span>
                    </div>
                </div>
                {balance.zeffy_url && (
                    <a
                        href={balance.zeffy_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-full bg-primary hover:bg-primary/90 text-white px-4 py-2 text-sm font-bold shadow-warm transition-colors"
                        data-testid="my-balance-pay-zeffy"
                    >
                        <ExternalLink className="h-4 w-4" />
                        Pay via Zeffy
                    </a>
                )}
            </div>

            {unpaid.length > 0 && (
                <div className="bg-card rounded-xl border border-border p-3 space-y-2 mb-3">
                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">What you owe</div>
                    {unpaid.map((ln) => {
                        const locked = lockedLineIds.has(ln.id);
                        return (
                            <label
                                key={ln.id}
                                className={`flex items-center gap-3 p-2 rounded-lg ${locked ? "opacity-60" : "hover:bg-muted/40 cursor-pointer"}`}
                                data-testid={`my-balance-line-${ln.id}`}
                            >
                                <input
                                    type="checkbox"
                                    disabled={locked}
                                    checked={selectedLines.includes(ln.id)}
                                    onChange={() => toggle(ln.id)}
                                    className="h-4 w-4 rounded"
                                    data-testid={`my-balance-line-check-${ln.id}`}
                                />
                                <div className="flex-1 min-w-0">
                                    <div className="font-semibold truncate">{ln.label}</div>
                                    {locked && <div className="text-xs text-amber-700">Awaiting admin verification</div>}
                                </div>
                                <div className="font-heading font-bold tabular-nums">${ln.amount.toFixed(2)}</div>
                            </label>
                        );
                    })}
                </div>
            )}

            {(balance.pending_receipts || []).length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-3" data-testid="my-balance-pending-receipts">
                    <div className="text-xs font-bold uppercase tracking-wider text-amber-900 mb-1">Pending verification</div>
                    {balance.pending_receipts.map((r) => (
                        <div key={r.id} className="text-sm flex items-center justify-between gap-2" data-testid={`my-balance-pending-${r.id}`}>
                            <div className="text-amber-900">
                                ${r.amount.toFixed(2)} · ref <code>{r.confirmation}</code>
                                {r.created_at && ` · ${format(parseISO(r.created_at), "MMM d")}`}
                            </div>
                            <CheckCircle2 className="h-4 w-4 text-amber-600 shrink-0" />
                        </div>
                    ))}
                </div>
            )}

            {selectable.length > 0 && (
                <div className="bg-card rounded-xl border border-border p-3">
                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2 inline-flex items-center gap-1.5">
                        <Receipt className="h-3.5 w-3.5" /> Already paid? Submit your Zeffy receipt
                    </div>
                    <div className="flex flex-wrap gap-2 items-end">
                        <div className="flex-1 min-w-[200px]">
                            <Label className="text-xs">Zeffy confirmation / receipt #</Label>
                            <Input
                                value={confirmation}
                                onChange={(e) => setConfirmation(e.target.value)}
                                placeholder="RCT-XXXX-XXXX or your confirmation email"
                                className="rounded-xl mt-1"
                                data-testid="my-balance-confirmation"
                            />
                        </div>
                        <Button
                            onClick={submitReceipt}
                            disabled={submitting || selectedLines.length === 0}
                            className="rounded-full bg-primary hover:bg-primary/90"
                            data-testid="my-balance-submit-receipt"
                        >
                            {submitting ? "Submitting…" : `Confirm $${selectedTotal.toFixed(2)} paid`}
                        </Button>
                    </div>
                    <div className="text-xs text-muted-foreground mt-2">
                        Tick the lines you paid for, paste the Zeffy reference, and we&apos;ll mark them paid once an admin verifies.
                    </div>
                </div>
            )}
        </div>
    );
}
