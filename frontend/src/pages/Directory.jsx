import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import {
    Search, Mail, Phone, MapPin, Calendar, Shield,
    Facebook, Instagram, Linkedin, Twitter, Youtube, Globe,
} from "lucide-react";
import { format, parseISO } from "date-fns";

const SOCIAL_PLATFORMS = [
    { key: "facebook_url", label: "Facebook", icon: Facebook, color: "#1877F2" },
    { key: "instagram_url", label: "Instagram", icon: Instagram, color: "#E4405F" },
    { key: "linkedin_url", label: "LinkedIn", icon: Linkedin, color: "#0A66C2" },
    { key: "twitter_url", label: "X", icon: Twitter, color: "#000000" },
    { key: "tiktok_url", label: "TikTok", icon: null, glyph: "TT", color: "#000000" },
    { key: "pinterest_url", label: "Pinterest", icon: null, glyph: "P", color: "#E60023" },
    { key: "youtube_url", label: "YouTube", icon: Youtube, color: "#FF0000" },
    { key: "website_url", label: "Website", icon: Globe, color: "#0A2463" },
];

function SocialIcons({ member, size = "h-7 w-7", stop = true }) {
    const items = SOCIAL_PLATFORMS.filter((p) => member[p.key]);
    if (items.length === 0) return null;
    return (
        <div className="flex flex-wrap gap-1.5 mt-3">
            {items.map((p) => {
                const Icon = p.icon;
                const href = /^https?:\/\//i.test(member[p.key]) ? member[p.key] : `https://${member[p.key]}`;
                return (
                    <a
                        key={p.key}
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => { if (stop) e.stopPropagation(); }}
                        className={`${size} rounded-full grid place-items-center text-white hover:scale-110 transition-transform shadow-sm`}
                        style={{ backgroundColor: p.color }}
                        title={p.label}
                        aria-label={`${p.label} profile`}
                        data-testid={`member-social-${p.key}`}
                    >
                        {Icon ? <Icon className="h-3.5 w-3.5" /> : <span className="text-[10px] font-bold">{p.glyph}</span>}
                    </a>
                );
            })}
        </div>
    );
}

