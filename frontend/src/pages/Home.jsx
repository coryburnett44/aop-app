import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useSiteSettings } from "../context/SiteSettingsContext";
import { Calendar, Users, Star, ArrowRight, MapPin, Shield, HeartHandshake, LogIn, Cake, UserPlus } from "lucide-react";
import { format, parseISO } from "date-fns";
import Countdown from "../components/Countdown";
import { BlocksRenderer } from "../components/cms/BlockRenderer";

const AOP_LOGO = "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/k67x4iui_Trendsetters%20logo.png";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function Home() {
    const { user, loading } = useAuth();
    const { settings } = useSiteSettings();
    const [events, setEvents] = useState([]);
    const [news, setNews] = useState([]);
    const [newMembers, setNewMembers] = useState([]);
    const [birthdays, setBirthdays] = useState([]);

    useEffect(() => {
        if (!user) return;
        api.get("/events?upcoming=true").then(({ data }) => setEvents(data.slice(0, 3))).catch(() => {});
        api.get("/news").then(({ data }) => setNews(data.slice(0, 2))).catch(() => {});
        api.get("/members-new?days=30&limit=6").then(({ data }) => setNewMembers(data)).catch(() => {});
        api.get("/members-birthdays?days=30&limit=8").then(({ data }) => setBirthdays(data)).catch(() => {});
    }, [user]);

    if (loading) return null;
    if (!user) return <Navigate to="/login" replace />;

    const sec = settings?.home_sections || {};
    const showSection = (key) => sec[key] !== false; // default-true
    const topBlocks = settings?.home_blocks_top || [];
    const bottomBlocks = settings?.home_blocks_bottom || [];
    const founders = settings?.founders_items || [];

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

                <div className="relative w-full bg-slate-50">
                    {/* Founders row — responsive grid: 2 cols on mobile, scales up with item count */}
                    {showSection("founders") && founders.length > 0 && (
                    <div className="w-full" style={{ backgroundColor: NAVY }} data-testid="hero-founders">
                        <div className={`grid grid-cols-2 ${founders.length === 1 ? "" : founders.length === 2 ? "sm:grid-cols-2" : founders.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-4"} max-w-7xl mx-auto`}>
                            {founders.map((f) => (
                                <div key={f.name} className="relative aspect-square bg-slate-900 overflow-hidden border border-white/10 group" data-testid={`founder-${f.name}`}>
                                    <img
                                        src={f.image_url}
                                        alt={f.name ? `${f.role || "Founder"} ${f.name}` : "Founder"}
                                        loading="lazy"
                                        className="absolute inset-0 w-full h-full object-contain transition-transform duration-500 group-hover:scale-105"
                                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                    )}

                    {/* Headline below image so neither crops the other */}
                    {showSection("hero_text") && (
                    <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12 sm:py-16 grid lg:grid-cols-[1fr_auto] gap-8 items-center">
                        <div>
                            <div
                                className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold uppercase tracking-[0.2em] mb-5 text-white"
                                style={{ backgroundColor: RED }}
                                data-testid="hero-tag"
                            >
                                <Star className="h-3.5 w-3.5 fill-current" /> {settings?.hero_eyebrow || "Members Portal"}
                            </div>
                            <h1 className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl leading-[0.95] tracking-tighter" style={{ color: NAVY }} data-testid="hero-headline">
                                {settings?.hero_headline ? (
                                    <span>{settings.hero_headline}</span>
                                ) : (
                                    <>
                                        Alpha Omega Phi
                                        <span className="block mt-2 text-2xl sm:text-3xl lg:text-4xl font-bold text-slate-700">
                                            Military Fraternity &amp; Sorority, Inc.
                                        </span>
                                    </>
                                )}
                            </h1>
                            <p className="mt-5 text-base sm:text-lg leading-relaxed text-slate-600 max-w-2xl" data-testid="hero-subtext">
                                {settings?.hero_subtext || "Welcome, Trendsetters. Your home for chapter events, members, awards, hours, and the work we do together for our veterans and communities."}
                            </p>
                            <div className="mt-7 flex flex-wrap gap-3">
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
                                {user && (
                                    <Link
                                        to="/events"
                                        className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold border-2 transition-colors"
                                        style={{ borderColor: NAVY, color: NAVY }}
                                        data-testid="hero-cta-events"
                                    >
                                        See events
                                    </Link>
                                )}
                            </div>
                        </div>

                        <img
                            src={AOP_LOGO}
                            alt="AOP crest"
                            className="hidden lg:block w-48 drop-shadow-2xl"
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                        />
                    </div>
                    )}
                </div>
            </section>

            {/* Custom top blocks */}
            {topBlocks.length > 0 && (
                <section className="max-w-4xl mx-auto px-6 lg:px-10 py-8" data-testid="home-blocks-top">
                    <BlocksRenderer blocks={topBlocks} />
                </section>
            )}

            {/* 10-Year Anniversary Countdown */}
            {showSection("countdown") && <Countdown />}

            {/* Pillars */}
            {showSection("pillars") && (
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
            )}

            {/* Secondary banner photo removed per user request */}

            {/* Leadership Team — two banner images side-by-side, responsive */}
            {showSection("leadership_team") && (settings?.leadership_team_items?.length > 0) && (
                <section className="bg-white py-14" data-testid="home-leadership">
                    <div className="max-w-7xl mx-auto px-6 lg:px-10">
                        <div className="text-center mb-8">
                            <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>{settings.leadership_team_eyebrow || "National board"}</div>
                            <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight" style={{ color: NAVY }}>
                                {settings.leadership_team_title || "Leadership Team"}
                            </h2>
                        </div>
                        <div className={`grid grid-cols-1 ${settings.leadership_team_items.length >= 2 ? "md:grid-cols-2" : ""} ${settings.leadership_team_items.length >= 3 ? "lg:grid-cols-3" : ""} gap-6 lg:gap-8`}>
                            {settings.leadership_team_items.map((l, idx) => (
                                <div
                                    key={`${l.term}-${idx}`}
                                    className="bg-white rounded-3xl overflow-hidden border-4 shadow-warm-lg"
                                    style={{ borderColor: NAVY }}
                                    data-testid={`leadership-${l.term}`}
                                >
                                    <img
                                        src={l.image_url}
                                        alt={l.alt || l.term}
                                        loading="lazy"
                                        className="block w-full h-auto object-contain"
                                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* Family pulse: New Members + Birthdays */}
            {showSection("family_pulse") && user && (newMembers.length > 0 || birthdays.length > 0) && (
                <section className="bg-slate-50 border-b" style={{ borderColor: `${NAVY}20` }}>
                    <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12 sm:py-16">
                        <div className="text-center mb-10">
                            <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>The family</div>
                            <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-black tracking-tight" style={{ color: NAVY }}>
                                Who joined, who's celebrating
                            </h2>
                        </div>
                        <div className="grid lg:grid-cols-2 gap-6">
                            {/* New Members */}
                            <div className="bg-white rounded-3xl p-6 sm:p-7 border-2 shadow-warm" style={{ borderColor: `${NAVY}15` }} data-testid="home-new-members">
                                <div className="flex items-center gap-3 mb-5">
                                    <div className="w-10 h-10 rounded-2xl grid place-items-center text-white shadow-warm" style={{ backgroundColor: NAVY }}>
                                        <UserPlus className="h-5 w-5" />
                                    </div>
                                    <div>
                                        <h3 className="font-heading font-black text-lg" style={{ color: NAVY }}>New members</h3>
                                        <div className="text-xs text-slate-500">Last 30 days</div>
                                    </div>
                                </div>
                                {newMembers.length === 0 ? (
                                    <div className="text-sm text-slate-500 py-6 text-center">No new members in the last 30 days.</div>
                                ) : (
                                    <ul className="divide-y divide-slate-100">
                                        {newMembers.map((m) => {
                                            const initials = (m.name || m.email).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                                            return (
                                                <li key={m.id} className="py-3 flex items-center gap-3" data-testid={`new-member-${m.id}`}>
                                                    <div className="w-10 h-10 rounded-full grid place-items-center text-white font-bold shrink-0" style={{ backgroundColor: NAVY }}>
                                                        {m.avatar_url ? <img src={m.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : initials}
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="font-semibold text-sm truncate" style={{ color: NAVY }}>{m.name}</div>
                                                        <div className="text-xs text-slate-500 truncate">
                                                            {m.line_name && <span className="font-bold mr-2" style={{ color: RED }}>"{m.line_name}"</span>}
                                                            {m.city || "—"}
                                                        </div>
                                                    </div>
                                                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400">
                                                        {m.created_at && format(parseISO(m.created_at), "MMM d")}
                                                    </div>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                )}
                            </div>

                            {/* Birthdays */}
                            <div className="bg-white rounded-3xl p-6 sm:p-7 border-2 shadow-warm" style={{ borderColor: `${RED}25` }} data-testid="home-birthdays">
                                <div className="flex items-center gap-3 mb-5">
                                    <div className="w-10 h-10 rounded-2xl grid place-items-center text-white shadow-warm" style={{ backgroundColor: RED }}>
                                        <Cake className="h-5 w-5" />
                                    </div>
                                    <div>
                                        <h3 className="font-heading font-black text-lg" style={{ color: NAVY }}>Upcoming birthdays</h3>
                                        <div className="text-xs text-slate-500">Next 30 days</div>
                                    </div>
                                </div>
                                {birthdays.length === 0 ? (
                                    <div className="text-sm text-slate-500 py-6 text-center">No birthdays in the next 30 days.</div>
                                ) : (
                                    <ul className="divide-y divide-slate-100">
                                        {birthdays.map((m) => {
                                            const initials = (m.name || m.email).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                                            return (
                                                <li key={m.id} className="py-3 flex items-center gap-3" data-testid={`birthday-${m.id}`}>
                                                    <div className="w-10 h-10 rounded-full grid place-items-center text-white font-bold shrink-0" style={{ backgroundColor: RED }}>
                                                        {m.avatar_url ? <img src={m.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : initials}
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="font-semibold text-sm truncate" style={{ color: NAVY }}>{m.name}</div>
                                                        <div className="text-xs text-slate-500 truncate">
                                                            {m.line_name && <span className="font-bold mr-2" style={{ color: RED }}>"{m.line_name}"</span>}
                                                            Turning {m.age_turning}
                                                        </div>
                                                    </div>
                                                    <div className="text-right shrink-0">
                                                        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400">
                                                            {format(parseISO(m.next_birthday), "MMM d")}
                                                        </div>
                                                        <div className="text-[10px] font-semibold" style={{ color: RED }}>
                                                            {m.days_until_birthday === 0 ? "Today!" : `in ${m.days_until_birthday}d`}
                                                        </div>
                                                    </div>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                )}
                            </div>
                        </div>
                    </div>
                </section>
            )}

            {/* Upcoming events */}
            {showSection("upcoming_events") && (
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
            )}

            {/* News */}
            {showSection("news") && (
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
            )}

            {/* Custom bottom blocks */}
            {bottomBlocks.length > 0 && (
                <section className="max-w-4xl mx-auto px-6 lg:px-10 py-8" data-testid="home-blocks-bottom">
                    <BlocksRenderer blocks={bottomBlocks} />
                </section>
            )}
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
