import { useEffect, useMemo, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
    Medal, Star, Heart, GraduationCap, Sparkles, Trophy, Award as AwardIcon,
    DollarSign, UserPlus, Users, Plus, Pencil, Trash2,
} from "lucide-react";
import { format, parseISO } from "date-fns";
import { formatCalendarDay } from "../lib/dateUtil";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { toast } from "sonner";

const CATALOG_ICONS = {
    medal: Medal, star: Star, heart: Heart, "graduation-cap": GraduationCap,
    sparkles: Sparkles, trophy: Trophy, award: AwardIcon,
};

const OTY_ICONS = {
    member_of_year: Trophy,
    chapter_of_year: AwardIcon,
    top_cs_member: Heart,
    top_cs_chapter: Heart,
    top_fundraising_member: DollarSign,
    top_fundraising_chapter: DollarSign,
    top_recruiter: UserPlus,
};

export default function Awards() {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Awards &amp; Honors</h1>
            <p className="text-muted-foreground mt-2">Recognition for the members who show up, lead, and lift others.</p>

            <Tabs defaultValue="catalog" className="mt-8">
                <TabsList className="rounded-full bg-muted p-1">
                    <TabsTrigger value="catalog" className="rounded-full" data-testid="awards-tab-catalog">Awards catalog</TabsTrigger>
                    <TabsTrigger value="oty" className="rounded-full" data-testid="awards-tab-oty">Of The Year</TabsTrigger>
                </TabsList>
                <TabsContent value="catalog" className="mt-6"><CatalogSection /></TabsContent>
                <TabsContent value="oty" className="mt-6"><OfTheYearSection isAdmin={isAdmin} /></TabsContent>
            </Tabs>
        </div>
    );
}

