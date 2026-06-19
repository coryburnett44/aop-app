import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { format, parseISO } from "date-fns";
import { MapPin, Users, Calendar, ArrowLeft, UserCheck, Trash2, Plus, X, UserPlus } from "lucide-react";
import { toast } from "sonner";
import PaidEventCheckout from "../components/PaidEventCheckout";

export default function EventDetail() {
    const { id } = useParams();
    const { user } = useAuth();
    const [event, setEvent] = useState(null);
    const [rsvps, setRsvps] = useState([]);
    const [subs, setSubs] = useState([]);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        const [ev, rs, sb] = await Promise.all([
            api.get(`/events/${id}`),
            api.get(`/events/${id}/rsvps`),
            api.get(`/events/${id}/sub-events`).catch(() => ({ data: [] })),
        ]);
        setEvent(ev.data);
        setRsvps(rs.data);
        setSubs(sb.data || []);
    };

    useEffect(() => {
        load().catch(() => {});
    }, [id]);

    const hasRsvped = user && rsvps.some((r) => r.user_id === user.id);
    const myRsvp = user && rsvps.find((r) => r.user_id === user.id);
    const myGuests = myRsvp?.guests || [];
    const allowsTickets = !!event?.allows_ticket_types;
    // Guests drafted before the member clicks RSVP. Lets them submit one
    // combined request (member + guests in the same POST) so they receive a
    // single confirmation email instead of two (RSVP → ticket; then later
    // guests → re-sent ticket).
    const [pendingGuests, setPendingGuests] = useState([]);

    async function rsvpWithGuests(guests, memberTicketType) {
        if (!user) { toast.error("Please log in to RSVP"); return; }
        setLoading(true);
        try {
            const { data } = await api.post(`/events/${id}/rsvp`, { guests, ticket_type: memberTicketType });
            toast.success(data.rsvped ? `You're going! 🎉${data.guests ? ` +${data.guests} guests` : ""} Ticket emailed.` : "RSVP removed");
            setPendingGuests([]);
            await load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Something went wrong");
        }
        setLoading(false);
    }

    async function toggleRsvp() {
        if (hasRsvped) { await rsvpWithGuests([], "general"); return; }
        await rsvpWithGuests(pendingGuests, "general");
    }

    async function updateGuests(guests) {
        if (!myRsvp) return;
        setLoading(true);
        try {
            await api.put(`/events/${id}/rsvp/guests`, { guests, ticket_type: myRsvp?.ticket_type || "general" });
            toast.success("Guest list updated — new ticket QRs sent");
            await load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Something went wrong");
        }
        setLoading(false);
    }

    if (!event)
        return (
            <div className="max-w-5xl mx-auto px-6 py-12">
                <div className="h-96 rounded-2xl bg-muted animate-pulse" />
            </div>
        );

    return (
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-10">
            <Link to="/events" className="text-sm text-muted-foreground hover:text-primary inline-flex items-center gap-1" data-testid="back-to-events">
                <ArrowLeft className="h-4 w-4" /> Back to events
            </Link>
            <div className="mt-4 relative rounded-3xl overflow-hidden bg-slate-900">
                {event.cover_image ? (
                    <img src={event.cover_image} alt={event.title} className="block w-full h-auto max-h-[600px] object-contain mx-auto" />
                ) : (
                    <div className="aspect-[21/9] bg-muted" />
                )}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 via-black/30 to-transparent p-6 sm:p-8 text-white">
                    <div className="text-xs uppercase tracking-wider bg-secondary/90 text-[hsl(34_8%_16%)] font-semibold inline-block rounded-full px-3 py-1 mb-3">
                        {event.category}
                    </div>
                    <h1 className="font-heading text-2xl sm:text-4xl lg:text-5xl font-bold tracking-tight drop-shadow">{event.title}</h1>
                </div>
                {event.cancelled && (
                    <div
                        className="absolute top-4 left-4 sm:top-6 sm:left-6 inline-flex items-center gap-2 rounded-full bg-red-600 text-white px-4 py-1.5 text-xs sm:text-sm font-bold uppercase tracking-wider shadow-lg ring-2 ring-white/30"
                        data-testid="event-cancelled-banner"
                    >
                        ● Cancelled
                    </div>
                )}
            </div>

            {event.cancelled && (
                <div
                    className="mt-6 rounded-2xl border-2 border-red-300 bg-red-50 p-5 text-red-900"
                    data-testid="event-cancelled-notice"
                >
                    <div className="font-heading font-bold text-lg">This event has been cancelled.</div>
                    {event.cancellation_note && (
                        <div className="text-sm mt-1 text-red-800">{event.cancellation_note}</div>
                    )}
                    <div className="text-xs text-red-700 mt-2 opacity-80">RSVPs are closed. The event remains on the calendar for reference.</div>
                </div>
            )}

            <div className="grid lg:grid-cols-[1fr_300px] gap-10 mt-8">
                <div>
                    <h2 className="font-heading text-xl font-semibold mb-3">About this event</h2>
                    <p className="text-base leading-relaxed text-foreground/80 whitespace-pre-wrap">{event.description}</p>
                </div>
                <aside className="bg-card rounded-2xl p-6 border border-border h-fit shadow-warm space-y-4" data-testid="event-sidebar">
                    <div className="flex items-start gap-3">
                        <Calendar className="h-5 w-5 mt-0.5 text-primary" />
                        <div>
                            <div className="font-medium">{format(parseISO(event.start_at), "EEEE, MMM d")}</div>
                            <div className="text-sm text-muted-foreground">
                                {format(parseISO(event.start_at), "h:mm a")}
                                {event.end_at && ` – ${format(parseISO(event.end_at), "h:mm a")}`}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-start gap-3">
                        <MapPin className="h-5 w-5 mt-0.5 text-primary" />
                        <div className="font-medium">{event.location || "TBA"}</div>
                    </div>
                    <div className="flex items-start gap-3">
                        <Users className="h-5 w-5 mt-0.5 text-primary" />
                        <div>
                            <div className="font-medium">{event.rsvp_count} going{event.guest_count > 0 ? ` + ${event.guest_count} guests` : ""}</div>
                            {event.capacity > 0 && (
                                <div className="text-sm text-muted-foreground">{Math.max(0, event.capacity - event.rsvp_count - (event.guest_count || 0))} spots left</div>
                            )}
                        </div>
                    </div>
                    {/* External ticket / payment link — opens in a new tab, no internal RSVP */}
                    {event.external_url && !event.cancelled && (
                        <a
                            href={event.external_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-full inline-flex items-center justify-center gap-2 rounded-full py-4 px-6 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold shadow-warm transition-colors"
                            data-testid="event-external-btn"
                        >
                            {event.external_button_label || "Get tickets"} ↗
                        </a>
                    )}
                    {/* Paid event — Zeffy checkout takes precedence over the free flow */}
                    {!event.external_url && event.is_paid && !hasRsvped && !event.cancelled && (
                        <PaidEventCheckout event={event} onPaid={() => load()} />
                    )}
                    {!event.external_url && !event.is_paid && !hasRsvped && allowsTickets && !event.cancelled && (
                        <MemberTicketPicker event={event} onRsvp={(tt) => rsvpWithGuests(pendingGuests, tt)} disabled={loading} />
                    )}
                    {!event.external_url && !event.is_paid && !hasRsvped && !allowsTickets && !event.cancelled && (
                        <Button
                            onClick={toggleRsvp}
                            disabled={loading}
                            className="w-full rounded-full py-6 bg-primary hover:bg-primary/90 shadow-warm"
                            data-testid="rsvp-btn"
                        >
                            {loading ? "Updating…" : (pendingGuests.length > 0 ? `RSVP — me + ${pendingGuests.length} guest${pendingGuests.length === 1 ? "" : "s"}` : "RSVP")}
                        </Button>
                    )}
                    {!hasRsvped && !event.cancelled && !event.external_url && !event.is_paid && (
                        <GuestManager
                            guests={pendingGuests}
                            onSave={async (guests) => setPendingGuests(guests)}
                            disabled={loading}
                            allowsTickets={allowsTickets}
                            pendingMode
                        />
                    )}
                    {event.cancelled && !hasRsvped && (
                        <Button
                            disabled
                            className="w-full rounded-full py-6 bg-muted text-muted-foreground cursor-not-allowed"
                            data-testid="rsvp-btn-cancelled"
                        >
                            RSVPs closed — cancelled
                        </Button>
                    )}
                    {hasRsvped && (
                        <Button
                            onClick={toggleRsvp}
                            disabled={loading}
                            className="w-full rounded-full py-6 bg-accent hover:bg-accent/90 text-accent-foreground"
                            data-testid="rsvp-btn"
                        >
                            {loading ? "Updating…" : `You're going (${(myRsvp?.ticket_type || "general").replace("_", " ")}) — cancel`}
                        </Button>
                    )}
                    {hasRsvped && !event.cancelled && (
                        <GuestManager guests={myGuests} onSave={updateGuests} disabled={loading} allowsTickets={allowsTickets} />
                    )}
                    {rsvps.length > 0 && (
                        <div>
                            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Going</div>
                            <div className="flex flex-wrap gap-1.5">
                                {rsvps.slice(0, 8).map((r) => (
                                    <span key={r.id} className="text-xs bg-muted rounded-full px-3 py-1">{r.user_name}</span>
                                ))}
                                {rsvps.length > 8 && <span className="text-xs text-muted-foreground px-3 py-1">+{rsvps.length - 8} more</span>}
                            </div>
                        </div>
                    )}
                    {user?.role === "admin" && !event.cancelled && (
                        <AdminRsvpForMemberDialog event={event} existingRsvps={rsvps} onAdded={load} allowsTickets={allowsTickets} />
                    )}
                </aside>
            </div>

            {/* Iter 38: Sub-events panel now ALWAYS renders for parent events (no parent_event_id)
                so admins can add sub-events from any main event, not just the anniversary tree.
                Members only see it when at least one sub-event exists. */}
            {(subs.length > 0 || (user?.role === "admin" && !event.parent_event_id)) && (
                <SubEventsPanel
                    subs={subs}
                    parentEvent={event}
                    isAdmin={user?.role === "admin"}
                    onChange={load}
                />
            )}

            {user?.role === "admin" && <CheckInPanel eventId={id} eventTitle={event.title} allowsTickets={event.allows_ticket_types} />}
        </div>
    );
}

