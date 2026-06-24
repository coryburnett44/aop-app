/**
 * Admin-side balance editor — used inside the member-edit dialog.
 *
 * Surfaces three things for one member:
 *   1. The per-member Zeffy URL (admin pastes it; we soft-validate https).
 *   2. The list of balance lines (label + amount + status pill).
 *   3. Actions: add line, edit unpaid line, delete unpaid line, mark line paid,
 *      approve a pending receipt the member submitted.
 *
 * The component owns its own fetch of `/api/admin/members/:id/balance` so it
 * can refresh after every mutation without coupling to the parent dialog's
 * form state (which is for the *user record*, not the balance).
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { toast } from "sonner";
import { Trash2, CheckCircle2, Edit3, ExternalLink } from "lucide-react";
import { format, parseISO } from "date-fns";

export default function MemberBalanceEditor({ memberId, memberName }) {
    const [balance, setBalance] = useState(null);
    const [zeffyUrl, setZeffyUrl] = useState("");
    // Track the URL value last confirmed by the server so we can show a clear
    // "Unsaved / Saving / Saved" hint and auto-save on blur. Without this hint
    // admins paste the URL, click the dialog's bottom "Save changes" (which
    // does NOT touch `outstanding_zeffy_url` — that's an isolated endpoint),
    // close the dialog, and the URL silently disappears.
    const [serverZeffyUrl, setServerZeffyUrl] = useState("");
    const [urlSaving, setUrlSaving] = useState(false);
    const [editingLineId, setEditingLineId] = useState(null);
    const [editForm, setEditForm] = useState({ label: "", amount: "" });
    const [newLine, setNewLine] = useState({ label: "", amount: "" });
    const [pendingReceipts, setPendingReceipts] = useState([]);
    const [busy, setBusy] = useState(false);

    async function load() {
        try {
            const { data } = await api.get(`/admin/members/${memberId}/balance`);
            setBalance(data);
            setZeffyUrl(data.zeffy_url || "");
            setServerZeffyUrl(data.zeffy_url || "");
            // Pending receipts come from /transactions?user_id=&type_filter=fee
            // and we filter to balance+pending in the UI for accuracy.
            const { data: txs } = await api.get(`/transactions?user_id=${memberId}`).catch(() => ({ data: [] }));
            setPendingReceipts(
                (txs || []).filter((t) => t.purpose === "balance" && t.status === "pending"),
            );
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to load balance");
        }
    }

    useEffect(() => { if (memberId) load(); }, [memberId]);

    async function saveZeffyUrl({ silent = false } = {}) {
        const next = zeffyUrl.trim();
        if (next === serverZeffyUrl.trim()) return; // nothing to save
        setUrlSaving(true);
        setBusy(true);
        try {
            await api.put(`/admin/members/${memberId}/balance/zeffy-url`, { url: next });
            setServerZeffyUrl(next);
            if (!silent) toast.success(next ? "Zeffy URL saved" : "Zeffy URL cleared");
            // Re-fetch the canonical balance so the "Open this member's Zeffy
            // form" preview link refreshes too.
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setUrlSaving(false);
        setBusy(false);
    }

    async function addLine() {
        const amount = parseFloat(newLine.amount);
        if (!newLine.label.trim() || !(amount > 0)) {
            toast.error("Enter a label and a positive amount");
            return;
        }
        setBusy(true);
        try {
            await api.post(`/admin/members/${memberId}/balance/lines`, {
                label: newLine.label.trim(),
                amount,
            });
            setNewLine({ label: "", amount: "" });
            toast.success("Line added");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Add failed"); }
        setBusy(false);
    }

    async function saveLineEdit(lineId) {
        const amount = parseFloat(editForm.amount);
        if (!editForm.label.trim() || !(amount > 0)) {
            toast.error("Enter a label and a positive amount");
            return;
        }
        setBusy(true);
        try {
            await api.put(`/admin/members/${memberId}/balance/lines/${lineId}`, {
                label: editForm.label.trim(),
                amount,
            });
            setEditingLineId(null);
            toast.success("Saved");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    async function deleteLine(lineId) {
        if (!window.confirm("Delete this balance line? This cannot be undone.")) return;
        setBusy(true);
        try {
            await api.delete(`/admin/members/${memberId}/balance/lines/${lineId}`);
            toast.success("Line removed");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
        setBusy(false);
    }

    async function markPaid(lineId) {
        if (!window.confirm("Mark this line PAID? This creates a completed transaction on the member's record. Use this after reconciling the Zeffy payment.")) return;
        setBusy(true);
        try {
            await api.post(`/admin/members/${memberId}/balance/lines/${lineId}/mark-paid`);
            toast.success("Marked paid");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Mark-paid failed"); }
        setBusy(false);
    }

    async function approveReceipt(txId) {
        setBusy(true);
        try {
            await api.put(`/admin/transactions/${txId}/approve-balance`);
            toast.success("Receipt approved");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Approve failed"); }
        setBusy(false);
    }

    if (!balance) {
        return (
            <div className="rounded-2xl border border-border bg-muted/30 p-4 text-sm text-muted-foreground" data-testid="balance-editor-loading">
                Loading balance…
            </div>
        );
    }

    const unpaidLines = balance.lines.filter((l) => !l.paid_at);
    const paidLines = balance.lines.filter((l) => l.paid_at);

    return (
        <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 space-y-4" data-testid="balance-editor">
            <div className="flex items-baseline justify-between flex-wrap gap-2">
                <div>
                    <div className="text-sm font-bold text-primary uppercase tracking-wider">Outstanding balance</div>
                    <div className="text-xs text-muted-foreground">
                        Anniversary fees, back dues, late fees. Does NOT affect membership expiration.
                    </div>
                </div>
                <div className="text-2xl font-heading font-black text-primary" data-testid="balance-total">
                    ${balance.total.toFixed(2)}
                </div>
            </div>

            {/* Zeffy URL */}
            <div className="bg-card rounded-xl p-3 border border-border">
                <Label className="text-xs flex items-center justify-between">
                    <span>Per-member Zeffy payment URL</span>
                    {(() => {
                        const dirty = zeffyUrl.trim() !== serverZeffyUrl.trim();
                        if (urlSaving) return <span className="text-[10px] uppercase tracking-wider font-bold text-amber-700" data-testid="balance-zeffy-url-status-saving">Saving…</span>;
                        if (dirty) return <span className="text-[10px] uppercase tracking-wider font-bold text-amber-700" data-testid="balance-zeffy-url-status-unsaved">Unsaved · auto-saves on blur</span>;
                        if (serverZeffyUrl) return <span className="text-[10px] uppercase tracking-wider font-bold text-emerald-700" data-testid="balance-zeffy-url-status-saved">Saved</span>;
                        return null;
                    })()}
                </Label>
                <div className="flex gap-2 mt-1.5">
                    <Input
                        value={zeffyUrl}
                        onChange={(e) => setZeffyUrl(e.target.value)}
                        onBlur={() => { void saveZeffyUrl({ silent: true }); }}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") {
                                e.preventDefault();
                                e.currentTarget.blur(); // triggers onBlur auto-save
                            }
                        }}
                        placeholder="https://www.zeffy.com/en-US/ticketing/..."
                        className="rounded-xl flex-1"
                        data-testid="balance-zeffy-url-input"
                    />
                    <Button
                        size="sm"
                        onClick={() => saveZeffyUrl()}
                        disabled={busy || zeffyUrl.trim() === serverZeffyUrl.trim()}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid="balance-zeffy-url-save"
                    >
                        Save URL
                    </Button>
                </div>
                <div className="text-[11px] text-muted-foreground mt-1.5">
                    Paste the member&apos;s personal Zeffy payment-plan link here. <strong>Auto-saves</strong> when you click elsewhere — the dialog&apos;s main &ldquo;Save changes&rdquo; button does not save this field.
                </div>
                {serverZeffyUrl && (
                    <a
                        href={serverZeffyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary hover:underline inline-flex items-center gap-1 mt-1.5"
                        data-testid="balance-zeffy-url-preview"
                    >
                        <ExternalLink className="h-3 w-3" /> Open this member&apos;s Zeffy form
                    </a>
                )}
            </div>

            {/* Pending receipts the member submitted */}
            {pendingReceipts.length > 0 && (
                <div className="bg-amber-50 border border-amber-300 rounded-xl p-3 space-y-2" data-testid="balance-pending-receipts">
                    <div className="text-xs font-bold text-amber-900 uppercase tracking-wider">Pending receipts to verify</div>
                    {pendingReceipts.map((tx) => (
                        <div key={tx.id} className="flex items-center justify-between gap-2 text-sm" data-testid={`balance-pending-${tx.id}`}>
                            <div className="flex-1 min-w-0">
                                <div className="font-semibold">${(tx.amount || 0).toFixed(2)}</div>
                                <div className="text-xs text-amber-800 truncate">
                                    Ref: <code>{tx.zeffy_confirmation || "—"}</code>
                                    {tx.created_at && ` · ${format(parseISO(tx.created_at), "MMM d")}`}
                                </div>
                            </div>
                            <Button
                                size="sm"
                                onClick={() => approveReceipt(tx.id)}
                                disabled={busy}
                                className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white shrink-0"
                                data-testid={`balance-approve-${tx.id}`}
                            >
                                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve
                            </Button>
                        </div>
                    ))}
                </div>
            )}

            {/* Unpaid lines */}
            <div className="space-y-2">
                <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Open balance lines</div>
                {unpaidLines.length === 0 ? (
                    <div className="text-xs text-muted-foreground italic">No open lines.</div>
                ) : (
                    unpaidLines.map((ln) => (
                        <div key={ln.id} className="bg-card rounded-xl p-3 border border-border" data-testid={`balance-line-${ln.id}`}>
                            {editingLineId === ln.id ? (
                                <div className="flex flex-wrap gap-2 items-end">
                                    <div className="flex-1 min-w-[160px]">
                                        <Label className="text-xs">Label</Label>
                                        <Input
                                            value={editForm.label}
                                            onChange={(e) => setEditForm({ ...editForm, label: e.target.value })}
                                            className="rounded-xl mt-1"
                                            data-testid={`balance-line-edit-label-${ln.id}`}
                                        />
                                    </div>
                                    <div className="w-28">
                                        <Label className="text-xs">Amount</Label>
                                        <Input
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            value={editForm.amount}
                                            onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })}
                                            className="rounded-xl mt-1"
                                            data-testid={`balance-line-edit-amount-${ln.id}`}
                                        />
                                    </div>
                                    <Button size="sm" onClick={() => saveLineEdit(ln.id)} disabled={busy} className="rounded-full" data-testid={`balance-line-save-${ln.id}`}>Save</Button>
                                    <Button size="sm" variant="outline" onClick={() => setEditingLineId(null)} className="rounded-full">Cancel</Button>
                                </div>
                            ) : (
                                <div className="flex items-center gap-3">
                                    <div className="flex-1 min-w-0">
                                        <div className="font-semibold truncate">{ln.label}</div>
                                        <div className="text-xs text-muted-foreground">
                                            Added {ln.created_at && format(parseISO(ln.created_at), "MMM d, yyyy")}
                                            {ln.created_by_name && ` by ${ln.created_by_name}`}
                                        </div>
                                    </div>
                                    <div className="font-heading font-bold tabular-nums">${ln.amount.toFixed(2)}</div>
                                    <div className="flex gap-1">
                                        <button
                                            onClick={() => { setEditingLineId(ln.id); setEditForm({ label: ln.label, amount: String(ln.amount) }); }}
                                            className="rounded-full p-1.5 hover:bg-muted text-slate-600"
                                            title="Edit"
                                            data-testid={`balance-line-edit-btn-${ln.id}`}
                                        >
                                            <Edit3 className="h-3.5 w-3.5" />
                                        </button>
                                        <button
                                            onClick={() => markPaid(ln.id)}
                                            disabled={busy}
                                            className="rounded-full p-1.5 hover:bg-emerald-100 text-emerald-700"
                                            title="Mark paid"
                                            data-testid={`balance-line-mark-paid-${ln.id}`}
                                        >
                                            <CheckCircle2 className="h-3.5 w-3.5" />
                                        </button>
                                        <button
                                            onClick={() => deleteLine(ln.id)}
                                            disabled={busy}
                                            className="rounded-full p-1.5 hover:bg-destructive/10 text-destructive"
                                            title="Delete"
                                            data-testid={`balance-line-delete-${ln.id}`}
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>

            {/* Add new line */}
            <div className="bg-card rounded-xl p-3 border border-dashed border-primary/40">
                <Label className="text-xs">Add a balance line</Label>
                <div className="flex flex-wrap gap-2 mt-1.5">
                    <Input
                        value={newLine.label}
                        onChange={(e) => setNewLine({ ...newLine, label: e.target.value })}
                        placeholder="e.g. 10-Year Anniversary Fee"
                        className="rounded-xl flex-1 min-w-[200px]"
                        data-testid="balance-new-line-label"
                    />
                    <Input
                        type="number"
                        step="0.01"
                        min="0"
                        value={newLine.amount}
                        onChange={(e) => setNewLine({ ...newLine, amount: e.target.value })}
                        placeholder="0.00"
                        className="rounded-xl w-28"
                        data-testid="balance-new-line-amount"
                    />
                    <Button
                        size="sm"
                        onClick={addLine}
                        disabled={busy}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid="balance-new-line-add"
                    >
                        Add
                    </Button>
                </div>
            </div>

            {/* Paid history */}
            {paidLines.length > 0 && (
                <details className="bg-muted/40 rounded-xl p-3" data-testid="balance-paid-history">
                    <summary className="text-xs font-bold uppercase tracking-wider text-muted-foreground cursor-pointer">
                        Payment history ({paidLines.length})
                    </summary>
                    <div className="mt-2 space-y-1.5">
                        {paidLines.map((ln) => (
                            <div key={ln.id} className="flex items-center justify-between text-xs" data-testid={`balance-paid-line-${ln.id}`}>
                                <div className="flex-1 min-w-0">
                                    <span className="font-semibold">{ln.label}</span>
                                    <span className="text-muted-foreground">
                                        {" "}· paid {ln.paid_at && format(parseISO(ln.paid_at), "MMM d, yyyy")}
                                        {ln.paid_by_name && ` by ${ln.paid_by_name}`}
                                        {ln.paid_via === "member_receipt" && " (member submitted receipt)"}
                                    </span>
                                </div>
                                <div className="tabular-nums shrink-0">${ln.amount.toFixed(2)}</div>
                            </div>
                        ))}
                    </div>
                </details>
            )}

            <div className="sr-only" data-testid="balance-member-name">{memberName}</div>
        </div>
    );
}