function CatalogSection() {
    const [awards, setAwards] = useState([]);
    const [recent, setRecent] = useState([]);
    const [recipientsAward, setRecipientsAward] = useState(null); // award whose modal is open

    useEffect(() => {
        api.get("/awards").then(({ data }) => setAwards(data)).catch(() => {});
        (async () => {
            const { data: members } = await api.get("/members");
            const all = [];
            await Promise.all(members.slice(0, 20).map(async (m) => {
                try {
                    const { data } = await api.get(`/members/${m.id}/awards`);
                    data.forEach((g) => all.push({ ...g, member: m }));
                } catch { /* skip members whose awards 404 */ }
            }));
            all.sort((a, b) => (b.granted_at || "").localeCompare(a.granted_at || ""));
            setRecent(all.slice(0, 12));
        })().catch(() => {});
    }, []);

    return (
        <div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {awards.map((a) => {
                    const Icon = CATALOG_ICONS[a.icon] || Trophy;
                    return (
                        <div key={a.id} className="bg-card rounded-2xl border border-border p-6 shadow-warm relative overflow-hidden" data-testid={`award-${a.id}`}>
                            <div className="absolute -top-6 -right-6 w-32 h-32 rounded-full opacity-20" style={{ backgroundColor: a.color }} />
                            <div className="w-14 h-14 rounded-2xl grid place-items-center relative z-10" style={{ backgroundColor: `${a.color}33`, color: a.color }}>
                                <Icon className="h-7 w-7" />
                            </div>
                            <h3 className="font-heading font-bold text-xl mt-4 relative z-10">{a.name}</h3>
                            <p className="text-sm text-muted-foreground mt-2 leading-relaxed relative z-10">{a.description}</p>
                            {(() => {
                                const total = a.granted_count || 0;
                                const distinct = a.granted_distinct_count == null ? total : a.granted_distinct_count;
                                const label = total === distinct
                                    ? `Granted to ${distinct} member${distinct !== 1 ? "s" : ""}`
                                    : `Granted ${total} times to ${distinct} member${distinct !== 1 ? "s" : ""}`;
                                if (total === 0) {
                                    return (
                                        <div className="mt-4 text-xs font-semibold text-muted-foreground relative z-10" data-testid={`award-grant-count-${a.id}`}>
                                            Not yet granted
                                        </div>
                                    );
                                }
                                return (
                                    <button
                                        type="button"
                                        onClick={() => setRecipientsAward(a)}
                                        className="mt-4 text-xs font-semibold text-primary hover:underline relative z-10 inline-flex items-center gap-1 group"
                                        data-testid={`award-grant-count-${a.id}`}
                                        aria-label={`See recipients of ${a.name}`}
                                    >
                                        <span>{label}</span>
                                        <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">→</span>
                                    </button>
                                );
                            })()}
                        </div>
                    );
                })}
                {awards.length === 0 && <div className="col-span-full text-muted-foreground">No awards configured yet.</div>}
            </div>

            <RecipientsDialog award={recipientsAward} onClose={() => setRecipientsAward(null)} />

            {recent.length > 0 && (
                <>
                    <h2 className="font-heading text-2xl font-semibold mt-12 mb-4">Recent recipients</h2>
                    <div className="space-y-3">
                        {recent.map((g) => {
                            const Icon = CATALOG_ICONS[g.award_icon] || Trophy;
                            const initials = (g.user_name || "M").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                            const ord = g.ordinal || 0;
                            const totalForMember = g.award_count || 0;
                            const ordinalLabel = ord === 1 ? "1st Award" : ord === 2 ? "2nd Award" : ord === 3 ? "3rd Award" : ord ? `${ord}th Award` : "";
                            const showOrdinalPill = ord && totalForMember > 1;
                            return (
                                <div key={g.id} className="bg-card rounded-2xl border border-border p-5 flex items-center gap-4" data-testid={`grant-${g.id}`}>
                                    <div className="w-12 h-12 rounded-2xl grid place-items-center" style={{ backgroundColor: `${g.award_color}33`, color: g.award_color }}>
                                        <Icon className="h-6 w-6" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium flex items-center gap-2 flex-wrap">
                                            <span>{g.award_name}</span>
                                            {showOrdinalPill && (
                                                <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary" data-testid={`grant-ordinal-${g.id}`}>
                                                    {ordinalLabel}
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {g.granted_at && formatCalendarDay(g.granted_at, "MMM d, yyyy")}
                                            {g.reason && ` · ${g.reason}`}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Avatar className="h-8 w-8">
                                            {g.member?.avatar_url && <AvatarImage src={g.member.avatar_url} />}
                                            <AvatarFallback className="bg-primary/15 text-primary text-xs">{initials}</AvatarFallback>
                                        </Avatar>
                                        <span className="text-sm font-medium hidden sm:inline">{g.user_name}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </>
            )}
        </div>
    );
}

/**
 * Modal that lists every recipient of a given award with the year it was
 * granted. Triggered by clicking the "Granted to X members" counter on each
 * tile in the Awards Catalog. Fetches lazily when opened so we don't preload
 * dozens of grant lists on page mount.
 */
function RecipientsDialog({ award, onClose }) {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!award) return;
        setRows([]); // clear immediately so switching awards doesn't briefly show prior data
        setLoading(true);
        api.get(`/awards/${award.id}/grants`)
            .then(({ data }) => setRows(data || []))
            .catch(() => setRows([]))
            .finally(() => setLoading(false));
    }, [award]);

    if (!award) return null;
    const Icon = CATALOG_ICONS[award.icon] || Trophy;

    // Group by year (newest first) for a tidy timeline-style listing
    const byYear = rows.reduce((acc, r) => {
        const y = r.year || "—";
        (acc[y] = acc[y] || []).push(r);
        return acc;
    }, {});
    const years = Object.keys(byYear).sort((a, b) => String(b).localeCompare(String(a)));

    return (
        <Dialog open={!!award} onOpenChange={(v) => { if (!v) onClose(); }}>
            <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="award-recipients-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl flex items-center gap-3">
                        <span className="w-11 h-11 rounded-2xl grid place-items-center shrink-0" style={{ backgroundColor: `${award.color}33`, color: award.color }}>
                            <Icon className="h-5 w-5" />
                        </span>
                        <span className="min-w-0 truncate">{award.name}</span>
                    </DialogTitle>
                </DialogHeader>
                <div className="mt-2 text-sm text-muted-foreground" data-testid="award-recipients-count">
                    {loading ? "Loading…" : `${rows.length} grant${rows.length === 1 ? "" : "s"}`}
                </div>
                {!loading && rows.length === 0 && (
                    <div className="mt-4 text-sm italic text-muted-foreground">No recipients yet.</div>
                )}
                <div className="mt-4 space-y-5">
                    {years.map((year) => (
                        <div key={year} data-testid={`recipients-year-${year}`}>
                            <div className="flex items-center gap-3 mb-2">
                                <div className="font-heading text-lg font-bold">{year}</div>
                                <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">
                                    {byYear[year].length} grant{byYear[year].length === 1 ? "" : "s"}
                                </div>
                                <div className="flex-1 h-px bg-border" />
                            </div>
                            <ul className="space-y-2">
                                {byYear[year].map((r, i) => {
                                    const initials = (r.member_name || "M").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                                    return (
                                        <li key={`${r.user_id}-${r.granted_at}-${i}`} className="flex items-center gap-3 p-2 rounded-xl hover:bg-muted/40 transition-colors" data-testid={`recipient-row-${r.user_id}-${r.ordinal || 1}`}>
                                            <Avatar className="h-9 w-9 shrink-0">
                                                {r.avatar_url && <AvatarImage src={mediaUrl(r.avatar_url)} alt={r.member_name} />}
                                                <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">{initials}</AvatarFallback>
                                            </Avatar>
                                            <div className="flex-1 min-w-0">
                                                <div className="font-medium truncate">{r.member_name}</div>
                                                {r.reason && <div className="text-[11px] text-muted-foreground truncate">{r.reason}</div>}
                                            </div>
                                            {r.ordinal > 1 && (
                                                <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary shrink-0" title={`${r.ordinal}th award to this member`}>
                                                    {r.ordinal}×
                                                </span>
                                            )}
                                            <div className="text-xs text-muted-foreground tabular-nums shrink-0">
                                                {r.granted_at ? formatCalendarDay(r.granted_at, "MMM d") : ""}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    ))}
                </div>
            </DialogContent>
        </Dialog>
    );
}


function OfTheYearSection({ isAdmin }) {
    const [categories, setCategories] = useState([]);
    const [rows, setRows] = useState([]);
    const [editing, setEditing] = useState(null); // { _new?, category?, row? }
    const [loading, setLoading] = useState(true);

    const load = () => {
        setLoading(true);
        Promise.all([
            api.get("/of-the-year/categories"),
            api.get("/of-the-year"),
        ]).then(([cats, list]) => {
            setCategories(cats.data);
            setRows(list.data);
        }).catch(() => {}).finally(() => setLoading(false));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, []);

    // Group winners by category, then sort each category by year (desc)
    const grouped = useMemo(() => {
        const g = {};
        categories.forEach((c) => { g[c.key] = []; });
        rows.forEach((r) => {
            if (!g[r.category]) g[r.category] = [];
            g[r.category].push(r);
        });
        Object.values(g).forEach((arr) => arr.sort((a, b) => b.year - a.year));
        return g;
    }, [categories, rows]);

    async function remove(id) {
        if (!window.confirm("Remove this winner?")) return;
        try {
            await api.delete(`/of-the-year/${id}`);
            toast.success("Removed");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    if (loading) return <div className="text-sm text-muted-foreground">Loading…</div>;

    return (
        <div className="space-y-8" data-testid="oty-section">
            {categories.map((c) => {
                const list = grouped[c.key] || [];
                const Icon = OTY_ICONS[c.key] || Trophy;
                return (
                    <div key={c.key} data-testid={`oty-cat-${c.key}`}>
                        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-2xl grid place-items-center bg-primary/10 text-primary">
                                    <Icon className="h-5 w-5" />
                                </div>
                                <div>
                                    <h3 className="font-heading text-xl font-bold tracking-tight">{c.label}</h3>
                                    <div className="text-xs text-muted-foreground">Annual — one winner per year</div>
                                </div>
                            </div>
                            {isAdmin && (
                                <Button size="sm" onClick={() => setEditing({ _new: true, category: c })} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`oty-add-${c.key}`}>
                                    <Plus className="h-4 w-4 mr-1.5" /> Add winner
                                </Button>
                            )}
                        </div>
                        {list.length === 0 ? (
                            <div className="bg-muted/30 rounded-2xl border-2 border-dashed border-border p-6 text-sm text-muted-foreground text-center">
                                No winners recorded yet for this category.
                            </div>
                        ) : (
                            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {list.map((r) => (
                                    <WinnerCard key={r.id} winner={r} isAdmin={isAdmin}
                                        onEdit={() => setEditing({ category: c, row: r })}
                                        onDelete={() => remove(r.id)} />
                                ))}
                            </div>
                        )}
                    </div>
                );
            })}
            {editing && (
                <WinnerEditor
                    isAdmin={isAdmin}
                    category={editing.category}
                    row={editing.row}
                    onClose={() => setEditing(null)}
                    onSaved={() => { setEditing(null); load(); }}
                />
            )}
        </div>
    );
}

function WinnerCard({ winner, isAdmin, onEdit, onDelete }) {
    const isMember = !!winner.user_id;
    const name = isMember ? (winner.user_name || "—") : (winner.chapter_name || "—");
    const avatar = isMember ? winner.user_avatar_url : winner.chapter_logo_url;
    const avatarSrc = avatar ? mediaUrl(avatar) : null;
    const initials = (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
    return (
        <div className="bg-card border border-border rounded-2xl p-4 flex items-center gap-3 shadow-sm" data-testid={`oty-winner-${winner.id}`}>
            <div className="w-12 h-12 rounded-full grid place-items-center bg-yellow-100 text-yellow-700 font-heading font-black shrink-0">
                {winner.year}
            </div>
            <Avatar className="h-12 w-12 shrink-0">
                {avatarSrc && <AvatarImage src={avatarSrc} alt={name} />}
                <AvatarFallback className="bg-primary/15 text-primary">{initials}</AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
                <div className="font-bold truncate" title={name}>{name}</div>
                {winner.note && <div className="text-xs text-muted-foreground truncate" title={winner.note}>{winner.note}</div>}
            </div>
            {isAdmin && (
                <div className="flex flex-col gap-1 shrink-0">
                    <button onClick={onEdit} className="p-1.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground" data-testid={`oty-edit-${winner.id}`} title="Edit">
                        <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={onDelete} className="p-1.5 rounded-full hover:bg-destructive/10 text-muted-foreground hover:text-destructive" data-testid={`oty-delete-${winner.id}`} title="Remove">
                        <Trash2 className="h-3.5 w-3.5" />
                    </button>
                </div>
            )}
        </div>
    );
}

function WinnerEditor({ category, row, onClose, onSaved }) {
    const isNew = !row;
    const isMember = category?.target === "member";
    const [form, setForm] = useState({
        year: row?.year || new Date().getFullYear(),
        user_id: row?.user_id || "",
        chapter_id: row?.chapter_id || "",
        note: row?.note || "",
    });
    const [members, setMembers] = useState([]);
    const [chapters, setChapters] = useState([]);
    const [memberQuery, setMemberQuery] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        // Always load chapters too — member categories can OPTIONALLY tag a
        // chapter ("the chapter this member was in during that year") so it
        // surfaces on the Personnel Brief.
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
        if (isMember) api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
    }, [isMember]);

    const filteredMembers = useMemo(() => {
        if (!memberQuery) return members;
        const q = memberQuery.toLowerCase();
        return members.filter((m) => (m.name || "").toLowerCase().includes(q) || (m.email || "").toLowerCase().includes(q));
    }, [members, memberQuery]);

    const selectedMember = members.find((m) => m.id === form.user_id);
    const selectedChapter = chapters.find((c) => c.id === form.chapter_id);

    async function save() {
        if (!form.year) { toast.error("Year is required"); return; }
        if (isMember && !form.user_id) { toast.error("Pick a member"); return; }
        if (!isMember && !form.chapter_id) { toast.error("Pick a chapter"); return; }
        setBusy(true);
        try {
            if (isNew) {
                await api.post("/of-the-year", {
                    category: category.key,
                    year: Number(form.year),
                    user_id: isMember ? form.user_id : null,
                    // Member categories can OPTIONALLY tag a chapter context
                    // for the Personnel Brief; chapter categories require it.
                    chapter_id: form.chapter_id || null,
                    note: form.note,
                });
                toast.success("Winner added");
            } else {
                await api.put(`/of-the-year/${row.id}`, {
                    year: Number(form.year),
                    user_id: isMember ? form.user_id : null,
                    chapter_id: form.chapter_id || null,
                    note: form.note,
                });
                toast.success("Updated");
            }
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md" data-testid="oty-editor">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">
                        {isNew ? "Add" : "Edit"} {category?.label}
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-4 mt-2">
                    <div>
                        <Label>Year *</Label>
                        <Input type="number" min="1900" max="2100" value={form.year}
                            onChange={(e) => setForm({ ...form, year: e.target.value })}
                            className="rounded-xl mt-1.5" data-testid="oty-year-input" />
                    </div>
                    {isMember ? (
                        <div>
                            <Label>Member *</Label>
                            <Input placeholder="Search by name or email…" value={memberQuery}
                                onChange={(e) => setMemberQuery(e.target.value)}
                                className="rounded-xl mt-1.5 mb-2" data-testid="oty-member-search" />
                            <Select value={form.user_id} onValueChange={(v) => setForm({ ...form, user_id: v })}>
                                <SelectTrigger className="rounded-xl" data-testid="oty-member-select">
                                    <SelectValue placeholder="Pick a member" />
                                </SelectTrigger>
                                <SelectContent className="max-h-72">
                                    {filteredMembers.map((m) => (
                                        <SelectItem key={m.id} value={m.id}>{m.name}{m.email ? ` · ${m.email}` : ""}</SelectItem>
                                    ))}
                                    {filteredMembers.length === 0 && <div className="p-2 text-sm text-muted-foreground">No matches</div>}
                                </SelectContent>
                            </Select>
                            {selectedMember && (
                                <div className="mt-3 flex items-center gap-3 p-3 bg-muted/40 rounded-xl" data-testid="oty-member-preview">
                                    <Avatar className="h-12 w-12">
                                        {selectedMember.avatar_url && <AvatarImage src={selectedMember.avatar_url} />}
                                        <AvatarFallback>{(selectedMember.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}</AvatarFallback>
                                    </Avatar>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-bold truncate">{selectedMember.name}</div>
                                        <div className="text-xs text-muted-foreground truncate">{selectedMember.email}</div>
                                    </div>
                                </div>
                            )}
                            <div className="mt-3">
                                <Label className="flex items-center gap-1">
                                    Chapter context <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-1.5 py-0.5 bg-muted text-muted-foreground">optional</span>
                                </Label>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Which chapter this member was assigned to during {form.year}. Shows on the Personnel Brief. Leave blank to auto-resolve from assignment history.
                                </p>
                                <Select value={form.chapter_id} onValueChange={(v) => setForm({ ...form, chapter_id: v === "__none__" ? "" : v })}>
                                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="oty-member-chapter-select">
                                        <SelectValue placeholder="Auto-resolve from assignment history" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__none__">Auto-resolve from assignment history</SelectItem>
                                        {chapters.map((c) => (
                                            <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    ) : (
                        <div>
                            <Label>Chapter *</Label>
                            <Select value={form.chapter_id} onValueChange={(v) => setForm({ ...form, chapter_id: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="oty-chapter-select">
                                    <SelectValue placeholder="Pick a chapter" />
                                </SelectTrigger>
                                <SelectContent>
                                    {chapters.map((c) => (
                                        <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            {selectedChapter && (
                                <div className="mt-3 flex items-center gap-3 p-3 bg-muted/40 rounded-xl" data-testid="oty-chapter-preview">
                                    <div className="w-12 h-12 rounded-2xl grid place-items-center bg-primary/15 text-primary">
                                        <Users className="h-6 w-6" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-bold truncate">{selectedChapter.name}</div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                    <div>
                        <Label>Note (optional)</Label>
                        <Textarea rows={2} value={form.note}
                            onChange={(e) => setForm({ ...form, note: e.target.value })}
                            placeholder="Why this winner stood out…"
                            className="rounded-xl mt-1.5" data-testid="oty-note-input" />
                    </div>
                    <Button onClick={save} disabled={busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="oty-save-btn">
                        {busy ? "Saving…" : (isNew ? "Add winner" : "Save changes")}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
