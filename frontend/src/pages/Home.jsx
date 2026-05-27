import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Calendar, Users, Star, ArrowRight, MapPin, Shield, HeartHandshake, LogIn } from "lucide-react";
import { format } from "date-fns";
import Countdown from "../components/Countdown";

const HERO_BANNER = "https://images.clubexpress.com/211315/photos/original/Sheron_Tana_Banner_743849018.jpg";
const SECONDARY_BANNER = "https://images.clubexpress.com/211315/photos/original/Kendra_Brandy_Banner_2074356465.jpg";
const AOP_LOGO = "https://images.clubexpress.com/211315/graphics/AOP_2_281912154.png";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function Home() {
    const { user } = useAuth();
    const [events, setEvents] = useState([]);
    const [news, setNews] = useState([]);

    useEffect(() => {
        api.get("/events?upcoming=true").then(({ data }) => setEvents(data.slice(0, 3))).catch(() => {});
        api.get("/news").then(({ data }) => setNews(data.slice(0, 2))).catch(() => {});
    }, []);

    return (
        <div className="bg-white text-[#0A2463]" data-testid="home-aop">
            {/* Hero with group photo */}
            <section className="relative overflow-hidden">
                {/* Patriotic stripe */}
                <div className="absolute inset-x-0 top-0 h-1.5 z-10 flex">
                    <div className="flex-1" style={{ backgroundColor: RED }} />
                    <div className="flex-1 bg-white" />
                    <div className="flex-1" style={{ backgroundColor: NAVY }} />
                </div>

                <div className="relative h-[640px] sm:h-[680px] w-full">
                    <img
                        src={HERO_BANNER}
                        alt="Alpha Omega Phi members"
                        className="absolute inset-0 w-full h-full object-cover"
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                    />
                    <div
                        className="absolute inset-0"
                        style={{
                            background: `linear-gradient(180deg, rgba(10,36,99,0.55) 0%, rgba(10,36,99,0.35) 40%, rgba(10,36,99,0.85) 100%)`,
                        }}
                    />

                    <div className="relative h-full max-w-7xl mx-auto px-6 lg:px-10 flex items-center">
                        <div className="text-white animate-float-in max-w-3xl">
                            <div
                                className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold uppercase tracking-[0.2em] mb-6 backdrop-blur-md"
                                style={{ backgroundColor: "rgba(200,16,46,0.85)" }}
                                data-testid="hero-tag"
                            >
                                <Star className="h-3.5 w-3.5 fill-current" /> Members Portal
                            </div>
                            <h1 className="font-heading font-black text-4xl sm:text-5xl lg:text-7xl leading-[0.95] tracking-tighter">
                                Alpha Omega Phi
                                <span className="block mt-2 text-3xl sm:text-4xl lg:text-5xl font-bold opacity-95">
                                    Military Fraternity &amp; Sorority, Inc.
                                </span>
                            </h1>
                            <p className="mt-6 text-base sm:text-xl leading-relaxed opacity-90 max-w-2xl">
                                Welcome, Trendsetters. Your home for chapter events, members, awards, hours, and the work
                                we do together for our veterans and communities.
                            </p>
                            <div className="mt-8 flex flex-wrap gap-3">
                                {user ? (
                                    <Link
                                        to="/profile"
                                        className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-warm-lg hover:-translate-y-0.5 transition-all"
                                        style={{ backgroundColor: RED }}
                                        data-testid="hero-cta-profile"
                                    >
                                        Go to my profile <ArrowRight className="h-4 w-4" />
                                    </Link>
                                ) : (
                                    <Link
                                        to="/login"
                                        className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-warm-lg hover:-translate-y-0.5 transition-all"
                                        style={{ backgroundColor: RED }}
                                        data-testid="hero-cta-login"
                                    >
                                        <LogIn className="h-4 w-4" /> Member login
                                    </Link>
                                )}
                                <Link
                                    to="/events"
                                    className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold bg-white/10 border-2 border-white text-white backdrop-blur hover:bg-white hover:text-[#0A2463] transition-colors"
                                    data-testid="hero-cta-events"
                                >
                                    See events
                                </Link>
                            </div>
                        </div>

                        <img
                            src={AOP_LOGO}
                            alt="AOP crest"
                            className="hidden lg:block absolute right-10 top-1/2 -translate-y-1/2 w-48 drop-shadow-2xl"
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                        />
                    </div>
                </div>
            </section>

            {/* 10-Year Anniversary Countdown */}
            <Countdown />

            {/* Pillars */}
            <section className="bg-white border-b-2" style={{ borderColor: NAVY }}>
                <div className="max-w-7xl mx-auto px-6 lg:px-10 py-16">
                    <div className="text-center mb-12">
                        <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>What we stand for</div>
                        <h2 className="font-heading text-3xl sm:text-4xl font-black tracking-tight" style={{ color: NAVY }}>
                            Three pillars, one family
                        </h2>
                    </div>
                    <div className="grid md:grid-cols-3 gap-6">
                        <Pillar color={RED} title="Veteran Assistance" icon={<Shield className="h-6 w-6" />}
                            body="Connecting service members with the welfare, health, and benefits resources they earned." />
                        <Pillar color={NAVY} title="Community Service" icon={<HeartHandshake className="h-6 w-6" />}
                            body="Giving back in every chapter — food drives, mentorship, and outreach for local families." />
                        <Pillar color={RED} title="Fellowship" icon={<Users className="h-6 w-6" />}
                            body="A cross-branch family — bridging Army, Navy, Air Force, Marines, Coast Guard, and Space Force." />
                    </div>
                </div>
            </section>

            {/* Secondary banner photo */}
            <section className="max-w-7xl mx-auto px-6 lg:px-10 py-14">
                <div className="relative aspect-[21/9] rounded-3xl overflow-hidden shadow-warm-lg border-4" style={{ borderColor: NAVY }}>
                    <img
                        src={SECONDARY_BANNER}
                        alt="AOP members"
                        className="w-full h-full object-cover"
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                    />
                    <div className="absolute inset-0" style={{ background: `linear-gradient(90deg, rgba(10,36,99,0.7) 0%, transparent 50%, rgba(200,16,46,0.4) 100%)` }} />
                    <div className="absolute inset-y-0 left-0 flex items-center px-6 sm:px-10 lg:px-16 text-white max-w-2xl">
                        <div>
                            <div className="text-xs uppercase tracking-[0.25em] font-bold opacity-90 mb-3">Trendsetters</div>
                            <h3 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-black leading-tight">
                                Setting the standard, every chapter, every day.
                            </h3>
                        </div>
                    </div>
                </div>
            </section>

            {/* Upcoming events */}
            <section className="bg-slate-50 py-16">
                <div className="max-w-7xl mx-auto px-6 lg:px-10">
                    <div className="flex items-end justify-between mb-8">
                        <div>
                            <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>What's next</div>
                            <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-black tracking-tight" style={{ color: NAVY }}>
                                Upcoming events
                            </h2>
                        </div>
                        <Link to="/events" className="font-bold hover:underline hidden sm:inline-flex items-center gap-1" style={{ color: RED }} data-testid="home-view-events">
                            View all <ArrowRight className="h-4 w-4" />
                        </Link>
                    </div>
                    <div className="grid md:grid-cols-3 gap-6">
                        {events.map((e) => (
                            <Link
                                key={e.id}
                                to={`/events/${e.id}`}
                                className="group bg-white rounded-2xl overflow-hidden shadow-warm border-2 border-transparent hover:-translate-y-1 hover:shadow-warm-lg hover:border-[#C8102E] transition-all"
                                data-testid={`home-event-${e.id}`}
                            >
                                <div className="aspect-[16/10] overflow-hidden bg-slate-100">
                                    {e.cover_image && (
                                        <img src={e.cover_image} alt={e.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                                    )}
                                </div>
                                <div className="p-6">
                                    <div className="text-xs font-bold uppercase tracking-wide" style={{ color: RED }}>
                                        {format(new Date(e.start_at), "EEE, MMM d · h:mm a")}
                                    </div>
                                    <h3 className="font-heading font-bold text-xl mt-2 leading-snug" style={{ color: NAVY }}>{e.title}</h3>
                                    <div className="mt-3 flex items-center gap-2 text-sm text-slate-600">
                                        <MapPin className="h-4 w-4" /> {e.location || "TBA"}
                                    </div>
                                </div>
                            </Link>
                        ))}
                        {events.length === 0 &&
                            [1, 2, 3].map((i) => (
                                <div key={i} className="h-80 rounded-2xl bg-slate-200 animate-pulse" />
                            ))}
                    </div>
                </div>
            </section>

            {/* News */}
            <section className="py-16 bg-white">
                <div className="max-w-7xl mx-auto px-6 lg:px-10">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>From the chapter house</div>
                    <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-black tracking-tight mb-8" style={{ color: NAVY }}>
                        News &amp; stories
                    </h2>
                    <div className="grid md:grid-cols-2 gap-6">
                        {news.map((n) => (
                            <Link
                                key={n.id}
                                to={`/news/${n.id}`}
                                className="group flex gap-5 bg-white rounded-2xl overflow-hidden border-2 border-slate-200 hover:-translate-y-1 hover:shadow-warm hover:border-[#0A2463] transition-all"
                                data-testid={`home-news-${n.id}`}
                            >
                                <div className="w-40 shrink-0 bg-slate-100 overflow-hidden">
                                    {n.cover_image && (
                                        <img src={n.cover_image} alt={n.title} className="w-full h-full object-cover" />
                                    )}
                                </div>
                                <div className="py-5 pr-5">
                                    <div className="text-xs text-slate-500">
                                        {n.created_at && format(new Date(n.created_at), "MMM d, yyyy")}
                                    </div>
                                    <h3 className="font-heading font-bold text-lg mt-1 leading-snug" style={{ color: NAVY }}>{n.title}</h3>
                                    <p className="text-sm text-slate-600 mt-2 line-clamp-2">{n.summary}</p>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
}

function Pillar({ color, title, body, icon }) {
    return (
        <div className="relative bg-white rounded-2xl p-7 border-2 border-slate-200 shadow-warm hover:-translate-y-1 transition-transform">
            <div
                className="absolute top-0 left-6 -translate-y-1/2 w-12 h-12 rounded-2xl grid place-items-center text-white shadow-warm"
                style={{ backgroundColor: color }}
            >
                {icon}
            </div>
            <h3 className="font-heading font-black text-xl mt-4" style={{ color: NAVY }}>{title}</h3>
            <p className="text-sm text-slate-600 mt-2 leading-relaxed">{body}</p>
        </div>
    );
}