export default function Directory() {
    const [members, setMembers] = useState([]);
    const [chapters, setChapters] = useState([]);
    const [q, setQ] = useState("");
    const [active, setActive] = useState(null);

    const load = async () => {
        const { data } = await api.get("/members", { params: q ? { q } : {} });
        setMembers(data);
    };

    useEffect(() => {
        const t = setTimeout(load, 200);
        return () => clearTimeout(t);
    }, [q]);

    useEffect(() => {
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
    }, []);

    const chapterName = (id) => chapters.find((c) => c.id === id)?.name || "—";

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Members</h1>
                    <p className="text-muted-foreground mt-2">{members.length} brothers and sisters · click a card for the full member profile.</p>
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

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {members.map((m) => {
                    const initials = (m.name || m.email).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                    const fullAddress = [m.address, m.city, m.state, m.zip_code, m.country].filter(Boolean).join(", ");
                    return (
                        <button
                            key={m.id}
                            onClick={() => setActive(m)}
                            className="text-left bg-card border border-border rounded-2xl overflow-hidden hover:-translate-y-1 hover:shadow-warm transition-all focus:outline-none focus:ring-2 focus:ring-primary/40 flex flex-col"
                            data-testid={`member-card-${m.id}`}
                        >
                            {/* Rectangular member photo */}
                            <div className="aspect-[4/3] w-full bg-muted/40 border-b border-border overflow-hidden flex items-center justify-center">
                                {m.avatar_url ? (
                                    <img
                                        src={mediaUrl(m.avatar_url)}
                                        alt={m.name}
                                        className="w-full h-full object-cover"
                                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
                                    />
                                ) : (
                                    <span className="font-heading font-black text-6xl text-primary/40">{initials}</span>
                                )}
                            </div>
                            <div className="p-5 flex-1 flex flex-col">
                                <div className="flex items-start justify-between gap-2 mb-1">
                                    <h3 className="font-heading font-bold text-xl leading-tight flex-1">{m.name}</h3>
                                </div>
                                {m.line_name && <div className="text-xs font-bold uppercase tracking-widest text-primary mb-2">"{m.line_name}"</div>}
                                <div className="space-y-1.5 text-xs text-foreground/80">
                                    {m.email && <div className="flex items-start gap-2"><Mail className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" /><span className="break-all">{m.email}</span></div>}
                                    {m.phone && <div className="flex items-start gap-2"><Phone className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" />{m.phone}</div>}
                                    {fullAddress && <div className="flex items-start gap-2"><MapPin className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" /><span>{fullAddress}</span></div>}
                                    <div className="flex items-start gap-2"><Shield className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" />{chapterName(m.chapter_id)}</div>
                                </div>
                                <div className="mt-3 flex flex-wrap gap-1.5">
                                    {m.role === "admin" && (
                                        <span className="text-[10px] uppercase tracking-wider bg-primary/15 text-primary rounded-full px-2 py-0.5 font-semibold">Admin</span>
                                    )}
                                    <StatusPill status={m.status} />
                                    {m.membership_tier && m.membership_tier !== "standard" && (
                                        <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-accent/40">{m.membership_tier}</span>
                                    )}
                                </div>
                                <SocialIcons member={m} />
                            </div>
                        </button>
                    );
                })}
                {members.length === 0 && <div className="col-span-full text-muted-foreground">No members match that search.</div>}
            </div>

            <Dialog open={!!active} onOpenChange={(o) => !o && setActive(null)}>
                <DialogContent className="max-w-lg">
                    <DialogHeader><DialogTitle className="font-heading text-2xl">Member profile</DialogTitle></DialogHeader>
                    {active && <MemberDetail member={active} chapters={chapters} />}
                </DialogContent>
            </Dialog>
        </div>
    );
}

function MemberDetail({ member, chapters }) {
    const [d, setD] = useState(member);
    useEffect(() => {
        api.get(`/members/${member.id}`).then(({ data }) => setD(data)).catch(() => {});
    }, [member.id]);
    const chapter = chapters.find((c) => c.id === d.chapter_id);
    const initials = (d.name || d.email).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
    const fullAddress = [d.address, d.city, d.state, d.zip_code, d.country].filter(Boolean).join(", ");
    return (
        <div data-testid={`member-detail-${d.id}`}>
            <div className="flex items-center gap-4">
                <Avatar className="h-20 w-20 border-2 border-white shadow-warm">
                    {d.avatar_url && <AvatarImage src={mediaUrl(d.avatar_url)} />}
                    <AvatarFallback className="bg-primary/20 text-primary font-bold text-2xl">{initials}</AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                    <div className="font-heading text-xl font-bold">{d.name}</div>
                    {d.line_name && <div className="text-xs font-bold uppercase tracking-widest text-primary">"{d.line_name}"</div>}
                    <div className="mt-2 flex flex-wrap gap-2 items-center">
                        {d.role === "admin" && <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/15 text-primary inline-flex items-center gap-1"><Shield className="h-3 w-3" />Admin</span>}
                        <StatusPill status={d.status} />
                        {d.membership_tier && <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-accent/40">{d.membership_tier}</span>}
                    </div>
                </div>
            </div>

            <div className="mt-5 space-y-3 text-sm">
                {d.email && <Row icon={<Mail className="h-4 w-4" />}>{d.email}</Row>}
                {d.phone && <Row icon={<Phone className="h-4 w-4" />}>{d.phone}</Row>}
                {fullAddress && <Row icon={<MapPin className="h-4 w-4" />}>{fullAddress}</Row>}
                {chapter && <Row icon={<Shield className="h-4 w-4" />}>{chapter.name}{chapter.region ? ` · ${chapter.region}` : ""}{chapter.state ? ` (${chapter.state})` : ""}</Row>}
                {d.branch_of_service && <Row icon={<Shield className="h-4 w-4" />}>{d.branch_of_service}</Row>}
                {d.created_at && <Row icon={<Calendar className="h-4 w-4" />}>Joined {format(parseISO(d.created_at), "MMM d, yyyy")}</Row>}
            </div>

            <SocialIcons member={d} size="h-9 w-9" stop={false} />

            {d.bio && (
                <div className="mt-5 pt-4 border-t">
                    <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-1">Bio</div>
                    <p className="text-sm leading-relaxed">{d.bio}</p>
                </div>
            )}
            {d.interests?.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                    {d.interests.map((i) => (
                        <span key={i} className="text-[10px] bg-secondary/40 rounded-full px-2 py-0.5 uppercase tracking-wider font-semibold">{i}</span>
                    ))}
                </div>
            )}
        </div>
    );
}

function Row({ icon, children }) {
    return (
        <div className="flex items-center gap-3">
            <div className="text-muted-foreground">{icon}</div>
            <div className="break-words">{children}</div>
        </div>
    );
}

function StatusPill({ status }) {
    const map = {
        active: "bg-green-500/15 text-green-700",
        inactive: "bg-slate-500/15 text-slate-600",
        grace: "bg-amber-500/20 text-amber-700",
        expired: "bg-destructive/15 text-destructive",
        deceased: "bg-black/10 text-black",
    };
    return (
        <span className={`text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 ${map[status] || "bg-muted"}`}>
            {status === "deceased" ? "Omega ✦" : status}
        </span>
    );
}
