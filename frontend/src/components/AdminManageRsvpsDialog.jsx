/**
 * Admin manage-RSVPs dialog — opens from an event detail page.
 *
 * Shows every RSVP on the event with:
 *   - the member's name + ticket type
 *   - their guests listed underneath (with per-guest "remove" button)
 *   - a per-row "Un-RSVP" button that removes the member + all their guests
 *
 * Confirms destructive actions with a browser confirm() (no network call to
 * a separate confirm modal — admins use this rarely and the dialog is already
 * modal). After every mutation we refetch the full list so the UI stays in
 * sync (counts, remaining guests). Parent receives `onChanged()` to refresh
 * the event card's attendance numbers.
 */
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { api } from "../lib/api";
import { toast } from "sonner";
import { UserMinus, Trash2, Search } from "lucide-react";

export default function AdminManageRsvpsDialog({ event, onChanged }) {
    const [open, setOpen] = useState(false);
    const [rows, setRows] = useState([]);
    const [busy, setBusy] = useState(false);
    const [q, setQ] = useState("");

    async function load() {
        try {
            const { data } = await api.get(`/events/${event.id}/rsvps`);
            setRows(data || []);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to load RSVPs");
        }
    }
    useEffect(() => { if (open) load(); }, [open, event.id]);  // eslint-disable-line react-hooks/exhaustive-deps

    async function unRsvp(r) {
        const guestCount = (r.guests || []).length;
        const msg = guestCount
            ? `Un-RSVP ${r.user_name} and remove all ${guestCount} guest${guestCount === 1 ? "" : "s"}?\n\nThis cannot be undone. Their check-in record (if any) will also be removed. Payment transactions are NOT refunded — handle separately if needed.`
            : `Un-RSVP ${r.user_name}?\n\nThis cannot be undone.`;
        if (!window.confirm(msg)) return;
        setBusy(true);
        try {
            const { data } = await api.delete(`/events/${event.id}/rsvps/${r.user_id}`);
            const removed = (data.guests_removed || 0) + 1;
            toast.success(`Removed ${r.user_name}${data.guests_removed ? ` + ${data.guests_removed} guest${data.guests_removed === 1 ? "" : "s"}` : ""}`);
            await load();
            if (onChanged) onChanged();
            void removed;
        } catch (e) {
            toast.error(e.response?.data?.detail || "Un-RSVP failed");
        }
        setBusy(false);
    }

    async function removeGuest(r, g) {
        if (!window.confirm(`Remove guest "${g.name || "(no name)"}" from ${r.user_name}'s RSVP?\n\nThe guest's check-in (if any) will also be removed.`)) return;
        setBusy(true);
        try {
            await api.delete(`/events/${event.id}/rsvps/${r.user_id}/guests/${g.ticket_id}`);
            toast.success(`Removed guest "${g.name || "(no name)"}"`);
            await load();
            if (onChanged) onChanged();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Remove guest failed");
        }
        setBusy(false);
    }

    const needle = q.trim().toLowerCase();
    const filtered = needle
        ? rows.filter((r) => {
            if ((r.user_name || "").toLowerCase().includes(needle)) return true;
            return (r.guests || []).some((g) => (g.name || "").toLowerCase().includes(needle));
        })
        : rows;

    const totalGuests = rows.reduce((s, r) => s + ((r.guests || []).length), 0);

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm" className="rounded-full" data-testid="admin-manage-rsvps-trigger">
                    Manage RSVPs
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="admin-manage-rsvps-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading">Manage RSVPs — {event.title}</DialogTitle>
                </DialogHeader>
                <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="text-sm text-muted-foreground">
                        <strong>{rows.length}</strong> RSVP{rows.length === 1 ? "" : "s"} · <strong>{totalGuests}</strong> guest{totalGuests === 1 ? "" : "s"} · <strong>{rows.length + totalGuests}</strong> total attendees
                    </div>
                    <div className="relative">
                        <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                        <Input
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            placeholder="Search member or guest…"
                            className="rounded-full pl-8 w-64 h-8 text-sm"
                            data-testid="admin-rsvps-search"
                        />
                    </div>
                </div>
                {filtered.length === 0 ? (
                    <div className="text-sm italic text-muted-foreground py-6 text-center" data-testid="admin-rsvps-empty">
                        {rows.length === 0 ? "No RSVPs for this event yet." : "No matches."}
                    </div>
                ) : (
                    <div className="space-y-2">
                        {filtered.map((r) => (
                            <div key={r.id} className="rounded-xl border border-border bg-card p-3" data-testid={`admin-rsvp-row-${r.user_id}`}>
                                <div className="flex items-center gap-3">
                                    <div className="flex-1 min-w-0">
                                        <div className="font-semibold truncate">{r.user_name}</div>
                                        <div className="text-xs text-muted-foreground">
                                            {r.ticket_type ? <span className="uppercase tracking-wider mr-2">{(r.ticket_type || "general").replace("_", " ")}</span> : null}
                                            {(r.guests || []).length} guest{(r.guests || []).length === 1 ? "" : "s"}
                                        </div>
                                    </div>
                                    <Button
                                        size="sm"
                                        variant="destructive"
                                        onClick={() => unRsvp(r)}
                                        disabled={busy}
                                        className="rounded-full"
                                        data-testid={`admin-un-rsvp-${r.user_id}`}
                                    >
                                        <UserMinus className="h-3.5 w-3.5 mr-1" /> Un-RSVP
                                    </Button>
                                </div>
                                {(r.guests || []).length > 0 && (
                                    <div className="mt-2 pl-4 border-l-2 border-muted space-y-1.5">
                                        {(r.guests || []).map((g) => (
                                            <div key={g.ticket_id} className="flex items-center gap-2" data-testid={`admin-guest-${g.ticket_id}`}>
                                                <div className="flex-1 min-w-0 text-sm">
                                                    <span className="font-medium">{g.name || <em className="text-muted-foreground">(no name)</em>}</span>
                                                    {g.ticket_type && g.ticket_type !== "general" && (
                                                        <span className="ml-2 text-[10px] uppercase tracking-wider font-bold rounded-full px-1.5 py-0.5 bg-primary/10 text-primary">{g.ticket_type.replace("_", " ")}</span>
                                                    )}
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => removeGuest(r, g)}
                                                    disabled={busy}
                                                    className="rounded-full p-1.5 hover:bg-destructive/10 text-destructive disabled:opacity-50"
                                                    title="Remove guest"
                                                    data-testid={`admin-remove-guest-${g.ticket_id}`}
                                                >
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
