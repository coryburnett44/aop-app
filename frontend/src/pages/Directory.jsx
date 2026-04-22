import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Input } from "../components/ui/input";
import { Search } from "lucide-react";

export default function Directory() {
    const [members, setMembers] = useState([]);
    const [q, setQ] = useState("");

    const load = async () => {
        const { data } = await api.get("/members", { params: q ? { q } : {} });
        setMembers(data);
    };

    useEffect(() => {
        const t = setTimeout(load, 200);
        return () => clearTimeout(t);
    }, [q]);

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Members</h1>
                    <p className="text-muted-foreground mt-2">{members.length} people you might know.</p>
                </div>
                <div className="relative w-full sm:w-80">
                    <Search className="h-4 w-4 absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        placeholder="Search by name or interest…"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        className="rounded-full pl-11"
                        data-testid="directory-search"
                    />
                </div>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                {members.map((m) => {
                    const initials = (m.name || m.email).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                    return (
                        <div
                            key={m.id}
                            className="bg-muted/40 border border-black/5 rounded-2xl p-6 hover:-translate-y-1 hover:shadow-warm transition-all"
                            data-testid={`member-card-${m.id}`}
                        >
                            <Avatar className="h-16 w-16 border-2 border-white shadow-warm">
                                {m.avatar_url && <AvatarImage src={m.avatar_url} alt={m.name} />}
                                <AvatarFallback className="bg-primary/20 text-primary font-bold text-lg">{initials}</AvatarFallback>
                            </Avatar>
                            <h3 className="font-heading font-semibold text-lg mt-4">{m.name}</h3>
                            <div className="text-xs text-muted-foreground">{m.city || "—"}</div>
                            {m.bio && <p className="text-sm text-muted-foreground mt-3 line-clamp-2 leading-relaxed">{m.bio}</p>}
                            {m.interests?.length > 0 && (
                                <div className="mt-4 flex flex-wrap gap-1.5">
                                    {m.interests.slice(0, 3).map((i) => (
                                        <span key={i} className="text-[10px] bg-secondary/40 rounded-full px-2 py-0.5 uppercase tracking-wider font-semibold">
                                            {i}
                                        </span>
                                    ))}
                                </div>
                            )}
                            {m.role === "admin" && (
                                <div className="mt-3 inline-block text-[10px] uppercase tracking-wider bg-primary/15 text-primary rounded-full px-2 py-0.5 font-semibold">
                                    Admin
                                </div>
                            )}
                        </div>
                    );
                })}
                {members.length === 0 && <div className="col-span-full text-muted-foreground">No members match that search.</div>}
            </div>
        </div>
    );
}
