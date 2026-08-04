import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../lib/api";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import { Compass, MapPin, Users as UsersIcon, ArrowLeft, Star, X, Mail, Phone } from "lucide-react";

/**
 * Iter 134/135 — Regions overview page.
 *
 * Iter 135 adds: Governor spotlight card at the top of each region, an
 * interactive US SVG map colored by region, and a clickable state that
 * pops a drawer with the exact members who live there.
 */

// USPS 2-letter → US Census FIPS ID used by the react-simple-maps
// topojson. The topo assigns each feature a numeric `id` string matching
// the state's FIPS code, so this lets us color each polygon by region.
const USPS_TO_FIPS = {
    AL: "01", AK: "02", AZ: "04", AR: "05", CA: "06", CO: "08", CT: "09", DE: "10",
    DC: "11", FL: "12", GA: "13", HI: "15", ID: "16", IL: "17", IN: "18", IA: "19",
    KS: "20", KY: "21", LA: "22", ME: "23", MD: "24", MA: "25", MI: "26", MN: "27",
    MS: "28", MO: "29", MT: "30", NE: "31", NV: "32", NH: "33", NJ: "34", NM: "35",
    NY: "36", NC: "37", ND: "38", OH: "39", OK: "40", OR: "41", PA: "42", RI: "44",
    SC: "45", SD: "46", TN: "47", TX: "48", UT: "49", VT: "50", VA: "51", WA: "53",
    WV: "54", WI: "55", WY: "56",
};
const FIPS_TO_USPS = Object.fromEntries(Object.entries(USPS_TO_FIPS).map(([k, v]) => [v, k]));

// Public CDN — us-atlas states topojson. Small (~120 KB) and cached.
const US_TOPO_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";

