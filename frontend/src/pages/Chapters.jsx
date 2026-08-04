import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../lib/api";
import { MapPin, Compass, Users as UsersIcon, Map as MapIcon, Star } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";

export default function Chapters() {
    const [chapters, setChapters] = useState([]);
    useEffect(() => { api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {}); }, []);

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Chapters</h1>
                    <p className="text-muted-foreground mt-2">Our regions, states, and chapter communities.</p>
                </div>
                <Link
                    to="/regions"
                    className="inline-flex items-center gap-2 rounded-full bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold hover:bg-primary/90 shadow-warm self-start"
                    data-testid="chapters-view-regions-btn"
                >
                    <MapIcon className="h-4 w-4" /> View Regions
                </Link>
            </div>

            <div className="mt-10 grid md:grid-cols-2 gap-5">
                {chapters.map((c) => (
                    <div key={c.id} className="bg-card rounded-2xl border border-border p-6 shadow-warm" data-testid={`chapter-${c.id}`}>
                        <div className="flex items-center gap-4">
                            {c.logo_url ? (
                                <img
                                    src={mediaUrl(c.logo_url)}
                                    alt={`${c.name} logo`}
                                    className="w-16 h-16 rounded-2xl object-contain border-2 border-border shrink-0"
                                    data-testid={`chapter-logo-${c.id}`}
                                />
                            ) : (
                                <div className="w-16 h-16 rounded-2xl bg-primary/10 text-primary grid place-items-center font-heading font-black text-xl shrink-0">
                                    {c.name.split(" ").map((s) => s[0]).join("").slice(0, 2)}
                                </div>
                            )}
                            <div>
                                <h3 className="font-heading text-xl font-bold">{c.name}</h3>
                                <div className="text-xs text-muted-foreground">Chartered {c.founded_year || "—"}</div>
                            </div>
                        </div>
                        <div className="mt-4 space-y-1 text-sm text-muted-foreground">
                            {c.region && <div className="flex items-center gap-2"><Compass className="h-4 w-4" /> {c.region} region</div>}
                            {c.state && <div className="flex items-center gap-2"><MapPin className="h-4 w-4" /> {c.state}</div>}
                            <div className="flex items-center gap-2"><UsersIcon className="h-4 w-4" /> {c.member_count} member{c.member_count !== 1 ? "s" : ""}</div>
                        </div>
                        {c.description && <p className="text-sm mt-4 leading-relaxed">{c.description}</p>}
                        {c.lieutenant_governor && (
                            <div
                                className="mt-4 flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-3"
                                data-testid={`chapter-lt-governor-${c.id}`}
                            >
                                <Avatar className="h-11 w-11 shrink-0 border border-primary/30">
                                    <AvatarImage src={mediaUrl(c.lieutenant_governor.avatar_url)} alt={c.lieutenant_governor.name} />
                                    <AvatarFallback className="bg-primary/10 text-primary font-semibold">
                                        {(c.lieutenant_governor.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("")}
                                    </AvatarFallback>
                                </Avatar>
                                <div className="min-w-0">
                                    <div className="flex items-center gap-1.5">
                                        <Star className="h-3 w-3 text-primary fill-primary" />
                                        <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">Lieutenant Governor</span>
                                    </div>
                                    <div className="font-semibold text-sm truncate">{c.lieutenant_governor.name}</div>
                                    {c.lieutenant_governor.title && <div className="text-xs text-muted-foreground truncate">{c.lieutenant_governor.title}</div>}
                                </div>
                            </div>
                        )}
                    </div>
                ))}
                {chapters.length === 0 && <div className="text-muted-foreground col-span-full">No chapters yet.</div>}
            </div>
        </div>
    );
}
