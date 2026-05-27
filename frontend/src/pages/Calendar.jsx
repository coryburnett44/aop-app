import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { ChevronLeft, ChevronRight, Calendar as CalIcon, MapPin } from "lucide-react";
import { format, parseISO, startOfMonth, endOfMonth, eachDayOfInterval, getDay, isSameMonth, isSameDay, addMonths, subMonths } from "date-fns";

const NAVY = "#0A2463";
const RED = "#C8102E";

function ymKey(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }

export default function CalendarPage() {
    const [cursor, setCursor] = useState(new Date());
    const [events, setEvents] = useState([]);
    const [activeDay, setActiveDay] = useState(null);

    useEffect(() => {
        api.get(`/events/calendar?month=${ymKey(cursor)}`)
            .then(({ data }) => setEvents(data))
            .catch(() => setEvents([]));
    }, [cursor]);

    const monthStart = startOfMonth(cursor);
    const monthEnd = endOfMonth(cursor);
    const firstDow = getDay(monthStart);
    const days = eachDayOfInterval({ start: monthStart, end: monthEnd });
    const leading = Array.from({ length: firstDow }, (_, i) => i);

    const eventsByDay = useMemo(() => {
        const map = {};
        events.forEach((e) => {
            const key = e.start_at?.slice(0, 10);
            if (!key) return;
            (map[key] = map[key] || []).push(e);
        });
        return map;
    }, [events]);

    const todayKey = format(new Date(), "yyyy-MM-dd");
    const dayEvents = activeDay ? (eventsByDay[activeDay] || []) : [];

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-10">
            <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] font-bold" style={{ color: RED }}>Chapter calendar</div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter mt-1" style={{ color: NAVY }}>
                        {format(cursor, "MMMM yyyy")}
                    </h1>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" className="rounded-full" onClick={() => setCursor((c) => subMonths(c, 1))} data-testid="cal-prev">
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button variant="outline" className="rounded-full" onClick={() => setCursor(new Date())} data-testid="cal-today">Today</Button>
                    <Button variant="outline" className="rounded-full" onClick={() => setCursor((c) => addMonths(c, 1))} data-testid="cal-next">
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-7 gap-px bg-slate-200 rounded-3xl overflow-hidden border-2 border-slate-200" data-testid="calendar-grid">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                    <div key={d} className="bg-white text-center text-[10px] sm:text-xs font-bold uppercase tracking-widest py-3 text-slate-500">{d}</div>
                ))}
                {leading.map((i) => <div key={`lead-${i}`} className="bg-slate-50 min-h-[80px] sm:min-h-[110px]" />)}
                {days.map((d) => {
                    const key = format(d, "yyyy-MM-dd");
                    const dayEvts = eventsByDay[key] || [];
                    const isToday = key === todayKey;
                    return (
                        <button
                            key={key}
                            onClick={() => dayEvts.length > 0 && setActiveDay(key)}
                            className={`bg-white min-h-[80px] sm:min-h-[110px] p-1.5 sm:p-2 text-left transition-colors ${dayEvts.length > 0 ? "hover:bg-slate-50 cursor-pointer" : "cursor-default"}`}
                            data-testid={`cal-day-${key}`}
                        >
                            <div className={`text-xs sm:text-sm font-bold inline-flex items-center justify-center w-6 h-6 rounded-full ${isToday ? "text-white" : "text-slate-700"}`} style={isToday ? { backgroundColor: RED } : {}}>
                                {format(d, "d")}
                            </div>
                            <div className="mt-1 space-y-0.5">
                                {dayEvts.slice(0, 3).map((e) => (
                                    <div key={e.id} className="text-[10px] sm:text-xs rounded px-1 py-0.5 truncate text-white" style={{ backgroundColor: NAVY }}>
                                        {e.title}
                                    </div>
                                ))}
                                {dayEvts.length > 3 && <div className="text-[10px] text-slate-500">+{dayEvts.length - 3} more</div>}
                            </div>
                        </button>
                    );
                })}
            </div>

            <div className="mt-8">
                <h2 className="font-heading text-2xl font-bold mb-4" style={{ color: NAVY }}>This month at a glance</h2>
                {events.length === 0 ? (
                    <div className="text-slate-500 text-sm">No events scheduled.</div>
                ) : (
                    <div className="space-y-2">
                        {events.map((e) => (
                            <Link key={e.id} to={`/events/${e.id}`} className="flex items-center gap-4 p-4 bg-white rounded-2xl border border-slate-200 hover:border-slate-400 transition-colors" data-testid={`cal-event-${e.id}`}>
                                <div className="text-center px-3 py-1 rounded-xl text-white font-bold shrink-0" style={{ backgroundColor: NAVY }}>
                                    <div className="text-[10px] uppercase">{format(parseISO(e.start_at), "MMM")}</div>
                                    <div className="text-xl font-black -mt-1">{format(parseISO(e.start_at), "d")}</div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-heading font-bold" style={{ color: NAVY }}>{e.title}</div>
                                    <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-3 flex-wrap">
                                        <span><CalIcon className="h-3 w-3 inline" /> {format(parseISO(e.start_at), "h:mm a")}</span>
                                        {e.location && <span><MapPin className="h-3 w-3 inline" /> {e.location}</span>}
                                        <span>{e.rsvp_count || 0} RSVPs</span>
                                        {e.checkin_count > 0 && <span>· {e.checkin_count} checked in</span>}
                                    </div>
                                </div>
                            </Link>
                        ))}
                    </div>
                )}
            </div>

            <Dialog open={!!activeDay} onOpenChange={(o) => !o && setActiveDay(null)}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>
                            {activeDay && format(parseISO(activeDay), "EEEE, MMM d")}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-2 mt-2">
                        {dayEvents.map((e) => (
                            <Link key={e.id} to={`/events/${e.id}`} className="block p-4 rounded-xl bg-slate-50 hover:bg-slate-100">
                                <div className="font-bold" style={{ color: NAVY }}>{e.title}</div>
                                <div className="text-xs text-slate-500 mt-1">{format(parseISO(e.start_at), "h:mm a")} · {e.location || "TBA"}</div>
                            </Link>
                        ))}
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}
