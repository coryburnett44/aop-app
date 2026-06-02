import { Link } from "react-router-dom";
import { Star, MapPin, Calendar as CalendarIcon, ArrowRight, Sparkles, Heart, Trophy, Users } from "lucide-react";
import Countdown from "../components/Countdown";

const NAVY = "#0A2463";
const RED = "#C8102E";

const TIERS = [
    { name: "Bronze", price: 500, color: "#CD7F32",
      perks: ["Logo on event signage", "Social media mention", "2 anniversary tickets"] },
    { name: "Silver", price: 1500, color: "#A8A8A8",
      perks: ["Bronze perks", "Half-page program ad", "4 anniversary tickets", "Sponsor reception access"] },
    { name: "Gold", price: 3000, color: "#D4AF37",
      perks: ["Silver perks", "Full-page program ad", "8 anniversary tickets", "Stage acknowledgment", "VIP table"] },
    { name: "Platinum", price: 5000, color: "#0A2463",
      perks: ["Gold perks", "Premier branding on banner", "16 tickets", "Speaking slot", "Named gala segment"] },
];

export default function Anniversary() {
    return (
        <div className="bg-white">
            <Countdown />

            <section className="max-w-5xl mx-auto px-6 lg:px-10 py-16">
                <div className="text-center">
                    <div className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold uppercase tracking-[0.2em] mb-6 border-2"
                         style={{ borderColor: RED, color: RED, backgroundColor: "#fff5f5" }}>
                        <Star className="h-3.5 w-3.5 fill-current" /> A decade of service
                    </div>
                    <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight" style={{ color: NAVY }}>
                        10 Years of Alpha Omega Phi
                    </h1>
                    <p className="mt-5 text-lg leading-relaxed text-slate-600 max-w-2xl mx-auto">
                        Ten years. Multiple chapters. One family. Join us in Atlanta to celebrate every Trendsetter who
                        helped build this organization — and to invest in the next decade of fellowship and service.
                    </p>
                </div>

                <div className="mt-12 grid sm:grid-cols-3 gap-5">
                    <FactCard icon={<CalendarIcon className="h-6 w-6" />} title="When" lines={["Tuesday, July 27, 2027", "6:00 PM — late"]} />
                    <FactCard icon={<MapPin className="h-6 w-6" />} title="Where" lines={["Atlanta, Georgia", "Venue TBA"]} />
                    <FactCard icon={<Users className="h-6 w-6" />} title="Who" lines={["Active, Alumni & Honorary", "Sponsors, Veterans, Family"]} />
                </div>
            </section>

            {/* Sponsorship */}
            <section className="bg-slate-50 py-16">
                <div className="max-w-6xl mx-auto px-6 lg:px-10">
                    <div className="text-center mb-12">
                        <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>Support the mission</div>
                        <h2 className="font-heading text-3xl sm:text-4xl font-black tracking-tight" style={{ color: NAVY }}>
                            Sponsorship tiers
                        </h2>
                        <p className="text-slate-600 mt-3 max-w-xl mx-auto">
                            Every dollar funds veteran assistance and community programs. AOP is a registered 501(c)(3) — contributions are tax-deductible.
                        </p>
                    </div>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
                        {TIERS.map((t) => (
                            <div key={t.name} className="relative bg-white rounded-2xl border-2 border-slate-200 p-6 shadow-warm hover:-translate-y-1 hover:shadow-warm-lg transition-all" data-testid={`sponsor-tier-${t.name.toLowerCase()}`}>
                                <div className="w-12 h-12 rounded-2xl grid place-items-center text-white" style={{ backgroundColor: t.color }}>
                                    <Trophy className="h-6 w-6" />
                                </div>
                                <div className="mt-4 font-heading text-2xl font-black" style={{ color: NAVY }}>{t.name}</div>
                                <div className="text-3xl font-black mt-1" style={{ color: RED }}>${t.price.toLocaleString()}</div>
                                <ul className="mt-4 space-y-1.5 text-sm text-slate-600">
                                    {t.perks.map((p) => (
                                        <li key={p} className="flex items-start gap-2">
                                            <Sparkles className="h-3.5 w-3.5 mt-1 shrink-0" style={{ color: t.color }} />
                                            <span>{p}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>

                    <div className="mt-10 text-center">
                        <Link to="/page/contact" className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-warm" style={{ backgroundColor: RED }} data-testid="sponsor-contact-btn">
                            Become a sponsor <ArrowRight className="h-4 w-4" />
                        </Link>
                    </div>
                </div>
            </section>

            <section className="max-w-4xl mx-auto px-6 lg:px-10 py-16 text-center">
                <Heart className="h-8 w-8 mx-auto mb-3" style={{ color: RED }} />
                <h2 className="font-heading text-2xl sm:text-3xl font-black tracking-tight" style={{ color: NAVY }}>
                    Every Trendsetter has a story
                </h2>
                <p className="mt-4 text-slate-600 leading-relaxed">
                    Want to share yours? Submit your decade-in-review photos and memories through the Photos tab —
                    we're building a commemorative program for the gala.
                </p>
                <Link to="/photos" className="inline-flex items-center gap-2 mt-6 text-primary font-bold hover:underline" data-testid="anniversary-photos-link">
                    Open Photos <ArrowRight className="h-4 w-4" />
                </Link>
            </section>
        </div>
    );
}

function FactCard({ icon, title, lines }) {
    return (
        <div className="bg-white rounded-2xl border-2 border-slate-200 p-6 shadow-warm text-center">
            <div className="w-12 h-12 rounded-2xl grid place-items-center mx-auto" style={{ backgroundColor: NAVY, color: "#fff" }}>
                {icon}
            </div>
            <div className="mt-3 text-xs uppercase tracking-widest font-bold" style={{ color: RED }}>{title}</div>
            {lines.map((l) => <div key={l} className="font-heading font-bold mt-1" style={{ color: NAVY }}>{l}</div>)}
        </div>
    );
}
