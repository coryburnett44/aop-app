import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { format, parseISO } from "date-fns";
import { MapPin, Users, Calendar, ArrowLeft } from "lucide-react";
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
        </div>
    );
}