export default function Regions() {
    const [regions, setRegions] = useState([]);
    const [unassigned, setUnassigned] = useState(0);
    const [loading, setLoading] = useState(true);
    // Drawer state: { region, state } — set when the user clicks a state
    // that belongs to a region, either on the map or in the state grid.
    const [drawer, setDrawer] = useState(null);
    const [drawerMembers, setDrawerMembers] = useState([]);
    const [drawerLoading, setDrawerLoading] = useState(false);

    async function reload() {
        try {
            const { data } = await api.get("/regions");
            setRegions(data.regions || []);
            setUnassigned(data.unassigned_count || 0);
        } finally {
            setLoading(false);
        }
    }
    useEffect(() => { reload(); }, []);

    // Build a lookup: USPS code → { region, state }. The interactive map
    // needs this to color each state polygon and route clicks.
    const stateIndex = useMemo(() => {
        const idx = {};
        for (const r of regions) {
            for (const s of r.states) {
                idx[s.code] = { region: r, state: s };
            }
        }
        return idx;
    }, [regions]);

    async function openStateDrawer(region, state) {
        setDrawer({ region, state });
        setDrawerMembers([]);
        setDrawerLoading(true);
        try {
            const { data } = await api.get(`/regions/${region.id}/members`, { params: { state_code: state.code } });
            setDrawerMembers(data.members || []);
        } finally {
            setDrawerLoading(false);
        }
    }

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
                    <>Our regions and how many members live in each state — <span className="font-semibold text-foreground">{grandTotal}</span> members across all regions.{unassigned > 0 && <> · <span className="text-amber-700 dark:text-amber-400">{unassigned} member{unassigned !== 1 ? "s" : ""} outside a region</span></>}</>
                )}
            </p>

            {/* -------------------- Interactive US map -------------------- */}
            {regions.length > 0 && (
                <div className="mt-8 bg-card rounded-2xl border border-border p-4 shadow-warm" data-testid="regions-us-map">
                    <div className="flex flex-wrap items-center gap-3 mb-2">
                        <span className="text-sm font-semibold">Interactive US map</span>
                        <span className="text-xs text-muted-foreground">Hover for state details · Click a member-populated state to see who lives there.</span>
                    </div>
                    <div className="flex flex-wrap gap-3 mb-3" data-testid="map-legend">
                        {regions.map((r) => (
                            <div key={r.id} className="flex items-center gap-2 text-xs">
                                <span className="inline-block h-3 w-3 rounded-sm border border-border" style={{ background: r.color }} />
                                <span>{r.name}</span>
                            </div>
                        ))}
                    </div>
                    <ComposableMap projection="geoAlbersUsa" width={980} height={520} style={{ width: "100%", height: "auto" }}>
                        <Geographies geography={US_TOPO_URL}>
                            {({ geographies }) =>
                                geographies.map((geo) => {
                                    const usps = FIPS_TO_USPS[String(geo.id).padStart(2, "0")] || "";
                                    const hit = stateIndex[usps];
                                    const fill = hit ? hit.region.color : "#E5E7EB";
                                    const clickable = hit && (hit.state.count || 0) > 0;
                                    return (
                                        <Geography
                                            key={geo.rsmKey}
                                            geography={geo}
                                            onClick={() => clickable && openStateDrawer(hit.region, hit.state)}
                                            data-testid={`map-state-${usps}`}
                                            style={{
                                                default: { fill, stroke: "#ffffff", strokeWidth: 0.6, outline: "none", cursor: clickable ? "pointer" : "default", opacity: hit ? 1 : 0.65 },
                                                hover: { fill: hit ? hit.region.color : "#D1D5DB", strokeWidth: 1, filter: hit ? "brightness(1.1)" : "none", outline: "none" },
                                                pressed: { outline: "none" },
                                            }}
                                        >
                                            <title>{usps}{hit ? ` · ${hit.state.name} · ${hit.state.count} member${hit.state.count !== 1 ? "s" : ""}` : ""}</title>
                                        </Geography>
                                    );
                                })
                            }
                        </Geographies>
                    </ComposableMap>
                </div>
            )}

            {/* -------------------- Region cards -------------------- */}
            <div className="mt-8 grid md:grid-cols-2 gap-5" data-testid="regions-grid">
                {regions.map((r) => (
                    <div
                        key={r.id}
                        className="bg-card rounded-2xl border border-border overflow-hidden shadow-warm"
                        data-testid={`region-card-${r.id}`}
                    >
                        <div
                            className="text-white px-6 py-5"
                            style={{ background: `linear-gradient(135deg, ${r.gradient_from} 0%, ${r.gradient_to} 100%)` }}
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <span className="text-2xl" aria-hidden>{r.emoji}</span>
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

                        {/* Governor spotlight */}
                        {r.governor && (
                            <div className="px-5 pt-4" data-testid={`region-governor-${r.id}`}>
                                <div className="rounded-xl border border-amber-500/40 bg-amber-50 dark:bg-amber-900/20 p-3">
                                    <div className="flex items-center gap-3">
                                        <div className="relative shrink-0">
                                            {r.governor.avatar_url ? (
                                                <img src={mediaUrl(r.governor.avatar_url)} alt={r.governor.name} className="h-12 w-12 rounded-full object-cover" />
                                            ) : (
                                                <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold text-primary">
                                                    {(r.governor.name || "?").slice(0, 2).toUpperCase()}
                                                </div>
                                            )}
                                            <Star className="h-4 w-4 text-amber-500 fill-amber-400 absolute -bottom-0.5 -right-0.5 drop-shadow" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="text-[10px] uppercase tracking-widest text-amber-700 dark:text-amber-400 font-bold">Governor</div>
                                            <div className="font-semibold text-sm truncate" data-testid={`governor-name-${r.id}`}>{r.governor.name}</div>
                                            {(r.governor.email || r.governor.phone) && (
                                                <div className="text-xs text-muted-foreground flex flex-wrap gap-x-3">
                                                    {r.governor.email && <span className="inline-flex items-center gap-1"><Mail className="h-3 w-3" />{r.governor.email}</span>}
                                                    {r.governor.phone && <span className="inline-flex items-center gap-1"><Phone className="h-3 w-3" />{r.governor.phone}</span>}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    {r.governor.bio && (
                                        <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 leading-snug line-clamp-3" data-testid={`governor-bio-${r.id}`}>
                                            {r.governor.bio}
                                        </p>
                                    )}
                                </div>
                            </div>
                        )}

                        <div className="p-5">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                {r.states.map((s) => {
                                    const zero = (s.count || 0) === 0;
                                    return (
                                        <button
                                            key={s.code}
                                            type="button"
                                            disabled={zero}
                                            onClick={() => openStateDrawer(r, s)}
                                            className={`flex items-center justify-between px-3 py-2 rounded-xl border text-left transition ${zero ? "border-border/60 text-muted-foreground cursor-not-allowed" : "border-border bg-muted/30 hover:border-primary hover:bg-primary/5 cursor-pointer"}`}
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
                                        </button>
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
                ))}
                {!loading && regions.length === 0 && (
                    <div className="text-muted-foreground col-span-full">No regions configured yet.</div>
                )}
            </div>

            {/* -------------------- State drawer -------------------- */}
            {drawer && (
                <div
                    className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6"
                    onClick={() => setDrawer(null)}
                    data-testid="region-state-drawer"
                >
                    <div
                        className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[85vh] overflow-hidden shadow-warm flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div
                            className="text-white px-5 py-4 flex items-center justify-between"
                            style={{ background: `linear-gradient(135deg, ${drawer.region.gradient_from} 0%, ${drawer.region.gradient_to} 100%)` }}
                        >
                            <div>
                                <div className="text-[10px] uppercase tracking-widest opacity-85">{drawer.region.name}</div>
                                <div className="font-heading text-xl font-bold leading-tight">
                                    {drawer.state.name} <span className="text-sm opacity-80">({drawer.state.code})</span>
                                </div>
                                <div className="text-xs opacity-85 mt-0.5">
                                    {drawerLoading ? "Loading…" : `${drawerMembers.length} member${drawerMembers.length !== 1 ? "s" : ""}`}
                                </div>
                            </div>
                            <button
                                onClick={() => setDrawer(null)}
                                className="rounded-full p-1.5 hover:bg-white/20"
                                data-testid="drawer-close-btn"
                                aria-label="Close"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 space-y-2">
                            {drawerLoading && <div className="text-sm text-muted-foreground p-6 text-center">Loading members…</div>}
                            {!drawerLoading && drawerMembers.length === 0 && <div className="text-sm text-muted-foreground p-6 text-center">No members found in this state.</div>}
                            {drawerMembers.map((m) => (
                                <Link
                                    key={m.id}
                                    to={`/directory?user=${m.id}`}
                                    className="flex items-center gap-3 p-3 rounded-xl border border-border hover:border-primary hover:bg-primary/5 transition"
                                    data-testid={`drawer-member-${m.id}`}
                                >
                                    {m.avatar_url ? (
                                        <img src={mediaUrl(m.avatar_url)} alt={m.name} className="h-10 w-10 rounded-full object-cover" />
                                    ) : (
                                        <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold text-primary">
                                            {(m.name || "?").slice(0, 2).toUpperCase()}
                                        </div>
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium truncate">{m.name}</div>
                                        <div className="text-xs text-muted-foreground truncate">
                                            {[m.line_name && `"${m.line_name}"`, m.city, m.state].filter(Boolean).join(" · ")}
                                        </div>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