function SubEventsPanel({ subs, parentEvent, isAdmin = false, onChange }) {
    const [creating, setCreating] = useState(false);
    return (
        <section className="mt-10 bg-card rounded-3xl border border-border p-6 shadow-warm" data-testid="sub-events-panel">
            <div className="flex items-start justify-between gap-3 mb-1">
                <div>
                    <h2 className="font-heading text-2xl font-bold">Sub-events</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        RSVP separately for each sub-event. Bring guests too — admins assign ticket types at the door.
                    </p>
                </div>
                {isAdmin && (
                    <button
                        type="button"
                        onClick={() => setCreating((v) => !v)}
                        className="rounded-full px-3 py-1.5 text-xs font-bold uppercase tracking-wider border-2 border-primary text-primary hover:bg-primary hover:text-white transition-colors shrink-0"
                        data-testid="sub-event-toggle-create"
                    >
                        {creating ? "Close" : "+ Create sub-event"}
                    </button>
                )}
            </div>
            {creating && (
                <SubEventCreateForm
                    parentEvent={parentEvent}
                    onCreated={() => { setCreating(false); onChange?.(); }}
                />
            )}
            <div className="grid sm:grid-cols-2 gap-4 mt-4">
                {subs.length === 0 && !creating && (
                    <div className="col-span-full text-sm text-muted-foreground italic">No sub-events yet.{isAdmin ? " Use the + button above to add one." : ""}</div>
                )}
                {subs.map((s) => (
                    <SubEventCard key={s.id} sub={s} isAdmin={isAdmin} onChange={onChange} />
                ))}
            </div>
        </section>
    );
}

