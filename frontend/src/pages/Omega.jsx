import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { format, parseISO } from "date-fns";
import { Flame, Plus, Pencil, Trash2, Upload as UploadIcon, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";

const NAVY = "#0A2463";
const RED = "#C8102E";

// ---------- Background palette ----------
// Frontend-only mapping so admins can preview without server round-trips.
const BACKGROUNDS = {
    "american-flag": {
        label: "American Flag",
        css: `
            linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,255,255,0.78) 100%),
            repeating-linear-gradient(180deg, ${RED} 0px, ${RED} 22px, #FFFFFF 22px, #FFFFFF 44px),
            radial-gradient(circle at 18% 20%, ${NAVY} 0%, ${NAVY} 32%, transparent 33%)
        `,
        text: "#0A2463",
        accent: "#C8102E",
    },
    "navy-starfield": {
        label: "Navy Starfield",
        css: `
            radial-gradient(2px 2px at 12% 18%, #FFFFFF 50%, transparent 51%),
            radial-gradient(1.5px 1.5px at 28% 62%, #FFFFFF 50%, transparent 51%),
            radial-gradient(2px 2px at 55% 30%, #FFFFFF 50%, transparent 51%),
            radial-gradient(1px 1px at 72% 78%, #FFFFFF 50%, transparent 51%),
            radial-gradient(2.5px 2.5px at 86% 22%, #FFFFFF 50%, transparent 51%),
            radial-gradient(1.5px 1.5px at 40% 88%, #FFFFFF 50%, transparent 51%),
            linear-gradient(135deg, #050B1F 0%, #0A2463 60%, #1B2845 100%)
        `,
        text: "#FFFFFF",
        accent: "#E8C547",
    },
    marble: {
        label: "Marble",
        css: "linear-gradient(135deg, #ECECEC 0%, #FFFFFF 50%, #E2E2E2 100%)",
        text: "#1F2937",
        accent: "#0A2463",
    },
    sepia: {
        label: "Sepia Parchment",
        css: "linear-gradient(135deg, #F4ECD8 0%, #E9DDC0 100%), radial-gradient(circle at 20% 30%, rgba(139,90,43,0.08), transparent 50%)",
        text: "#3D2E1E",
        accent: "#8B0000",
    },
    "solid-red": {
        label: "Solid Red",
        css: RED,
        text: "#FFFFFF",
        accent: "#FFFFFF",
    },
    "solid-navy": {
        label: "Solid Navy",
        css: NAVY,
        text: "#FFFFFF",
        accent: "#E8C547",
    },
    "solid-white": {
        label: "Solid White",
        css: "#FFFFFF",
        text: "#0A2463",
        accent: "#C8102E",
    },
};

const TEMPLATES = {
    biography: { label: "Biography", description: "Long-form layout with cover photo, full synopsis, dates and epitaph." },
    "memorial-card": { label: "Memorial Card", description: "Formal portrait with name & dates centered + a short tribute quote." },
    "in-service": { label: "In Service", description: "Military brief: rank, branch and service dates with photo and summary." },
};

export default function Omega() {
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [hero, setHero] = useState({ image_url: "", title: "", caption: "" });
    const isAdmin = user?.role === "admin";

    async function load() {
        try {
            const [{ data }, { data: h }] = await Promise.all([
                api.get("/omega"),
                api.get("/omega/hero").catch(() => ({ data: { image_url: "", title: "", caption: "" } })),
            ]);
            setItems(data);
            setHero(h || { image_url: "", title: "", caption: "" });
        } catch { /* ignore */ }
        setLoading(false);
    }
    useEffect(() => { load(); }, []);

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
                    {isAdmin && (
                        <div className="mt-7 flex flex-wrap gap-3 justify-center">
                            <TributeBuilder onSaved={load} trigger={(
                                <Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="add-tribute-btn">
                                    <Plus className="h-4 w-4 mr-1.5" /> Add tribute
                                </Button>
                            )} />
                            <HeroEditor hero={hero} onSaved={load} />
                        </div>
                    )}
                </div>
            </section>

            {/* Hero featured photo (admin-managed banner like the Omega Chapter clubexpress page) */}
            {hero.image_url && (
                <section className="max-w-5xl mx-auto px-6 lg:px-10 pt-10" data-testid="omega-hero-banner">
                    <div className="rounded-3xl overflow-hidden border-4 shadow-warm bg-white" style={{ borderColor: NAVY }}>
                        <img src={hero.image_url} alt={hero.title || "Omega Chapter featured"} className="w-full h-auto max-h-[520px] object-cover" />
                        {(hero.title || hero.caption) && (
                            <div className="p-5 sm:p-6 text-center">
                                {hero.title && <h2 className="font-heading text-2xl sm:text-3xl font-black" style={{ color: NAVY }}>{hero.title}</h2>}
                                {hero.caption && <p className="text-sm sm:text-base text-slate-600 mt-2 leading-relaxed max-w-3xl mx-auto whitespace-pre-wrap">{hero.caption}</p>}
                            </div>
                        )}
                    </div>
                </section>
            )}

            <section className="max-w-6xl mx-auto px-6 lg:px-10 py-14">
                {loading ? null : items.length === 0 ? (
                    <div className="text-center py-16 text-slate-500" data-testid="omega-empty">
                        <p className="font-heading text-xl mb-2" style={{ color: NAVY }}>The Omega Chapter stands ready.</p>
                        <p className="text-sm">No brothers or sisters have entered Omega yet. May it remain that way for many years.</p>
                    </div>
                ) : (
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="omega-grid">
                        {items.map((it) => (
                            <TributeCard key={it.id || it.user_id} item={it} isAdmin={isAdmin} onChanged={load} />
                        ))}
                    </div>
                )}
            </section>
        </div>
    );
}

