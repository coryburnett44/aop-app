import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { MapPin, Compass, Users as UsersIcon } from "lucide-react";

export default function Chapters() {
    const [chapters, setChapters] = useState([]);
    useEffect(() => { api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {}); }, []);

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Chapters</h1>
            <p className="text-muted-foreground mt-2">Our regions, states, and chapter communities.</p>

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
                    </div>
                ))}
                {chapters.length === 0 && <div className="text-muted-foreground col-span-full">No chapters yet.</div>}
            </div>
        </div>
    );
}
