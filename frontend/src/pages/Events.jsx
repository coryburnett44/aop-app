import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { format, isSameDay, parseISO, startOfMonth, endOfMonth, startOfWeek, endOfWeek, addDays, isSameMonth, addMonths } from "date-fns";
import { MapPin, Users, ChevronLeft, ChevronRight } from "lucide-react";

export default function Events() {
    const [events, setEvents] = useState([]);
    const [month, setMonth] = useState(new Date());

    useEffect(() => {
        api.get("/events").then(({ data }) => setEvents(data)).catch(() => {});
    }, []);

    const days = useMemo(() => {
        const start = startOfWeek(startOfMonth(month), { weekStartsOn: 0 });
        const end = endOfWeek(endOfMonth(month), { weekStartsOn: 0 });
        const arr = [];
        let d = start;
        while (d <= end) {
            arr.push(d);
            d = addDays(d, 1);
        }
        return arr;
    }, [month]);

    const eventsByDay = useMemo(() => {
        const map = {};
        events.forEach((e) => {
            const key = format(parseISO(e.start_at), "yyyy-MM-dd");
            (map[key] = map[key] || []).push(e);
        });
        return map;
    }, [events]);

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex items-end justify-between mb-10">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Events</h1>
                    <p className="text-muted-foreground mt-2">RSVP, show up, make memories.</p>
                </div>
            </div>

            <div className="grid lg:grid-cols-[1fr_400px] gap-10">
                {/* List */}
                <div className="space-y-4">
                    {events.length === 0 && <div className="text-muted-foreground">No events yet — check back soon.</div>}
                    {events.map((e) => (
                        <Link
                            key={e.id}
                            to={`/events/${e.id}`}
                            className="group grid grid-cols-[120px_1fr] gap-5 bg-card rounded-2xl p-5 shadow-warm border border-border hover:-translate-y-1 hover:shadow-warm-lg transition-all"
                            data-testid={`event-card-${e.id}`}
                        >
                            <div className="bg-secondary/30 rounded-xl aspect-square grid place-items-center text-center">
                                <div>
                                    <div className="text-xs font-semibold uppercase tracking-wider text-primary">
                                        {format(parseISO(e.start_at), "MMM")}
                                    </div>
                                    <div className="font-heading text-3xl font-black leading-none mt-1">
                                        {format(parseISO(e.start_at), "d")}
                                    </div>
                                    <div className="text-xs mt-2 text-muted-foreground">
                                        {format(parseISO(e.start_at), "h:mm a")}
                                    </div>
                                </div>
                            </div>
                            <div className="py-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-[10px] uppercase tracking-wider font-semibold text-accent-foreground bg-accent/40 rounded-full px-2 py-0.5">
                                        {e.category}
                                    </span>
                                    {e.cancelled && (
                                        <span
                                            className="text-[10px] uppercase tracking-wider font-bold text-white bg-red-600 rounded-full px-2 py-0.5"
                                            data-testid={`event-card-cancelled-${e.id}`}
                                        >
                                            ● Cancelled
                                        </span>
                                    )}
                                    {e.is_paid && !e.cancelled && (
                                        <span
                                            className="text-[10px] uppercase tracking-wider font-bold text-white bg-emerald-600 rounded-full px-2 py-0.5"
                                            data-testid={`event-card-paid-${e.id}`}
                                        >
                                            💲 ${e.payment_amount}
                                        </span>
                                    )}
                                </div>
                                <h3 className={`font-heading font-semibold text-xl mt-2 leading-snug ${e.cancelled ? "line-through opacity-60" : ""}`}>{e.title}</h3>
                                <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{e.description}</p>
                                <div className="mt-3 flex items-center gap-5 text-sm text-muted-foreground">
                                    <span className="inline-flex items-center gap-1.5"><MapPin className="h-4 w-4" /> {e.location || "TBA"}</span>
                                    <span className="inline-flex items-center gap-1.5"><Users className="h-4 w-4" /> {e.rsvp_count} going</span>
                                </div>
                            </div>
                        </Link>
                    ))}
                </div>

                {/* Calendar */}
                <div className="bg-card rounded-2xl p-5 border border-border h-fit sticky top-20" data-testid="calendar-widget">
                    <div className="flex items-center justify-between mb-4">
                        <button onClick={() => setMonth(addMonths(month, -1))} className="p-2 rounded-full hover:bg-muted" data-testid="cal-prev"><ChevronLeft className="h-4 w-4" /></button>
                        <div className="font-heading font-semibold">{format(month, "MMMM yyyy")}</div>
                        <button onClick={() => setMonth(addMonths(month, 1))} className="p-2 rounded-full hover:bg-muted" data-testid="cal-next"><ChevronRight className="h-4 w-4" /></button>
                    </div>
                    <div className="grid grid-cols-7 gap-1 text-[10px] text-muted-foreground uppercase mb-1">
                        {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                            <div key={i} className="text-center">{d}</div>
                        ))}
                    </div>
                    <div className="grid grid-cols-7 gap-1">
                        {days.map((d) => {
                            const key = format(d, "yyyy-MM-dd");
                            const has = !!eventsByDay[key];
                            const today = isSameDay(d, new Date());
                            return (
                                <div
                                    key={key}
                                    className={`aspect-square rounded-lg text-xs grid place-items-center relative ${
                                        isSameMonth(d, month) ? "" : "text-muted-foreground/40"
                                    } ${today ? "bg-primary text-primary-foreground font-bold" : has ? "bg-secondary/40" : "hover:bg-muted"}`}
                                >
                                    {format(d, "d")}
                                    {has && !today && <span className="absolute bottom-1 w-1 h-1 rounded-full bg-primary" />}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>
    );
}