// ---------- Card renderer (picks a template) ----------
function TributeCard({ item, isAdmin, onChanged }) {
    const bg = BACKGROUNDS[item.background] || BACKGROUNDS["navy-starfield"];
    const tpl = TEMPLATES[item.template] ? item.template : "biography";
    const member = item.member || {};
    const initials = (member.name || "").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

    return (
        <div
            className="relative rounded-2xl border-2 shadow-warm overflow-hidden flex flex-col"
            style={{ background: bg.css, borderColor: `${bg.text}25`, color: bg.text }}
            data-testid={`omega-card-${item.user_id}`}
        >
            <div className="absolute top-0 right-0 px-3 py-1 text-[10px] uppercase tracking-widest font-bold text-white z-10" style={{ backgroundColor: bg.accent, color: bg.accent === "#FFFFFF" ? bg.text : "#FFFFFF" }}>
                Omega ✦
            </div>

            {tpl === "biography" && <BiographyBody item={item} member={member} initials={initials} bg={bg} />}
            {tpl === "memorial-card" && <MemorialCardBody item={item} member={member} initials={initials} bg={bg} />}
            {tpl === "in-service" && <InServiceBody item={item} member={member} initials={initials} bg={bg} />}

            {isAdmin && (
                <div className="px-5 py-2 border-t flex justify-end gap-2" style={{ borderColor: `${bg.text}15`, background: `${bg.text}05` }}>
                    {item.type === "tribute" ? (
                        <>
                            <TributeBuilder existing={item} onSaved={onChanged} trigger={
                                <button className="text-xs underline hover:no-underline" data-testid={`edit-tribute-${item.user_id}`}>
                                    <Pencil className="h-3 w-3 inline mr-1" />Edit
                                </button>
                            } />
                            <button
                                onClick={async () => {
                                    if (!window.confirm("Remove this tribute? The member will still appear in Omega if they're marked deceased.")) return;
                                    try {
                                        await api.delete(`/omega/tributes/${item.id}`);
                                        toast.success("Tribute removed");
                                        onChanged();
                                    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
                                }}
                                className="text-xs text-red-600 underline hover:no-underline"
                                data-testid={`delete-tribute-${item.user_id}`}
                            >
                                <Trash2 className="h-3 w-3 inline mr-1" />Delete
                            </button>
                        </>
                    ) : (
                        <TributeBuilder presetUserId={item.user_id} onSaved={onChanged} trigger={
                            <button className="text-xs underline hover:no-underline" data-testid={`add-tribute-for-${item.user_id}`}>
                                <Plus className="h-3 w-3 inline mr-1" />Add tribute
                            </button>
                        } />
                    )}
                </div>
            )}
        </div>
    );
}

function CoverOrAvatar({ src, alt, initials, bg, size = "h-20 w-20" }) {
    if (src) return <img src={src} alt={alt} className={`${size} rounded-full object-cover border-4 border-white shadow-warm`} />;
    return (
        <Avatar className={`${size} border-4 border-white shadow-warm`}>
            <AvatarFallback className="text-white font-black text-2xl" style={{ backgroundColor: bg.accent }}>{initials}</AvatarFallback>
        </Avatar>
    );
}

function InServiceBody({ item, member, initials, bg }) {
    const dates = item.service_dates || [tryFormat(item.born_at), tryFormat(item.passed_at || member.deceased_at)].filter(Boolean).join(" — ");
    return (
        <div className="flex-1 flex flex-col">
            <div className="px-6 pt-6 pb-3 border-b text-center" style={{ borderColor: `${bg.text}20` }}>
                <div className="text-[10px] uppercase tracking-[0.3em] font-bold mb-1 opacity-70">In Service · In Memoriam</div>
                {item.rank && <div className="text-sm font-bold uppercase tracking-widest" style={{ color: bg.accent }}>{item.rank}</div>}
            </div>
            <div className="px-6 py-5 flex gap-4 items-start">
                <CoverOrAvatar src={item.cover_image || member.avatar_url} alt={member.name} initials={initials} bg={bg} size="h-24 w-24" />
                <div className="flex-1">
                    <h3 className="font-heading font-black text-xl leading-tight" style={{ color: bg.text }}>{member.name}</h3>
                    {member.line_name && <div className="text-[10px] font-bold uppercase tracking-widest mt-1" style={{ color: bg.accent }}>"{member.line_name}"</div>}
                    <dl className="text-xs mt-3 space-y-1 opacity-90">
                        {member.branch_of_service && <div className="flex gap-2"><dt className="font-bold uppercase tracking-wider opacity-70 min-w-[64px]">Branch</dt><dd>{member.branch_of_service}</dd></div>}
                        {dates && <div className="flex gap-2"><dt className="font-bold uppercase tracking-wider opacity-70 min-w-[64px]">Service</dt><dd>{dates}</dd></div>}
                        {(member.city || member.state) && <div className="flex gap-2"><dt className="font-bold uppercase tracking-wider opacity-70 min-w-[64px]">Home</dt><dd>{[member.city, member.state].filter(Boolean).join(", ")}</dd></div>}
                        {item.location && <div className="flex gap-2"><dt className="font-bold uppercase tracking-wider opacity-70 min-w-[64px]">Interred</dt><dd>{item.location}</dd></div>}
                    </dl>
                </div>
            </div>
            <div className="px-6 pb-5 flex-1">
                {item.epitaph && <blockquote className="border-l-4 pl-3 italic text-sm mb-3 opacity-90" style={{ borderColor: bg.accent }}>"{item.epitaph}"</blockquote>}
                {item.synopsis ? (
                    <p className="text-sm leading-relaxed opacity-90 whitespace-pre-wrap">{item.synopsis}</p>
                ) : item.biography ? (
                    <p className="text-sm leading-relaxed opacity-90 whitespace-pre-wrap">{item.biography}</p>
                ) : (
                    <p className="text-sm italic opacity-60">Service summary pending.</p>
                )}
            </div>
        </div>
    );
}

function BiographyBody({ item, member, initials, bg }) {
    return (
        <div className="flex-1 flex flex-col">
            <div className="px-6 pt-6 flex items-start gap-4">
                <CoverOrAvatar src={item.cover_image || member.avatar_url} alt={member.name} initials={initials} bg={bg} size="h-24 w-24" />
                <div className="flex-1">
                    <h3 className="font-heading font-bold text-2xl leading-tight" style={{ color: bg.text }}>{member.name}</h3>
                    {member.line_name && <div className="text-[10px] font-bold uppercase tracking-widest mt-1" style={{ color: bg.accent }}>"{member.line_name}"</div>}
                    <div className="text-xs mt-2 opacity-75">
                        {[member.branch_of_service, [member.city, member.state].filter(Boolean).join(", ")].filter(Boolean).join(" · ")}
                    </div>
                    <div className="text-[11px] mt-1 opacity-70">{tryFormat(item.born_at)} {item.born_at && (item.passed_at || member.deceased_at) && "—"} {tryFormat(item.passed_at || member.deceased_at)}</div>
                </div>
            </div>
            <div className="px-6 py-5 flex-1">
                {item.epitaph && <blockquote className="border-l-4 pl-3 italic text-sm mb-4 opacity-90" style={{ borderColor: bg.accent }}>"{item.epitaph}"</blockquote>}
                {item.biography ? (
                    <div className="text-sm leading-relaxed opacity-90 whitespace-pre-wrap">{item.biography}</div>
                ) : item.synopsis ? (
                    <p className="text-sm leading-relaxed opacity-90">{item.synopsis}</p>
                ) : (
                    <p className="text-sm italic opacity-60">A biography for {member.name} has not yet been written.</p>
                )}
            </div>
        </div>
    );
}

function MemorialCardBody({ item, member, initials, bg }) {
    return (
        <div className="p-7 flex-1 flex flex-col text-center">
            <div className="text-[10px] uppercase tracking-[0.3em] font-bold mb-3 opacity-70">In loving memory of</div>
            <h3 className="font-heading font-black text-2xl leading-tight" style={{ color: bg.text }}>{member.name}</h3>
            {member.line_name && <div className="text-xs font-bold uppercase tracking-widest mt-1" style={{ color: bg.accent }}>"{member.line_name}"</div>}
            <div className="text-xs mt-3 opacity-70">{tryFormat(item.born_at)} {item.born_at && (item.passed_at || member.deceased_at) && "—"} {tryFormat(item.passed_at || member.deceased_at)}</div>
            <div className="my-5 flex justify-center">
                <div className="h-px w-20" style={{ background: bg.accent }} />
            </div>
            <div className="mx-auto mb-3">
                <CoverOrAvatar src={item.cover_image || member.avatar_url} alt={member.name} initials={initials} bg={bg} size="h-24 w-24" />
            </div>
            {item.epitaph && <blockquote className="italic text-sm opacity-90 px-2 mt-3">"{item.epitaph}"</blockquote>}
            {!item.epitaph && item.synopsis && <p className="text-sm opacity-90 px-2 mt-3 leading-relaxed">{item.synopsis}</p>}
            {item.location && <div className="text-[11px] mt-4 opacity-60">Laid to rest in {item.location}</div>}
        </div>
    );
}

function tryFormat(d) {
    if (!d) return "";
    try { return format(parseISO(d.length === 10 ? `${d}T00:00:00` : d), "MMM d, yyyy"); }
    catch { return d; }
}

// ---------- Builder dialog (Admin: select member + template + background + synopsis/bio + cover image) ----------
function TributeBuilder({ trigger, existing, presetUserId, onSaved }) {
    const isEdit = !!existing;
    const [open, setOpen] = useState(false);
    const [members, setMembers] = useState([]);
    const [search, setSearch] = useState("");
    const [busy, setBusy] = useState(false);
    const [form, setForm] = useState({
        user_id: existing?.user_id || presetUserId || "",
        template: existing?.template || "biography",
        background: existing?.background || "navy-starfield",
        cover_image: existing?.cover_image || "",
        synopsis: existing?.synopsis || "",
        biography: existing?.biography || "",
        epitaph: existing?.epitaph || "",
        born_at: existing?.born_at || "",
        passed_at: existing?.passed_at || "",
        location: existing?.location || "",
        rank: existing?.rank || "",
        service_dates: existing?.service_dates || "",
    });

    useEffect(() => {
        if (open && !isEdit) {
            api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
        }
    }, [open, isEdit]);

    function set(field, val) { setForm((f) => ({ ...f, [field]: val })); }

    const filteredMembers = (members || []).filter((m) => {
        if (!search) return true;
        const q = search.toLowerCase();
        return m.name?.toLowerCase().includes(q) || m.email?.toLowerCase().includes(q) || (m.line_name || "").toLowerCase().includes(q);
    }).slice(0, 50);

    async function uploadCover(file) {
        if (!file) return;
        if (file.size > 15 * 1024 * 1024) { toast.error("Image must be under 15 MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const { data } = await api.post("/omega/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            set("cover_image", data.url);
            toast.success("Photo uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }

    async function save() {
        if (!form.user_id) { toast.error("Pick a member first"); return; }
        setBusy(true);
        try {
            if (isEdit) {
                const { user_id: _u, ...payload } = form;
                await api.put(`/omega/tributes/${existing.id}`, payload);
                toast.success("Tribute updated");
            } else {
                await api.post("/omega/tributes", form);
                toast.success("Tribute published");
            }
            setOpen(false);
            onSaved?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Save failed");
        }
        setBusy(false);
    }

    const previewMember = isEdit
        ? existing.member
        : members.find((m) => m.id === form.user_id) || (presetUserId ? { id: presetUserId, name: "Selected member" } : null);
    const previewItem = {
        ...form,
        type: "tribute",
        member: previewMember || { name: "Pick a member to preview", line_name: "" },
    };
    const previewBg = BACKGROUNDS[form.background] || BACKGROUNDS["navy-starfield"];

    return (
        <>
            <span onClick={() => setOpen(true)}>{trigger}</span>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto" data-testid="tribute-builder">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">{isEdit ? "Edit tribute" : "Add tribute to Omega Chapter"}</DialogTitle>
                    </DialogHeader>
                    <div className="grid lg:grid-cols-[1fr_320px] gap-6 mt-2">
                        <div className="space-y-4">
                            {!isEdit && !presetUserId && (
                                <div>
                                    <Label>Member *</Label>
                                    <Input
                                        placeholder="Search by name or email…"
                                        value={search}
                                        onChange={(e) => setSearch(e.target.value)}
                                        className="rounded-xl mt-1.5"
                                        data-testid="tribute-member-search"
                                    />
                                    <div className="max-h-44 overflow-y-auto mt-2 border border-border rounded-xl bg-muted/20">
                                        {filteredMembers.map((m) => (
                                            <button
                                                key={m.id}
                                                type="button"
                                                onClick={() => set("user_id", m.id)}
                                                className={`w-full text-left px-3 py-2 hover:bg-muted/60 border-b last:border-0 ${form.user_id === m.id ? "bg-primary/10" : ""}`}
                                                data-testid={`tribute-pick-${m.id}`}
                                            >
                                                <div className="text-sm font-medium">{m.name} {m.line_name && <span className="text-primary font-bold text-xs">"{m.line_name}"</span>}</div>
                                                <div className="text-xs text-muted-foreground">{m.email}</div>
                                            </button>
                                        ))}
                                        {filteredMembers.length === 0 && <div className="px-3 py-4 text-sm text-muted-foreground italic">No members match.</div>}
                                    </div>
                                </div>
                            )}

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label>Template</Label>
                                    <Select value={form.template} onValueChange={(v) => set("template", v)}>
                                        <SelectTrigger className="rounded-xl mt-1.5" data-testid="tribute-template"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(TEMPLATES).map(([k, t]) => <SelectItem key={k} value={k}>{t.label}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                    <p className="text-[11px] text-muted-foreground mt-1.5 leading-snug">{TEMPLATES[form.template]?.description}</p>
                                </div>
                                <div>
                                    <Label>Background</Label>
                                    <Select value={form.background} onValueChange={(v) => set("background", v)}>
                                        <SelectTrigger className="rounded-xl mt-1.5" data-testid="tribute-background"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(BACKGROUNDS).map(([k, b]) => <SelectItem key={k} value={k}>{b.label}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            <div>
                                <Label>Tribute photo</Label>
                                <div className="flex items-center gap-2 mt-1.5">
                                    <Input
                                        type="text"
                                        placeholder="Image URL or upload below"
                                        value={form.cover_image}
                                        onChange={(e) => set("cover_image", e.target.value)}
                                        className="rounded-xl flex-1"
                                        data-testid="tribute-cover-url"
                                    />
                                    <label className="cursor-pointer">
                                        <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                            <span data-testid="tribute-cover-upload"><UploadIcon className="h-3.5 w-3.5 mr-1" />Upload</span>
                                        </Button>
                                        <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadCover(e.target.files?.[0])} />
                                    </label>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label>Rank <span className="text-xs text-muted-foreground font-normal">(in-service)</span></Label>
                                    <Input value={form.rank} onChange={(e) => set("rank", e.target.value)} className="rounded-xl mt-1.5" placeholder="e.g. Sgt. First Class" data-testid="tribute-rank" />
                                </div>
                                <div>
                                    <Label>Service dates <span className="text-xs text-muted-foreground font-normal">(in-service)</span></Label>
                                    <Input value={form.service_dates} onChange={(e) => set("service_dates", e.target.value)} className="rounded-xl mt-1.5" placeholder="e.g. 1998 — 2018" data-testid="tribute-service-dates" />
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label>Born</Label>
                                    <Input type="date" value={form.born_at} onChange={(e) => set("born_at", e.target.value)} className="rounded-xl mt-1.5" data-testid="tribute-born" />
                                </div>
                                <div>
                                    <Label>Entered Omega</Label>
                                    <Input type="date" value={form.passed_at} onChange={(e) => set("passed_at", e.target.value)} className="rounded-xl mt-1.5" data-testid="tribute-passed" />
                                </div>
                            </div>

                            <div>
                                <Label>Resting place / location <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                                <Input value={form.location} onChange={(e) => set("location", e.target.value)} className="rounded-xl mt-1.5" placeholder="e.g. Arlington National Cemetery" data-testid="tribute-location" />
                            </div>

                            <div>
                                <Label>Epitaph / Quote <span className="text-xs text-muted-foreground font-normal">(one line — shown on biography & memorial-card)</span></Label>
                                <Input value={form.epitaph} onChange={(e) => set("epitaph", e.target.value)} className="rounded-xl mt-1.5" placeholder="A short quote that defined them" data-testid="tribute-epitaph" />
                            </div>

                            <div>
                                <Label>Synopsis <span className="text-xs text-muted-foreground font-normal">(short paragraph — classic / memorial card)</span></Label>
                                <Textarea value={form.synopsis} onChange={(e) => set("synopsis", e.target.value)} className="rounded-xl mt-1.5" rows={3} placeholder="A few sentences to honor their memory." data-testid="tribute-synopsis" />
                            </div>

                            <div>
                                <Label>Biography <span className="text-xs text-muted-foreground font-normal">(long-form — biography template)</span></Label>
                                <Textarea value={form.biography} onChange={(e) => set("biography", e.target.value)} className="rounded-xl mt-1.5" rows={8} placeholder="Tell their full story — birthplace, service, family, the Trendsetter they were." data-testid="tribute-biography" />
                            </div>
                        </div>

                        {/* Live preview */}
                        <div>
                            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2">Live preview</div>
                            <div
                                className="rounded-2xl border-2 shadow-warm overflow-hidden"
                                style={{ background: previewBg.css, borderColor: `${previewBg.text}25`, color: previewBg.text }}
                                data-testid="tribute-preview"
                            >
                                {previewItem.template === "biography" && <BiographyBody item={previewItem} member={previewItem.member} initials={(previewItem.member.name || "?").charAt(0).toUpperCase()} bg={previewBg} />}
                                {previewItem.template === "memorial-card" && <MemorialCardBody item={previewItem} member={previewItem.member} initials={(previewItem.member.name || "?").charAt(0).toUpperCase()} bg={previewBg} />}
                                {previewItem.template === "in-service" && <InServiceBody item={previewItem} member={previewItem.member} initials={(previewItem.member.name || "?").charAt(0).toUpperCase()} bg={previewBg} />}
                            </div>
                        </div>
                    </div>
                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Cancel</Button>
                        <Button onClick={save} disabled={busy || !form.user_id} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="tribute-save-btn">
                            {busy ? "Saving…" : (isEdit ? "Save changes" : "Publish tribute")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}


// ---------- Hero Editor (admin-only — manages the featured banner image on /omega) ----------
function HeroEditor({ hero, onSaved }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ image_url: "", title: "", caption: "" });
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (open) setForm({ image_url: hero.image_url || "", title: hero.title || "", caption: hero.caption || "" });
    }, [open, hero]);

    async function uploadImage(file) {
        if (!file) return;
        if (file.size > 15 * 1024 * 1024) { toast.error("Image must be under 15 MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const { data } = await api.post("/omega/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setForm((f) => ({ ...f, image_url: data.url }));
            toast.success("Photo uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }

    async function save() {
        setBusy(true);
        try {
            await api.put("/omega/hero", form);
            toast.success("Featured photo saved");
            setOpen(false);
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    async function clearHero() {
        if (!window.confirm("Remove the featured photo from the Omega Chapter page?")) return;
        setBusy(true);
        try {
            await api.put("/omega/hero", { image_url: "", title: "", caption: "" });
            toast.success("Featured photo removed");
            setOpen(false);
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <>
            <Button onClick={() => setOpen(true)} variant="outline" className="rounded-full" data-testid="omega-hero-edit-btn">
                <ImageIcon className="h-4 w-4 mr-1.5" /> {hero.image_url ? "Edit featured photo" : "Add featured photo"}
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-xl" data-testid="omega-hero-dialog">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">Omega Chapter featured photo</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 mt-2">
                        {form.image_url && (
                            <div className="rounded-xl overflow-hidden border border-border">
                                <img src={form.image_url} alt="Preview" className="w-full max-h-80 object-cover" />
                            </div>
                        )}
                        <div>
                            <Label>Image URL or upload</Label>
                            <div className="flex items-center gap-2 mt-1.5">
                                <Input
                                    type="text"
                                    placeholder="https://… or upload below"
                                    value={form.image_url}
                                    onChange={(e) => setForm((f) => ({ ...f, image_url: e.target.value }))}
                                    className="rounded-xl flex-1"
                                    data-testid="omega-hero-url"
                                />
                                <label className="cursor-pointer">
                                    <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                        <span data-testid="omega-hero-upload"><UploadIcon className="h-3.5 w-3.5 mr-1" />Upload</span>
                                    </Button>
                                    <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0])} />
                                </label>
                            </div>
                        </div>
                        <div>
                            <Label>Title <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                            <Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} className="rounded-xl mt-1.5" placeholder="e.g. In remembrance of Brother Neal Brooks" data-testid="omega-hero-title" />
                        </div>
                        <div>
                            <Label>Caption <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                            <Textarea value={form.caption} onChange={(e) => setForm((f) => ({ ...f, caption: e.target.value }))} className="rounded-xl mt-1.5" rows={3} placeholder="A short caption shown beneath the photo." data-testid="omega-hero-caption" />
                        </div>
                    </div>
                    <DialogFooter className="mt-4 flex-wrap gap-2">
                        {hero.image_url && (
                            <Button variant="outline" onClick={clearHero} disabled={busy} className="rounded-full text-destructive" data-testid="omega-hero-clear-btn">
                                <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Remove
                            </Button>
                        )}
                        <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Cancel</Button>
                        <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="omega-hero-save-btn">
                            {busy ? "Saving…" : "Save featured photo"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
