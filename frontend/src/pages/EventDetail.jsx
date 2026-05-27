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
import { MapPin, Users, Calendar, ArrowLeft, UserCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function EventDetail() {
    const { id } = useParams();
    const { user } = useAuth();
    const [event, setEvent] = useState(null);
    const [rsvps, setRsvps] = useState([]);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        const [ev, rs] = await Promise.all([api.get(`/events/${id}`), api.get(`/events/${id}/rsvps`)]);
        setEvent(ev.data);
        setRsvps(rs.data);
    };

    useEffect(() => {
        load().catch(() => {});
    }, [id]);

    const hasRsvped = user && rsvps.some((r) => r.user_id === user.id);

    async function toggleRsvp() {
        if (!user) {
            toast.error("Please log in to RSVP");
            return;
        }
        setLoading(true);
        try {
            const { data } = await api.post(`/events/${id}/rsvp`);
            toast.success(data.rsvped ? "You're going! 🎉" : "RSVP removed");
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
            <div className="mt-4 relative rounded-3xl overflow-hidden aspect-[21/9] bg-muted">
                {event.cover_image && <img src={event.cover_image} alt={event.title} className="w-full h-full object-cover" />}
                <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-black/10 to-transparent" />
                <div className="absolute bottom-0 p-8 text-white">
                    <div className="text-xs uppercase tracking-wider bg-secondary/90 text-[hsl(34_8%_16%)] font-semibold inline-block rounded-full px-3 py-1 mb-3">
                        {event.category}
                    </div>
                    <h1 className="font-heading text-3xl sm:text-5xl font-bold tracking-tight drop-shadow">{event.title}</h1>
                </div>
            </div>

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
                            <div className="font-medium">{event.rsvp_count} going</div>
                            {event.capacity > 0 && (
                                <div className="text-sm text-muted-foreground">{event.capacity - event.rsvp_count} spots left</div>
                            )}
                        </div>
                    </div>
                    <Button
                        onClick={toggleRsvp}
                        disabled={loading}
                        className={`w-full rounded-full py-6 ${hasRsvped ? "bg-accent hover:bg-accent/90 text-accent-foreground" : "bg-primary hover:bg-primary/90 shadow-warm"}`}
                        data-testid="rsvp-btn"
                    >
                        {loading ? "Updating…" : hasRsvped ? "You're going — cancel" : "RSVP"}
                    </Button>
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
                </aside>
            </div>

            {user?.role === "admin" && <CheckInPanel eventId={id} eventTitle={event.title} />}
        </div>
    );
}

function CheckInPanel({ eventId, eventTitle }) {
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
                        {["vip", "general", "guest", "speaker", "volunteer"].map((t) => totals[t] ? `${totals[t]} ${t}` : null).filter(Boolean).join(" · ") || "No check-ins yet"}
                    </div>
                </div>
                <CheckInDialog eventId={eventId} eventTitle={eventTitle} members={members} checkedInIds={checkedInIds} onDone={load} />
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

function CheckInDialog({ eventId, eventTitle, members, checkedInIds, onDone }) {
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
                                    <SelectItem value="general">General admission</SelectItem>
                                    <SelectItem value="vip">VIP</SelectItem>
                                    <SelectItem value="guest">Guest</SelectItem>
                                    <SelectItem value="speaker">Speaker</SelectItem>
                                    <SelectItem value="volunteer">Volunteer</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <DialogFooter className="mt-4"><Button onClick={submit} className="rounded-full bg-primary hover:bg-primary/90" data-testid="checkin-confirm-btn">Check in</Button></DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
