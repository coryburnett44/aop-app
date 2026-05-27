import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { format, parseISO } from "date-fns";
import { Flame } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function Omega() {
    const [members, setMembers] = useState([]);
    useEffect(() => { api.get("/omega").then(({ data }) => setMembers(data)).catch(() => {}); }, []);

    return (
        <div className="bg-gradient-to-b from-slate-50 to-white min-h-screen">
            <section className="relative overflow-hidden border-b-4" style={{ borderColor: NAVY }}>
                <div className="absolute inset-0 opacity-10" style={{ backgroundImage: `radial-gradient(circle at 30% 30%, ${NAVY} 0%, transparent 60%), radial-gradient(circle at 70% 70%, ${RED} 0%, transparent 60%)` }} />
                <div className="relative max-w-5xl mx-auto px-6 lg:px-10 py-16 text-center">
                    <div className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[10px] font-bold uppercase tracking-[0.25em] mb-5 text-white" style={{ backgroundColor: NAVY }}>
                        <Flame className="h-3.5 w-3.5" /> In Memoriam
                    </div>
                    <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-black tracking-tighter" style={{ color: NAVY }}>
                        Omega Chapter
                    </h1>
                    <p className="mt-5 text-base sm:text-lg text-slate-600 max-w-2xl mx-auto leading-relaxed">
                        Honoring the Trendsetters who answered their final call. Their service, sacrifice, and brotherhood live on in every member who follows.
                    </p>
                </div>
            </section>

            <section className="max-w-6xl mx-auto px-6 lg:px-10 py-14">
                {members.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <p className="font-heading text-xl mb-2" style={{ color: NAVY }}>The Omega Chapter stands ready.</p>
                        <p className="text-sm">No brothers or sisters have entered Omega yet. May it remain that way for many years.</p>
                    </div>
                ) : (
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="omega-grid">
                        {members.map((m) => {
                            const initials = (m.name || m.email).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                            return (
                                <div
                                    key={m.id}
                                    className="bg-white rounded-2xl border-2 p-6 shadow-warm relative overflow-hidden"
                                    style={{ borderColor: `${NAVY}25` }}
                                    data-testid={`omega-${m.id}`}
                                >
                                    <div className="absolute top-0 right-0 px-3 py-1 text-[10px] uppercase tracking-widest font-bold text-white" style={{ backgroundColor: NAVY }}>
                                        Omega ✦
                                    </div>
                                    <Avatar className="h-20 w-20 border-4 border-white shadow-warm mx-auto">
                                        {m.avatar_url && <AvatarImage src={m.avatar_url} />}
                                        <AvatarFallback className="text-white font-black text-2xl" style={{ backgroundColor: NAVY }}>{initials}</AvatarFallback>
                                    </Avatar>
                                    <h3 className="font-heading font-bold text-xl mt-4 text-center" style={{ color: NAVY }}>{m.name}</h3>
                                    {m.line_name && <div className="text-xs font-bold uppercase tracking-widest text-center mt-1" style={{ color: RED }}>"{m.line_name}"</div>}
                                    <div className="text-xs text-slate-500 text-center mt-2 space-y-0.5">
                                        {m.branch_of_service && <div>{m.branch_of_service}</div>}
                                        {m.city && <div>{m.city}</div>}
                                    </div>
                                    <div className="mt-4 pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
                                        {m.deceased_at && <>Entered Omega · {format(parseISO(m.deceased_at), "MMM d, yyyy")}</>}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </section>
        </div>
    );
}
