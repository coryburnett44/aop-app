import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Calendar, Users, Star, ArrowRight, MapPin, Shield, HeartHandshake } from "lucide-react";
import { format } from "date-fns";

const AOP_COVER = "https://alphaomegaphi.org/wp-content/uploads/2023/10/cover-AOP.jpg";
const AOP_LOGO = "https://alphaomegaphi.org/wp-content/uploads/2022/08/AOP-LOGO-1.png";
const AOP_TRI = "https://alphaomegaphi.org/wp-content/uploads/2022/12/Tri_South_03.png";
const AOP_VA = "https://alphaomegaphi.org/wp-content/uploads/2022/08/virginia-chapterVA_-NC_-MD_-DC-AND-01-scaled.jpg";

const NAVY = "#0A2463";
const RED = "#D62828";

export default function Home() {
    const [events, setEvents] = useState([]);
    const [news, setNews] = useState([]);

    useEffect(() => {
        api.get("/events?upcoming=true").then(({ data }) => setEvents(data.slice(0, 3))).catch(() => {});
        api.get("/news").then(({ data }) => setNews(data.slice(0, 2))).catch(() => {});
    }, []);

    return (
        <div className="bg-white text-[#0A2463]" data-testid="home-aop">
            {/* Hero */}
            <section className="relative overflow-hidden bg-white">
                {/* Patriotic stripe */}
                <div className="absolute inset-x-0 top-0 h-1 flex">
                    <div className="flex-1" style={{ backgroundColor: RED }} />
                    <div className="flex-1 bg-white" />
                    <div className="flex-1" style={{ backgroundColor: NAVY }} />
                </div>

                <div className="max-w-7xl mx-auto px-6 lg:px-10 pt-16 pb-20 grid lg:grid-cols-12 gap-10 items-center">
                    <div className="lg:col-span-7 animate-float-in">
                        <div
                            className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold uppercase tracking-wider mb-6 border-2"
                            style={{ borderColor: RED, color: RED, backgroundColor: "#fff5f5" }}
                            data-testid="hero-tag"
                        >
                            <Star className="h-3.5 w-3.5 fill-current" /> Honor · Service · Fellowship
                        </div>
                        <h1 className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl leading-[1.02] tracking-tighter" style={{ color: NAVY }}>
                            Alpha Omega Phi
                            <span className="block mt-1" style={{ color: RED }}>Military Fraternity</span>
                            <span className="block mt-1" style={{ color: NAVY }}>&amp; Sorority, Inc.</span>
                        </h1>
                        <p className="mt-6 text-base sm:text-lg leading-relaxed text-slate-600 max-w-xl">
                            A co-ed family for U.S. Armed Forces members — past, present, and future. United across branches,
                            grounded in service to our veterans and our communities.
                        </p>
                        <div className="mt-8 flex flex-wrap gap-3">
                            <Link
                                to="/register"
                                className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-warm hover:-translate-y-0.5 hover:shadow-warm-lg transition-all"
                                style={{ backgroundColor: RED }}
                                data-testid="hero-cta-join"
                            >
                                Apply for membership <ArrowRight className="h-4 w-4" />
                            </Link>
                            <Link
                                to="/events"
                                className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold border-2 hover:bg-slate-50 transition-colors"
                                style={{ borderColor: NAVY, color: NAVY }}
                                data-testid="hero-cta-events"
                            >
                                Upcoming events
                            </Link>
                        </div>

                        <div className="mt-10 grid grid-cols-3 gap-6 max-w-md">
                            <Stat icon={<Shield className="h-5 w-5" />} num="All" label="Branches" />
                            <Stat icon={<Users className="h-5 w-5" />} num="Multi" label="Chapters" />
                            <Stat icon={<HeartHandshake className="h-5 w-5" />} num="501(c)(3)" label="Nonprofit" />
                        </div>
                    </div>

                    <div className="lg:col-span-5 relative">
                        <div
                            className="relative aspect-[4/5] rounded-[2rem] overflow-hidden shadow-warm-lg border-4"
                            style={{ borderColor: NAVY }}
                        >
                            <img
                                src={AOP_COVER}
                                alt="Alpha Omega Phi members"
                                className="w-full h-full object-cover"
                                onError={(e) => { e.currentTarget.style.display = "none"; }}
                            />
                            <div
                                className="absolute inset-0"
                                style={{ background: `linear-gradient(135deg, ${NAVY}33 0%, transparent 40%, ${RED}33 100%)` }}
                            />
                        </div>
                        <div
                            className="absolute -bottom-6 -left-6 bg-white rounded-2xl p-4 shadow-warm-lg w-56 hidden sm:block border-2"
                            style={{ borderColor: RED }}
                        >
                            <div className="text-[10px] uppercase tracking-wider font-bold" style={{ color: RED }}>Our motto</div>
                            <div className="font-heading font-black mt-1 leading-tight" style={{ color: NAVY }}>
                                One family. One mission.
                            </div>
                        </div>
                        <img
                            src={AOP_LOGO}
                            alt="AOP crest"
                            className="absolute -top-6 -right-6 w-24 h-24 hidden sm:block drop-shadow-lg"
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                        />
                    </div>
                </div>
            </section>

            {/* Pillars */}
            <section className="bg-white border-y-2" style={{ borderColor: NAVY }}>
                <div className="max-w-7xl mx-auto px-6 lg:px-10 py-14 grid md:grid-cols-3 gap-6">
                    <Pillar
                        color={RED}
                        title="Veteran Assistance"
                        body="Connecting service members with the welfare, health, and benefits resources they earned."
                        icon={<Shield className="h-6 w-6" />}
                    />
                    <Pillar
                        color={NAVY}
                        title="Community Service"
                        body="Giving back in every chapter — food drives, mentorship, and outreach for local families."
                        icon={<HeartHandshake className="h-6 w-6" />}
                    />
                    <Pillar
                        color={RED}
                        title="Fellowship"
                        body="A cross-branch family — bridging Army, Navy, Air Force, Marines, Coast Guard, and Space Force."
                        icon={<Users className="h-6 w-6" />}
                    />
                </div>
            </section>

            {/* Image strip */}
            <section className="max-w-7xl mx-auto px-6 lg:px-10 py-14">
                <div className="grid sm:grid-cols-2 gap-6">
                    <div className="relative aspect-[16/10] rounded-2xl overflow-hidden shadow-warm">
                        <img src={AOP_TRI} alt="Chapter members" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                        <div className="absolute inset-0 bg-gradient-to-t from-[#0A2463]/80 to-transparent" />
                        <div className="absolute bottom-4 left-4 text-white">
                            <div className="text-[10px] uppercase tracking-wider font-bold opacity-90">Brotherhood</div>
                            <div className="font-heading text-xl font-bold">Standing together, coast to coast</div>
                        </div>
                    </div>
                    <div className="relative aspect-[16/10] rounded-2xl overflow-hidden shadow-warm">
                        <img src={AOP_VA} alt="Chapter event" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                        <div className="absolute inset-0 bg-gradient-to-t from-[#D62828]/80 to-transparent" />
                        <div className="absolute bottom-4 left-4 text-white">
                            <div className="text-[10px] uppercase tracking-wider font-bold opacity-90">Chapters</div>
                            <div className="font-heading text-xl font-bold">Regional families with a national mission</div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Upcoming events */}
            <section className="bg-slate-50 py-16">
                <div className="max-w-7xl mx-auto px-6 lg:px-10">
                    <div className="flex items-end justify-between mb-8">
                        <div>
                            <div className="text-xs uppercase tracking-wider font-bold mb-2" style={{ color: RED }}>What's next</div>
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
                                className="group bg-white rounded-2xl overflow-hidden shadow-warm border-2 border-transparent hover:-translate-y-1 hover:shadow-warm-lg hover:border-[#D62828] transition-all"
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
                    <div className="text-xs uppercase tracking-wider font-bold mb-2" style={{ color: RED }}>From the chapter house</div>
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

            {/* Final CTA banner */}
            <section className="relative overflow-hidden" style={{ backgroundColor: NAVY }}>
                <div className="absolute inset-0 opacity-10" style={{
                    backgroundImage: "repeating-linear-gradient(45deg, #fff 0 2px, transparent 2px 22px)",
                }} />
                <div className="relative max-w-5xl mx-auto px-6 lg:px-10 py-16 text-center text-white">
                    <Star className="h-8 w-8 mx-auto mb-4 fill-current" style={{ color: RED }} />
                    <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight">
                        Ready to stand with us?
                    </h2>
                    <p className="mt-4 text-base sm:text-lg max-w-2xl mx-auto opacity-90">
                        Whether you wore the uniform or you support those who did — there's a place for you in the AOP family.
                    </p>
                    <Link
                        to="/register"
                        className="inline-flex items-center gap-2 mt-8 rounded-full px-8 py-4 font-bold shadow-warm-lg hover:-translate-y-0.5 transition-transform text-white"
                        style={{ backgroundColor: RED }}
                        data-testid="footer-cta-join"
                    >
                        Apply for membership <ArrowRight className="h-5 w-5" />
                    </Link>
                </div>
            </section>
        </div>
    );
}

function Stat({ icon, num, label }) {
    return (
        <div>
            <div className="w-10 h-10 rounded-full bg-slate-100 grid place-items-center text-[#0A2463] mb-2">{icon}</div>
            <div className="font-heading font-black text-lg leading-none" style={{ color: NAVY }}>{num}</div>
            <div className="text-xs text-slate-500 mt-1">{label}</div>
        </div>
    );
}

function Pillar({ color, title, body, icon }) {
    return (
        <div className="relative bg-white rounded-2xl p-6 border-2 border-slate-200 shadow-warm">
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