function SubEventCreateForm({ parentEvent, onCreated }) {
    return (
        <SubEventForm
            parentEvent={parentEvent}
            onDone={onCreated}
            submitLabel="Create sub-event"
        />
    );
}

function SubEventForm({ parentEvent, existing, onDone, onCancel, submitLabel }) {
    const isEdit = !!existing;
    const [title, setTitle] = useState(existing?.title || "");
    const [category, setCategory] = useState(existing?.category || "general");
    const [startAt, setStartAt] = useState(
        existing?.start_at ? existing.start_at.slice(0, 16)
            : (parentEvent?.start_at ? parentEvent.start_at.slice(0, 16) : "")
    );
    const [endAt, setEndAt] = useState(existing?.end_at ? existing.end_at.slice(0, 16) : "");
    const [location, setLocation] = useState(existing?.location ?? parentEvent?.location ?? "");
    const [allowsTicketTypes, setAllowsTicketTypes] = useState(!!existing?.allows_ticket_types);
    const [busy, setBusy] = useState(false);

    async function submit(e) {
        e.preventDefault();
        if (!title.trim()) { toast.error("Title is required"); return; }
        if (!startAt) { toast.error("Start time is required"); return; }
        setBusy(true);
        try {
            const payload = {
                title: title.trim(),
                location: location.trim(),
                start_at: new Date(startAt).toISOString(),
                end_at: endAt ? new Date(endAt).toISOString() : null,
                category: category.trim() || "general",
                allows_ticket_types: !!allowsTicketTypes,
            };
            if (isEdit) {
                await api.put(`/events/${existing.id}`, payload);
                toast.success("Sub-event updated");
            } else {
                await api.post("/events", {
                    ...payload,
                    description: "",
                    capacity: 0,
                    cover_image: "",
                    parent_event_id: parentEvent.id,
                });
                toast.success("Sub-event created");
                setTitle(""); setEndAt("");
            }
            onDone?.();
        } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <form onSubmit={submit} className="rounded-2xl border-2 border-dashed border-primary/40 bg-primary/[0.04] p-4 mt-3 space-y-3" data-testid={isEdit ? "sub-event-edit-form" : "sub-event-create-form"}>
            <div className="grid sm:grid-cols-[2fr_1fr] gap-3">
                <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Title</label>
                    <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Welcome reception" className="mt-1 w-full rounded-xl border border-border px-3 py-2 text-sm" data-testid="sub-event-title" />
                </div>
                <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Category</label>
                    <input type="text" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="general / workshop / mixer" className="mt-1 w-full rounded-xl border border-border px-3 py-2 text-sm" data-testid="sub-event-category" />
                </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
                <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Starts</label>
                    <input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} className="mt-1 w-full rounded-xl border border-border px-3 py-2 text-sm" data-testid="sub-event-start" />
                </div>
                <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Ends <span className="font-normal normal-case">(optional)</span></label>
                    <input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} className="mt-1 w-full rounded-xl border border-border px-3 py-2 text-sm" data-testid="sub-event-end" />
                </div>
            </div>
            <div>
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</label>
                <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} className="mt-1 w-full rounded-xl border border-border px-3 py-2 text-sm" data-testid="sub-event-location" />
            </div>
            <label className="flex items-center gap-2 text-sm">
                <input
                    type="checkbox"
                    checked={allowsTicketTypes}
                    onChange={(e) => setAllowsTicketTypes(e.target.checked)}
                    className="h-4 w-4"
                    data-testid="sub-event-allows-tickets"
                />
                Allow ticket types (VIP / All Access / General Admission)
            </label>
            <div className="flex items-center gap-2 pt-1">
                <button type="submit" disabled={busy} className="rounded-full bg-primary text-white px-5 py-2 text-sm font-bold hover:bg-primary/90 disabled:opacity-50" data-testid="sub-event-submit">
                    {busy ? (isEdit ? "Saving…" : "Creating…") : (submitLabel || (isEdit ? "Save changes" : "Create sub-event"))}
                </button>
                {onCancel && (
                    <button type="button" onClick={onCancel} className="rounded-full px-4 py-2 text-sm font-semibold border border-border hover:bg-muted">
                        Cancel
                    </button>
                )}
            </div>
        </form>
    );
}

