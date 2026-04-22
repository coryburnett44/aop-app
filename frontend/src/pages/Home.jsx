import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Calendar, Users, Sparkles, ArrowRight, MapPin } from "lucide-react";
import { format } from "date-fns";

export default function Home() {
    const [events, setEvents] = useState([]);
    const [news, setNews] = useState([]);

    useEffect(() => {
        api.get("/events?upcoming=true").then(({ data }) => setEvents(data.slice(0, 3))).catch(() => {});
        api.get("/news").then(({ data }) => setNews(data.slice(0, 2))).catch(() => {});
    }, []);

    return (
        <div>
            {/* Hero */}
            <section className="relative overflow-hidden">
                <div className="max-w-7xl mx-auto px-6 lg:px-10 pt-14 pb-20 grid lg:grid-cols-12 gap-10 items-center">
                    <div className="lg:col-span-6 animate-float-in">
                        <div className="inline-flex items-center gap-2 rounded-full bg-secondary/40 px-4 py-1.5 text-xs font-semibold text-[hsl(34_8%_20%)] mb-6" data-testid="hero-tag">
                            <Sparkles className="h-3.5 w-3.5" /> Spring 2026 is here
                        </div>
                        <h1 className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl leading-[1.02] tracking-tighter">
                            A warm home for <span className="text-primary">our club</span>,
                            <span className="block">gathered in one place.</span>
                        </h1>
                        <p className="mt-6 text-base sm:text-lg leading-relaxed text-muted-foreground max-w-xl">
                            Manage membership, RSVP to events, publish news, and keep your community close. ClubHaven gives you everything ClubExpress does — with a friendlier feel.
                        </p>
                        <div className="mt-8 flex flex-wrap gap-3">
                            <Link
                                to="/register"
                                className="inline-flex items-center gap-2 rounded-full bg-primary text-primary-foreground px-6 py-3 font-medium shadow-warm hover:-translate-y-0.5 hover:shadow-warm-lg transition-all"
                                data-testid="hero-cta-join"
                            >
                                Join the club <ArrowRight className="h-4 w-4" />
                            </Link>
                            <Link
                                to="/events"
                                className="inline-flex items-center gap-2 rounded-full bg-background border border-border px-6 py-3 font-medium hover:bg-muted transition-colors"
                                data-testid="hero-cta-events"
                            >
                                Browse events
                            </Link>
                        </div>
                        <div className="mt-10 flex items-center gap-8">
                            <Stat icon={<Users className="h-5 w-5" />} num="240+" label="active members" />
                            <Stat icon={<Calendar className="h-5 w-5" />} num="40+" label="events a year" />
                        </div>
                    </div>

                    <div className="lg:col-span-6 relative">
                        <div className="relative aspect-[5/4] rounded-[2rem] overflow-hidden shadow-warm-lg">
                            <img
                                src="https://images.unsplash.com/photo-1758272133693-d2124dbe00de?q=80&w=1400"
                                alt="Community gathering outdoors"
                                className="w-full h-full object-cover"
                            />
                            <div className="absolute inset-0 bg-gradient-to-tr from-primary/15 via-transparent to-secondary/15" />
                        </div>
                        <div className="absolute -bottom-6 -left-6 bg-card rounded-2xl p-4 shadow-warm border border-border w-56 hidden sm:block">
                            <div className="text-xs text-muted-foreground">Next up</div>
                            <div className="font-heading font-semibold mt-1 leading-tight">
                                Sunday Trail Hike
                            </div>
                            <div className="text-xs mt-1 text-primary font-medium">28 members going</div>
                        </div>
                        <div className="absolute -top-6 -right-6 bg-secondary rounded-full px-4 py-2 shadow-warm hidden sm:flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-[hsl(34_8%_16%)] animate-pulse" />
                            <span className="text-xs font-semibold">Live now: book club</span>
                        </div>
                    </div>
                </div>
            </section>

            {/* Upcoming events */}
            <section className="max-w-7xl mx-auto px-6 lg:px-10 py-16">
                <div className="flex items-end justify-between mb-8">
                    <div>
                        <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight">
                            Upcoming events
                        </h2>
                        <p className="text-muted-foreground mt-2">What's happening around the clubhouse.</p>
                    </div>
                    <Link to="/events" className="text-primary font-medium hover:underline hidden sm:inline-flex items-center gap-1" data-testid="home-view-events">
                        View all <ArrowRight className="h-4 w-4" />
                    </Link>
                </div>
                <div className="grid md:grid-cols-3 gap-6">
                    {events.map((e) => (
                        <Link
                            key={e.id}
                            to={`/events/${e.id}`}
                            className="group bg-card rounded-2xl overflow-hidden shadow-warm border border-border hover:-translate-y-1 hover:shadow-warm-lg transition-all"
                            data-testid={`home-event-${e.id}`}
                        >
                            <div className="aspect-[16/10] overflow-hidden bg-muted">
                                {e.cover_image && (
                                    <img
                                        src={e.cover_image}
                                        alt={e.title}
                                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                                    />
                                )}
                            </div>
                            <div className="p-6">
                                <div className="text-xs font-semibold text-primary uppercase tracking-wide">
                                    {format(new Date(e.start_at), "EEE, MMM d · h:mm a")}
                                </div>
                                <h3 className="font-heading font-semibold text-xl mt-2 leading-snug">{e.title}</h3>
                                <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                                    <MapPin className="h-4 w-4" /> {e.location || "TBA"}
                                </div>
                            </div>
                        </Link>
                    ))}
                    {events.length === 0 &&
                        [1, 2, 3].map((i) => (
                            <div key={i} className="h-80 rounded-2xl bg-muted animate-pulse" />
                        ))}
                </div>
            </section>

            {/* News */}
            <section className="bg-muted/40 py-16">
                <div className="max-w-7xl mx-auto px-6 lg:px-10">
                    <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight mb-8">
                        From the club
                    </h2>
                    <div className="grid md:grid-cols-2 gap-6">
                        {news.map((n) => (
                            <Link
                                key={n.id}
                                to={`/news/${n.id}`}
                                className="group flex gap-5 bg-card rounded-2xl overflow-hidden border border-border hover:-translate-y-1 hover:shadow-warm transition-all"
                                data-testid={`home-news-${n.id}`}
                            >
                                <div className="w-40 shrink-0 bg-muted overflow-hidden">
                                    {n.cover_image && (
                                        <img src={n.cover_image} alt={n.title} className="w-full h-full object-cover" />
                                    )}
                                </div>
                                <div className="py-5 pr-5">
                                    <div className="text-xs text-muted-foreground">
                                        {n.created_at && format(new Date(n.created_at), "MMM d, yyyy")}
                                    </div>
                                    <h3 className="font-heading font-semibold text-lg mt-1 leading-snug">{n.title}</h3>
                                    <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{n.summary}</p>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
}

function Stat({ icon, num, label }) {
    return (
        <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-accent/40 grid place-items-center">{icon}</div>
            <div>
                <div className="font-heading font-bold text-lg leading-none">{num}</div>
                <div className="text-xs text-muted-foreground">{label}</div>
            </div>
        </div>
    );
}
