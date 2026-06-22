import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Heart, Target } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function Donations() {
    const { user } = useAuth();
    const [causes, setCauses] = useState([]);

    const load = () => api.get("/causes?active_only=true").then(({ data }) => setCauses(data));
    useEffect(() => { load().catch(() => {}); }, []);

    return (
        <div className="bg-slate-50 min-h-screen">
            <section className="bg-white border-b-2" style={{ borderColor: RED }}>
                <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>Support the mission</div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter" style={{ color: NAVY }}>Donations & Causes</h1>
                    <p className="text-slate-600 mt-3 max-w-2xl">Every contribution funds a brother, a sister, a family, or a future Trendsetter.</p>
                </div>
            </section>

            <section className="max-w-6xl mx-auto px-6 lg:px-10 py-10">
                {causes.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <Heart className="h-12 w-12 mx-auto text-slate-300" />
                        <p className="mt-3">No active causes right now. Check back soon.</p>
                    </div>
                ) : (
                    <div className="grid lg:grid-cols-2 gap-6">
                        {causes.map((c) => <CauseCard key={c.id} cause={c} canPledge={!!user} onPledged={load} />)}
                    </div>
                )}
            </section>
        </div>
    );
}

function CauseCard({ cause, canPledge, onPledged }) {
    const pct = cause.goal_amount > 0 ? Math.min(100, Math.round((cause.raised_amount / cause.goal_amount) * 100)) : 0;
    return (
        <div className="bg-white rounded-2xl overflow-hidden border-2 border-slate-200 shadow-warm flex flex-col" data-testid={`cause-${cause.id}`}>
            <div className="aspect-[2/1] bg-slate-100 overflow-hidden">
                {cause.cover_image && <img src={cause.cover_image} alt={cause.title} className="w-full h-full object-contain" />}
            </div>
            <div className="p-6 flex-1 flex flex-col">
                <div className="text-[10px] uppercase tracking-widest font-bold" style={{ color: RED }}>{cause.category}</div>
                <h3 className="font-heading font-black text-xl mt-1 leading-tight" style={{ color: NAVY }}>{cause.title}</h3>
                <p className="text-sm text-slate-600 mt-3 leading-relaxed">{cause.description}</p>

                <div className="mt-5 flex items-end justify-between gap-3">
                    <div>
                        <div className="font-heading font-black text-2xl" style={{ color: NAVY }}>${cause.raised_amount.toFixed(0)}</div>
                        <div className="text-xs text-slate-500"><Target className="h-3 w-3 inline" /> of ${cause.goal_amount.toFixed(0)} goal</div>
                    </div>
                    <div className="text-right">
                        <div className="font-heading font-black text-2xl" style={{ color: RED }}>{pct}%</div>
                        <div className="text-xs text-slate-500">{cause.donor_count} donor{cause.donor_count !== 1 ? "s" : ""}</div>
                    </div>
                </div>
                <div className="mt-3 w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${NAVY}, ${RED})` }} />
                </div>

                <div className="mt-6 flex gap-2">
                    {canPledge ? (
                        cause.zeffy_url ? (
                            <Button
                                asChild
                                className="flex-1 rounded-full text-white shadow-warm hover:opacity-90"
                                style={{ backgroundColor: RED }}
                                data-testid={`zeffy-donate-${cause.id}`}
                            >
                                <a href={cause.zeffy_url} target="_blank" rel="noopener noreferrer">
                                    <Heart className="h-4 w-4 mr-1.5 inline" /> Donate via Zeffy
                                </a>
                            </Button>
                        ) : (
                            // Donations through PayPal in-app checkout were retired.
                            // Until an officer adds a Zeffy URL to this cause, members
                            // see a friendly hand-off message rather than a dead button.
                            <div className="flex-1 rounded-2xl bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-600" data-testid={`donate-unavailable-${cause.id}`}>
                                Online giving for this cause is being set up. Contact your chapter officers to donate directly in the meantime.
                            </div>
                        )
                    ) : (
                        <Button asChild className="flex-1 rounded-full text-white shadow-warm" style={{ backgroundColor: RED }}>
                            <a href="/login">Log in to donate</a>
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
}

// PledgeDialog removed — the in-app PayPal donation checkout was retired.
// All donations now route to each cause's Zeffy URL. Causes without a Zeffy
// URL show a "contact your chapter" hand-off message inside the cause card.