function SubEventCard({ sub, isAdmin, onChange }) {
    const [editing, setEditing] = useState(false);

    async function del(e) {
        e.preventDefault();
        e.stopPropagation();
        if (!confirm(`Delete sub-event "${sub.title}"? This cannot be undone.`)) return;
        try {
            await api.delete(`/events/${sub.id}`);
            toast.success("Sub-event deleted");
            onChange?.();
        } catch (err) { toast.error(err.response?.data?.detail || "Delete failed"); }
    }

    return (
        <div className="rounded-2xl border border-border bg-muted/30 overflow-hidden hover:border-primary/40 hover:bg-muted/60 transition-colors" data-testid={`sub-event-${sub.id}`}>
            <Link to={`/events/${sub.id}`} className="block p-5">
                <div className="text-xs uppercase tracking-wider font-semibold text-primary mb-1">{sub.category}</div>
                <div className="font-heading text-lg font-bold leading-tight">{sub.title}</div>
                <div className="text-xs text-muted-foreground mt-1.5">
                    {format(parseISO(sub.start_at), "EEE, MMM d · h:mm a")}
                </div>
                <div className="text-xs mt-2 flex items-center gap-3">
                    <span><Users className="h-3 w-3 inline mr-1" />{sub.rsvp_count} going{sub.guest_count > 0 ? ` +${sub.guest_count} guests` : ""}</span>
                    {sub.allows_ticket_types && <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary">Tickets</span>}
                </div>
            </Link>
            {isAdmin && (
                <div className="flex items-center gap-2 px-5 pb-4 -mt-1">
                    <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setEditing(true); }}
                        className="rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-wider border border-primary text-primary hover:bg-primary hover:text-white transition-colors"
                        data-testid={`sub-event-edit-${sub.id}`}
                    >
                        Edit
                    </button>
                    <button
                        type="button"
                        onClick={del}
                        className="rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-wider border border-destructive text-destructive hover:bg-destructive hover:text-white transition-colors"
                        data-testid={`sub-event-delete-${sub.id}`}
                    >
                        Delete
                    </button>
                </div>
            )}
            <Dialog open={editing} onOpenChange={setEditing}>
                <DialogContent className="max-w-xl">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">Edit sub-event</DialogTitle>
                    </DialogHeader>
                    <SubEventForm
                        existing={sub}
                        onDone={() => { setEditing(false); onChange?.(); }}
                        onCancel={() => setEditing(false)}
                    />
                </DialogContent>
            </Dialog>
        </div>
    );
}

function _SubEventsPanelLegacy_REMOVED() { return null; }

function MemberTicketPicker({ event, onRsvp, disabled }) {
    // Use the admin-selected subset of ticket types if present; otherwise fall back
    // to the legacy default trio (vip/all_access/general).
    const enabled = (event?.enabled_ticket_types && event.enabled_ticket_types.length > 0)
        ? event.enabled_ticket_types
        : ["vip", "all_access", "general"];
    const [tt, setTt] = useState(enabled[0]);
    useEffect(() => { if (!enabled.includes(tt)) setTt(enabled[0]); /* eslint-disable-next-line */ }, [event?.id]);
    return (
        <div className="border-2 border-primary/20 rounded-2xl p-3 bg-primary/5 space-y-2" data-testid="member-ticket-picker">
            <Label className="text-xs">Your ticket type</Label>
            <Select value={tt} onValueChange={setTt}>
                <SelectTrigger className="rounded-xl text-sm" data-testid="member-ticket-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                    {enabled.map((t) => (
                        <SelectItem key={t} value={t} className="capitalize">{t.replace("_", " ")}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
            <Button
                onClick={() => onRsvp(tt)}
                disabled={disabled}
                className="w-full rounded-full py-6 bg-primary hover:bg-primary/90 shadow-warm"
                data-testid="rsvp-btn"
            >
                {disabled ? "Updating…" : "RSVP — email me my ticket"}
            </Button>
        </div>
    );
}

