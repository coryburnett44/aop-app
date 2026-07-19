import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Link } from "react-router-dom";
import { Compass, MapPin, Users as UsersIcon, ArrowLeft } from "lucide-react";

/**
 * Iter 134 — Regions overview page.
 *
 * Companion to the /chapters page. Shows the 4 official AOP regions with
 * per-state member counts sourced from the new `GET /api/regions` endpoint.
 * Each region card lists every state we recognize (with zero-count rows shown
 * greyed-out so admins can see coverage at a glance), a "Filter members" CTA
 * that deep-links into the Directory pre-filtered by region, and a total
 * count badge in the region header.
 */
const REGION_STYLES = {
    "central-east":  { bar: "from-sky-500 to-blue-600",     icon: "🌾" },
    "gulf-coast":    { bar: "from-orange-500 to-red-600",   icon: "🌊" },
    "southeastern":  { bar: "from-emerald-500 to-teal-600", icon: "🌴" },
    "mid-atlantic":  { bar: "from-violet-500 to-indigo-600", icon: "🏛️" },
};

export default function Regions() {
    const [regions, setRegions] = useState([]);
    const [unassigned, setUnassigned] = useState(0);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/regions")
            .then(({ data }) => {
                setRegions(data.regions || []);
                setUnassigned(data.unassigned_count || 0);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const grandTotal = regions.reduce((sum, r) => sum + (r.total || 0), 0);

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex items-center gap-3 mb-2">
                <Link to="/chapters" className="text-xs text-primary hover:underline inline-flex items-center gap-1" data-testid="regions-back-to-chapters">
                    <ArrowLeft className="h-3.5 w-3.5" /> Chapters
                </Link>
                <span className="text-xs text-muted-foreground">·</span>
                <span className="text-xs text-muted-foreground">Regions</span>
            </div>
            <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight" data-testid="regions-page-title">Regions</h1>
            <p className="text-muted-foreground mt-2">
                {loading ? "Loading…" : (
                    <>Our four regions and how many members live in each state — <span className="font-semibold text-foreground">{grandTotal}</span> members across all regions.{unassigned > 0 && <> · <span className="text-amber-700 dark:text-amber-400">{unassigned} member{unassigned !== 1 ? "s" : ""} outside a region</span></>}</>
                )}
            </p>

            <div className="mt-10 grid md:grid-cols-2 gap-5" data-testid="regions-grid">
                {regions.map((r) => {
                    const style = REGION_STYLES[r.id] || REGION_STYLES["central-east"];
                    return (
                        <div
                            key={r.id}
                            className="bg-card rounded-2xl border border-border overflow-hidden shadow-warm"
                            data-testid={`region-card-${r.id}`}
                        >
                            <div className={`bg-gradient-to-r ${style.bar} text-white px-6 py-5`}>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <span className="text-2xl" aria-hidden>{style.icon}</span>
                                        <div>
                                            <h3 className="font-heading text-xl font-bold leading-tight" data-testid={`region-name-${r.id}`}>{r.name}</h3>
                                            <div className="text-xs opacity-85">{r.description}</div>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-3xl font-black tabular-nums" data-testid={`region-total-${r.id}`}>{r.total}</div>
                                        <div className="text-[10px] uppercase tracking-widest opacity-85">member{r.total !== 1 ? "s" : ""}</div>
                                    </div>
                                </div>
                            </div>

                            <div className="p-5">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                    {r.states.map((s) => {
                                        const zero = (s.count || 0) === 0;
                                        return (
                                            <div
                                                key={s.code}
                                                className={`flex items-center justify-between px-3 py-2 rounded-xl border ${zero ? "border-border/60 text-muted-foreground" : "border-border bg-muted/30"}`}
                                                data-testid={`region-state-${r.id}-${s.code}`}
                                            >
                                                <div className="flex items-center gap-2 text-sm">
                                                    <MapPin className={`h-3.5 w-3.5 ${zero ? "opacity-40" : "text-primary"}`} />
                                                    <span className={zero ? "" : "font-medium text-foreground"}>{s.name}</span>
                                                    <span className={`text-[10px] font-mono ${zero ? "opacity-40" : "text-muted-foreground"}`}>{s.code}</span>
                                                </div>
                                                <span className={`inline-flex items-center gap-1 text-sm font-semibold tabular-nums ${zero ? "" : "text-primary"}`}>
                                                    <UsersIcon className="h-3.5 w-3.5" />{s.count}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between">
                                    <div className="text-xs text-muted-foreground flex items-center gap-1">
                                        <Compass className="h-3.5 w-3.5" /> {r.states.length} states
                                    </div>
                                    <Link
                                        to={`/directory?region=${r.id}`}
                                        className="text-xs font-semibold text-primary hover:underline"
                                        data-testid={`region-filter-link-${r.id}`}
                                    >
                                        Filter members in this region →
                                    </Link>
                                </div>
                            </div>
                        </div>
                    );
                })}
                {!loading && regions.length === 0 && (
                    <div className="text-muted-foreground col-span-full">No regions configured yet.</div>
                )}
            </div>
        </div>
    );
}