/**
 * Admin-only inline RSVP creator. Lets an admin pick any member by name/email
 * search and RSVP them — optionally with guest names + ticket type + email
 * suppression flag (for back-filling historic attendance without spamming the
 * member). One combined call hits POST /events/{id}/admin-rsvp so the target
 * member gets exactly one digital-ticket email (or none) just like the new
 * member-side combined flow.
 */
function AdminRsvpForMemberDialog({ event, existingRsvps, onAdded, allowsTickets }) {
    const [open, setOpen] = useState(false);
    const [members, setMembers] = useState([]);
    const [query, setQuery] = useState("");
    const [selectedId, setSelectedId] = useState("");
    const [ticketType, setTicketType] = useState("general");
    const [guests, setGuests] = useState([]);
    const [sendEmail, setSendEmail] = useState(true);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open || members.length) return;
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
    }, [open, members.length]);

    const rsvpedIds = new Set((existingRsvps || []).map((r) => r.user_id));
    const filtered = (members || [])
        .filter((m) => !rsvpedIds.has(m.id))
        .filter((m) => {
            const q = query.trim().toLowerCase();
            if (!q) return true;
            return (m.name || "").toLowerCase().includes(q) || (m.email || "").toLowerCase().includes(q);
        })
        .slice(0, 50);

    function addGuestRow() { setGuests([...guests, { name: "", email: "", phone: "", ticket_type: allowsTickets ? "general" : "guest" }]); }
    function removeGuest(i) { setGuests(guests.filter((_, idx) => idx !== i)); }
    function updateGuest(i, field, val) { setGuests(guests.map((g, idx) => idx === i ? { ...g, [field]: val } : g)); }

    async function submit(e) {
        e.preventDefault();
        if (!selectedId) { toast.error("Pick a member first"); return; }
        const cleanGuests = guests.filter((g) => g.name?.trim()).map((g) => ({
            name: g.name.trim(),
            email: g.email?.trim() || "",
            phone: g.phone?.trim() || "",
            ticket_type: g.ticket_type || (allowsTickets ? "general" : "guest"),
        }));
        setBusy(true);
        try {
            const { data } = await api.post(`/events/${event.id}/admin-rsvp`, {
                user_id: selectedId,
                ticket_type: ticketType,
                guests: cleanGuests,
                send_email: sendEmail,
            });
            toast.success(
                `${data.user_name} is going!${data.guests ? ` +${data.guests} guests.` : ""}${data.email_sent ? " Ticket emailed." : " Email suppressed."}`,
            );
            setOpen(false);
            setSelectedId(""); setGuests([]); setQuery(""); setTicketType("general"); setSendEmail(true);
            onAdded?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Could not RSVP this member");
        }
        setBusy(false);
    }

    return (
        <div className="border-t border-dashed border-primary/40 pt-3 mt-1" data-testid="admin-rsvp-section">
            <div className="text-[10px] uppercase tracking-widest font-bold text-primary mb-1.5">Admin tools</div>
            <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(true)}
                className="w-full rounded-full border-primary text-primary hover:bg-primary hover:text-white"
                data-testid="admin-add-rsvp-btn"
            >
                <Plus className="h-4 w-4 mr-1.5" /> RSVP a member + guests
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">RSVP a member for this event</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={submit} className="space-y-4 mt-2" data-testid="admin-rsvp-form">
                        <div>
                            <Label>Member *</Label>
                            <Input
                                placeholder="Search by name or email…"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid="admin-rsvp-member-search"
                            />
                            <div className="mt-1.5 max-h-44 overflow-y-auto rounded-xl border border-border bg-card divide-y divide-border" data-testid="admin-rsvp-member-list">
                                {filtered.length === 0 ? (
                                    <div className="px-3 py-3 text-xs text-muted-foreground italic">{members.length === 0 ? "Loading members…" : (rsvpedIds.size > 0 ? "All matching members already have RSVPs." : "No members match.")}</div>
                                ) : filtered.map((m) => (
                                    <label key={m.id} className={`flex items-center gap-2 px-3 py-2 cursor-pointer text-sm hover:bg-muted/40 ${selectedId === m.id ? "bg-primary/5" : ""}`} data-testid={`admin-rsvp-member-row-${m.id}`}>
                                        <input type="radio" name="admin-rsvp-pick" checked={selectedId === m.id} onChange={() => setSelectedId(m.id)} className="h-4 w-4 accent-primary shrink-0" data-testid={`admin-rsvp-member-radio-${m.id}`} />
                                        <span className="font-medium truncate">{m.name}</span>
                                        {m.email && <span className="text-xs text-muted-foreground truncate">· {m.email}</span>}
                                    </label>
                                ))}
                            </div>
                        </div>
                        {allowsTickets && (
                            <div>
                                <Label>Member ticket type</Label>
                                <Select value={ticketType} onValueChange={setTicketType}>
                                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="admin-rsvp-ticket-type"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="vip">VIP</SelectItem>
                                        <SelectItem value="all_access">All Access</SelectItem>
                                        <SelectItem value="general">General Admission</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                        <div>
                            <div className="flex items-center justify-between mb-2">
                                <Label className="text-xs uppercase tracking-wider">Guests ({guests.length})</Label>
                                <button type="button" onClick={addGuestRow} className="text-primary hover:underline text-xs font-medium" data-testid="admin-rsvp-add-guest">
                                    <UserPlus className="h-3 w-3 inline mr-1" />Add guest
                                </button>
                            </div>
                            {guests.length === 0 && <div className="text-[11px] italic text-muted-foreground">No guests. Add one above if needed.</div>}
                            <div className="space-y-2">
                                {guests.map((g, i) => (
                                    <div key={i} className="border border-border rounded-xl p-3 space-y-2 relative" data-testid={`admin-rsvp-guest-row-${i}`}>
                                        <button type="button" onClick={() => removeGuest(i)} className="absolute top-2 right-2 text-muted-foreground hover:text-destructive" data-testid={`admin-rsvp-remove-guest-${i}`}>
                                            <X className="h-4 w-4" />
                                        </button>
                                        <Input placeholder="Guest name *" value={g.name} onChange={(e) => updateGuest(i, "name", e.target.value)} className="rounded-xl" data-testid={`admin-rsvp-guest-name-${i}`} />
                                        <div className="grid grid-cols-2 gap-2">
                                            <Input placeholder="Email (optional)" value={g.email || ""} onChange={(e) => updateGuest(i, "email", e.target.value)} className="rounded-xl text-sm" data-testid={`admin-rsvp-guest-email-${i}`} />
                                            <Input placeholder="Phone (optional)" value={g.phone || ""} onChange={(e) => updateGuest(i, "phone", e.target.value)} className="rounded-xl text-sm" data-testid={`admin-rsvp-guest-phone-${i}`} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <label className="flex items-center gap-2 text-sm" data-testid="admin-rsvp-send-email-label">
                            <input
                                type="checkbox"
                                checked={sendEmail}
                                onChange={(e) => setSendEmail(e.target.checked)}
                                className="h-4 w-4 accent-primary"
                                data-testid="admin-rsvp-send-email-toggle"
                            />
                            <span>Email the digital ticket to the member <span className="text-xs text-muted-foreground">(uncheck to back-fill silently)</span></span>
                        </label>
                        <Button type="submit" disabled={busy || !selectedId} className="w-full rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="admin-rsvp-submit">
                            {busy ? "Saving…" : `Confirm RSVP${guests.length ? ` + ${guests.length} guest${guests.length === 1 ? "" : "s"}` : ""}`}
                        </Button>
                    </form>
                </DialogContent>
            </Dialog>
        </div>
    );
}


function GuestManager({ guests, onSave, disabled, allowsTickets, pendingMode }) {
    const [open, setOpen] = useState(false);
    const [list, setList] = useState(guests || []);
    useEffect(() => { setList(guests || []); }, [guests]);

    function add() { setList([...list, { name: "", email: "", phone: "", ticket_type: allowsTickets ? "general" : "guest" }]); }
    function remove(i) { setList(list.filter((_, idx) => idx !== i)); }
    function update(i, field, val) { setList(list.map((g, idx) => idx === i ? { ...g, [field]: val } : g)); }

    async function save() {
        const cleaned = list.filter((g) => g.name?.trim()).map((g) => ({
            name: g.name.trim(),
            email: g.email?.trim() || "",
            phone: g.phone?.trim() || "",
            ticket_type: g.ticket_type || (allowsTickets ? "general" : "guest"),
        }));
        await onSave(cleaned);
        setOpen(false);
    }

    return (
        <div className={`${pendingMode ? "" : "border-t border-border/40 pt-3 mt-1"}`} data-testid="guest-manager">
            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2 flex items-center justify-between">
                <span>{pendingMode ? `Add guests before you RSVP (${(guests || []).length})` : `Your guests (${(guests || []).length})`}</span>
                <button onClick={() => setOpen(true)} className="text-primary hover:underline normal-case tracking-normal text-xs font-medium" data-testid="manage-guests-btn">
                    <UserPlus className="h-3 w-3 inline mr-1" />{(guests || []).length > 0 ? "Edit" : "Add"}
                </button>
            </div>
            {pendingMode && (guests || []).length === 0 && (
                <div className="text-[11px] text-muted-foreground italic leading-relaxed -mt-1 mb-2">
                    Bringing a +1? Add them now — you'll get one combined ticket email when you RSVP (instead of two separate emails).
                </div>
            )}
            {(guests || []).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                    {(guests || []).map((g, i) => (
                        <span key={i} className="text-xs bg-accent/40 rounded-full px-3 py-1" data-testid={`guest-pill-${i}`}>
                            {g.name}
                            {g.ticket_type && g.ticket_type !== "guest" && allowsTickets ? ` · ${g.ticket_type.replace("_", " ")}` : ""}
                        </span>
                    ))}
                </div>
            )}
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
                    <DialogHeader><DialogTitle className="font-heading text-2xl">{pendingMode ? "Add guests" : "Manage your guests"}</DialogTitle></DialogHeader>
                    <p className="text-xs text-muted-foreground -mt-1">
                        {pendingMode
                            ? "Each guest gets their own QR ticket inside your single confirmation email after you RSVP."
                            : "Each guest receives their own QR ticket inside your confirmation email. Updating the list re-sends the email."}
                    </p>
                    <div className="space-y-3 mt-3">
                        {list.length === 0 && <div className="text-sm text-muted-foreground italic">No guests yet — add one below.</div>}
                        {list.map((g, i) => (
                            <div key={i} className="border border-border rounded-xl p-3 space-y-2 relative" data-testid={`guest-row-${i}`}>
                                <button onClick={() => remove(i)} className="absolute top-2 right-2 text-muted-foreground hover:text-destructive" data-testid={`remove-guest-${i}`}>
                                    <X className="h-4 w-4" />
                                </button>
                                <Input placeholder="Guest name *" value={g.name} onChange={(e) => update(i, "name", e.target.value)} className="rounded-xl" data-testid={`guest-name-${i}`} />
                                <div className="grid grid-cols-2 gap-2">
                                    <Input placeholder="Email (optional)" value={g.email || ""} onChange={(e) => update(i, "email", e.target.value)} className="rounded-xl text-sm" data-testid={`guest-email-${i}`} />
                                    <Input placeholder="Phone (optional)" value={g.phone || ""} onChange={(e) => update(i, "phone", e.target.value)} className="rounded-xl text-sm" data-testid={`guest-phone-${i}`} />
                                </div>
                                {allowsTickets && (
                                    <div>
                                        <Label className="text-xs">Ticket type for this guest</Label>
                                        <Select value={g.ticket_type || "general"} onValueChange={(v) => update(i, "ticket_type", v)}>
                                            <SelectTrigger className="rounded-xl mt-1 text-sm" data-testid={`guest-ticket-type-${i}`}><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="vip">VIP</SelectItem>
                                                <SelectItem value="all_access">All Access</SelectItem>
                                                <SelectItem value="general">General Admission</SelectItem>
                                                <SelectItem value="guest">Guest</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                )}
                            </div>
                        ))}
                        <Button variant="outline" onClick={add} className="w-full rounded-full" data-testid="add-guest-btn">
                            <Plus className="h-4 w-4 mr-1" /> Add guest
                        </Button>
                    </div>
                    <DialogFooter className="mt-4">
                        <Button onClick={save} disabled={disabled} className="rounded-full bg-primary hover:bg-primary/90" data-testid="save-guests-btn">Save</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

function CheckInPanel({ eventId, eventTitle, allowsTickets }) {
    const [checkins, setCheckins] = useState([]);
    const [members, setMembers] = useState([]);

    const load = () => api.get(`/events/${eventId}/check-ins`).then(({ data }) => setCheckins(data));
    useEffect(() => {
        load().catch(() => {});
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
    }, [eventId]);

    const checkedInIds = new Set(checkins.filter((c) => c.user_id).map((c) => c.user_id));
    const totals = checkins.reduce((acc, c) => { acc[c.ticket_type] = (acc[c.ticket_type] || 0) + 1; return acc; }, {});

    async function remove(id) {
        if (!confirm("Remove this check-in?")) return;
        await api.delete(`/events/${eventId}/check-ins/${id}`);
        toast.success("Removed");
        load();
    }

    return (
        <section className="mt-12 bg-card rounded-3xl border-2 border-primary/20 p-6 shadow-warm" data-testid="checkin-panel">
            <div className="flex items-end justify-between gap-3 flex-wrap mb-5">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] font-bold text-primary">Admin · Event Check-In</div>
                    <h2 className="font-heading text-2xl font-black mt-1">{checkins.length} checked in</h2>
                    <div className="text-xs text-muted-foreground mt-1">
                        {["vip", "all_access", "general", "guest", "speaker", "volunteer"].map((t) => totals[t] ? `${totals[t]} ${t.replace("_", " ")}` : null).filter(Boolean).join(" · ") || "No check-ins yet"}
                    </div>
                </div>
                <CheckInDialog eventId={eventId} eventTitle={eventTitle} members={members} checkedInIds={checkedInIds} allowsTickets={allowsTickets} onDone={load} />
            </div>
            {checkins.length === 0 ? (
                <div className="text-sm text-muted-foreground py-6 text-center">No check-ins yet. Add the first attendee.</div>
            ) : (
                <div className="space-y-2">
                    {checkins.map((c) => (
                        <div key={c.id} className="flex items-center gap-3 p-3 bg-muted/40 rounded-xl" data-testid={`checkin-${c.id}`}>
                            <div className={`w-10 h-10 rounded-full grid place-items-center text-white font-bold text-sm shrink-0 ${c.ticket_type === "vip" ? "bg-yellow-600" : c.ticket_type === "guest" ? "bg-slate-500" : "bg-primary"}`}>
                                {(c.user_name || "?")[0]?.toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="font-medium truncate">{c.user_name}</div>
                                <div className="text-xs text-muted-foreground">{format(parseISO(c.checked_in_at), "MMM d · h:mm a")} · by {c.checked_in_by_name}</div>
                            </div>
                            <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2.5 py-1 bg-card border">
                                {c.ticket_type}
                            </span>
                            <button onClick={() => remove(c.id)} className="text-muted-foreground hover:text-destructive" data-testid={`remove-checkin-${c.id}`}>
                                <Trash2 className="h-4 w-4" />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
}

function CheckInDialog({ eventId, eventTitle, members, checkedInIds, allowsTickets, onDone }) {
    const [open, setOpen] = useState(false);
    const [mode, setMode] = useState("member");
    const [userId, setUserId] = useState("");
    const [guestName, setGuestName] = useState("");
    const [ticketType, setTicketType] = useState("general");
    const [search, setSearch] = useState("");

    async function submit() {
        try {
            const payload = { ticket_type: ticketType };
            if (mode === "member") {
                if (!userId) { toast.error("Pick a member"); return; }
                payload.user_id = userId;
            } else {
                if (!guestName.trim()) { toast.error("Enter a guest name"); return; }
                payload.guest_name = guestName.trim();
            }
            await api.post(`/events/${eventId}/check-in`, payload);
            toast.success("Checked in ✅");
            setUserId(""); setGuestName(""); setSearch(""); setTicketType("general"); setMode("member");
            setOpen(false);
            onDone();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    const filtered = members.filter((m) => {
        if (checkedInIds.has(m.id)) return false;
        if (!search) return true;
        const q = search.toLowerCase();
        return m.name?.toLowerCase().includes(q) || m.email?.toLowerCase().includes(q) || m.line_name?.toLowerCase().includes(q);
    }).slice(0, 30);

    return (
        <>
            <Button onClick={() => setOpen(true)} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="add-checkin-btn">
                <UserCheck className="h-4 w-4 mr-1.5" /> Check in
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
                    <DialogHeader><DialogTitle className="font-heading text-2xl">Check in to "{eventTitle}"</DialogTitle></DialogHeader>
                    <div className="space-y-4 mt-2">
                        <div className="flex gap-2">
                            <button onClick={() => setMode("member")} className={`flex-1 rounded-full py-2 text-sm font-semibold ${mode === "member" ? "bg-primary text-white shadow-warm" : "bg-muted"}`} data-testid="checkin-mode-member">Member</button>
                            <button onClick={() => setMode("guest")} className={`flex-1 rounded-full py-2 text-sm font-semibold ${mode === "guest" ? "bg-primary text-white shadow-warm" : "bg-muted"}`} data-testid="checkin-mode-guest">Guest</button>
                        </div>
                        {mode === "member" ? (
                            <div>
                                <Input placeholder="Search by name or email…" value={search} onChange={(e) => setSearch(e.target.value)} className="rounded-xl" data-testid="checkin-search" />
                                <div className="max-h-56 overflow-y-auto mt-2 border border-border rounded-xl">
                                    {filtered.length === 0 ? (
                                        <div className="p-4 text-sm text-muted-foreground text-center">No matching members (already checked in are hidden).</div>
                                    ) : filtered.map((m) => (
                                        <button
                                            key={m.id}
                                            onClick={() => setUserId(m.id)}
                                            className={`w-full text-left px-3 py-2 hover:bg-muted/60 border-b last:border-0 ${userId === m.id ? "bg-primary/10" : ""}`}
                                            data-testid={`checkin-pick-${m.id}`}
                                        >
                                            <div className="text-sm font-medium">{m.name}</div>
                                            <div className="text-xs text-muted-foreground">{m.email}</div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div>
                                <Label>Guest name</Label>
                                <Input value={guestName} onChange={(e) => setGuestName(e.target.value)} placeholder="John Doe" className="rounded-xl mt-1.5" data-testid="checkin-guest-name" />
                            </div>
                        )}
                        <div>
                            <Label>Ticket type</Label>
                            <Select value={ticketType} onValueChange={setTicketType}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="checkin-ticket-type"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {allowsTickets && <SelectItem value="vip">VIP</SelectItem>}
                                    {allowsTickets && <SelectItem value="all_access">All Access</SelectItem>}
                                    <SelectItem value="general">General Admission</SelectItem>
                                    {!allowsTickets && <SelectItem value="vip">VIP</SelectItem>}
                                    <SelectItem value="guest">Guest</SelectItem>
                                    <SelectItem value="speaker">Speaker</SelectItem>
                                    <SelectItem value="volunteer">Volunteer</SelectItem>
                                </SelectContent>
                            </Select>
                            {allowsTickets && <p className="text-[11px] text-muted-foreground mt-1">VIP / All Access / General Admission are available for this sub-event.</p>}
                        </div>
                    </div>
                    <DialogFooter className="mt-4"><Button onClick={submit} className="rounded-full bg-primary hover:bg-primary/90" data-testid="checkin-confirm-btn">Check in</Button></DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
