import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Sparkles, Plus, Trash2, Users, Calendar, Newspaper, FileText, LayoutDashboard, Building2, Layers, Trophy, Clock } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import AdminDashboard from "./AdminDashboard";

export default function Admin() {
    const [tab, setTab] = useState("dashboard");

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10">
            <div className="flex items-end justify-between mb-8">
                <div>
                    <h1 className="font-heading text-4xl font-bold tracking-tight">Admin console</h1>
                    <p className="text-muted-foreground mt-2">Members, chapters, tiers, events, hours, awards, and content.</p>
                </div>
                <div className="inline-flex items-center gap-2 bg-secondary/30 rounded-full px-4 py-1.5 text-xs font-semibold">
                    <Sparkles className="h-4 w-4" /> AI tools available
                </div>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="dashboard" className="rounded-full" data-testid="admin-tab-dashboard"><LayoutDashboard className="h-4 w-4 mr-1.5" />Dashboard</TabsTrigger>
                    <TabsTrigger value="members" className="rounded-full" data-testid="admin-tab-members"><Users className="h-4 w-4 mr-1.5" />Members</TabsTrigger>
                    <TabsTrigger value="chapters" className="rounded-full" data-testid="admin-tab-chapters"><Building2 className="h-4 w-4 mr-1.5" />Chapters</TabsTrigger>
                    <TabsTrigger value="tiers" className="rounded-full" data-testid="admin-tab-tiers"><Layers className="h-4 w-4 mr-1.5" />Tiers</TabsTrigger>
                    <TabsTrigger value="events" className="rounded-full" data-testid="admin-tab-events"><Calendar className="h-4 w-4 mr-1.5" />Events</TabsTrigger>
                    <TabsTrigger value="hours" className="rounded-full" data-testid="admin-tab-hours"><Clock className="h-4 w-4 mr-1.5" />Hours</TabsTrigger>
                    <TabsTrigger value="awards" className="rounded-full" data-testid="admin-tab-awards"><Trophy className="h-4 w-4 mr-1.5" />Awards</TabsTrigger>
                    <TabsTrigger value="news" className="rounded-full" data-testid="admin-tab-news"><Newspaper className="h-4 w-4 mr-1.5" />News</TabsTrigger>
                    <TabsTrigger value="pages" className="rounded-full" data-testid="admin-tab-pages"><FileText className="h-4 w-4 mr-1.5" />Pages</TabsTrigger>
                </TabsList>

                <TabsContent value="dashboard" className="mt-6"><AdminDashboard /></TabsContent>
                <TabsContent value="members" className="mt-6"><MembersAdmin /></TabsContent>
                <TabsContent value="chapters" className="mt-6"><ChaptersAdmin /></TabsContent>
                <TabsContent value="tiers" className="mt-6"><TiersAdmin /></TabsContent>
                <TabsContent value="events" className="mt-6"><EventsAdmin /></TabsContent>
                <TabsContent value="hours" className="mt-6"><HoursAdmin /></TabsContent>
                <TabsContent value="awards" className="mt-6"><AwardsAdmin /></TabsContent>
                <TabsContent value="news" className="mt-6"><NewsAdmin /></TabsContent>
                <TabsContent value="pages" className="mt-6"><PagesAdmin /></TabsContent>
            </Tabs>
        </div>
    );
}

/* -------- Events -------- */
function EventsAdmin() {
    const [events, setEvents] = useState([]);
    const load = () => api.get("/events").then(({ data }) => setEvents(data));
    useEffect(() => { load(); }, []);

    async function del(id) {
        if (!confirm("Delete this event?")) return;
        await api.delete(`/events/${id}`);
        toast.success("Deleted");
        load();
    }

    return (
        <div>
            <div className="flex justify-end mb-4">
                <EventDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-event-btn"><Plus className="h-4 w-4 mr-1" />New event</Button>} />
            </div>
            <div className="space-y-3">
                {events.map((e) => (
                    <div key={e.id} className="bg-card border border-border rounded-2xl p-5 flex items-center justify-between" data-testid={`admin-event-${e.id}`}>
                        <div>
                            <div className="font-heading font-semibold text-lg">{e.title}</div>
                            <div className="text-sm text-muted-foreground mt-1">{format(parseISO(e.start_at), "EEE, MMM d · h:mm a")} · {e.rsvp_count} RSVPs</div>
                        </div>
                        <div className="flex gap-2">
                            <EventDialog event={e} onSaved={load} trigger={<Button variant="outline" className="rounded-full">Edit</Button>} />
                            <Button variant="ghost" size="icon" onClick={() => del(e.id)} data-testid={`delete-event-${e.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function EventDialog({ event, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        title: event?.title || "",
        description: event?.description || "",
        location: event?.location || "",
        start_at: event ? event.start_at.slice(0, 16) : "",
        end_at: event?.end_at ? event.end_at.slice(0, 16) : "",
        capacity: event?.capacity || 0,
        cover_image: event?.cover_image || "",
        category: event?.category || "social",
        price: event?.price || 0,
    });
    const [aiBusy, setAiBusy] = useState(false);

    async function save() {
        const payload = {
            ...form,
            capacity: Number(form.capacity),
            price: Number(form.price),
            start_at: new Date(form.start_at).toISOString(),
            end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
        };
        try {
            if (event) await api.put(`/events/${event.id}`, payload);
            else await api.post("/events", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Save failed");
        }
    }

    async function aiGenerate() {
        if (!form.title) { toast.error("Add a title first"); return; }
        setAiBusy(true);
        try {
            const { data } = await api.post("/ai/event-description", { title: form.title, topic: form.description, audience: "club members", tone: "friendly" });
            setForm({ ...form, description: data.text });
            toast.success("AI draft ready ✨");
        } catch (e) {
            toast.error(e.response?.data?.detail || "AI failed");
        }
        setAiBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{event ? "Edit event" : "New event"}</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" data-testid="event-title-input" /></div>
                    <div className="bg-secondary/20 rounded-2xl p-4 border border-secondary/40">
                        <div className="flex items-center justify-between mb-2">
                            <Label className="inline-flex items-center gap-1.5"><Sparkles className="h-4 w-4 text-primary" /> Description (AI-assisted)</Label>
                            <Button type="button" size="sm" variant="outline" className="rounded-full" onClick={aiGenerate} disabled={aiBusy} data-testid="ai-generate-btn">
                                {aiBusy ? "Writing…" : "Generate with AI"}
                            </Button>
                        </div>
                        <Textarea rows={6} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl" data-testid="event-description-input" />
                    </div>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div><Label>Start</Label><Input type="datetime-local" value={form.start_at} onChange={(e) => setForm({ ...form, start_at: e.target.value })} className="rounded-xl mt-1.5" data-testid="event-start-input" /></div>
                        <div><Label>End (optional)</Label><Input type="datetime-local" value={form.end_at} onChange={(e) => setForm({ ...form, end_at: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Location</Label><Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Category</Label><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Capacity (0 = unlimited)</Label><Input type="number" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Cover image URL</Label><Input value={form.cover_image} onChange={(e) => setForm({ ...form, cover_image: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                </div>
                <DialogFooter>
                    <Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="event-save-btn">Save event</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- News -------- */
function NewsAdmin() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/news").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) {
        if (!confirm("Delete this article?")) return;
        await api.delete(`/news/${id}`);
        load();
    }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <NewsDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-news-btn"><Plus className="h-4 w-4 mr-1" />New article</Button>} />
            </div>
            <div className="space-y-3">
                {items.map((n) => (
                    <div key={n.id} className="bg-card border border-border rounded-2xl p-5 flex items-center justify-between" data-testid={`admin-news-${n.id}`}>
                        <div>
                            <div className="font-heading font-semibold text-lg">{n.title}</div>
                            <div className="text-sm text-muted-foreground mt-1 line-clamp-1">{n.summary}</div>
                        </div>
                        <div className="flex gap-2">
                            <NewsDialog article={n} onSaved={load} trigger={<Button variant="outline" className="rounded-full">Edit</Button>} />
                            <Button variant="ghost" size="icon" onClick={() => del(n.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function NewsDialog({ article, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        title: article?.title || "",
        summary: article?.summary || "",
        body: article?.body || "",
        cover_image: article?.cover_image || "",
        tags: (article?.tags || []).join(", "),
    });
    const [emailBusy, setEmailBusy] = useState(false);

    async function save() {
        const payload = { ...form, tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean) };
        try {
            if (article) await api.put(`/news/${article.id}`, payload);
            else await api.post("/news", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Save failed");
        }
    }

    async function aiEmail() {
        if (!form.title) { toast.error("Add a title first"); return; }
        setEmailBusy(true);
        try {
            const { data } = await api.post("/ai/draft-email", { subject: form.title, goal: form.summary || form.title, tone: "warm" });
            setForm({ ...form, body: data.text });
            toast.success("Email drafted ✨");
        } catch (e) {
            toast.error(e.response?.data?.detail || "AI failed");
        }
        setEmailBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{article ? "Edit article" : "New article"}</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" data-testid="news-title-input" /></div>
                    <div><Label>Summary</Label><Input value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div className="bg-secondary/20 rounded-2xl p-4 border border-secondary/40">
                        <div className="flex items-center justify-between mb-2">
                            <Label className="inline-flex items-center gap-1.5"><Sparkles className="h-4 w-4 text-primary" /> Body (AI email-draft available)</Label>
                            <Button type="button" size="sm" variant="outline" className="rounded-full" onClick={aiEmail} disabled={emailBusy} data-testid="ai-email-btn">
                                {emailBusy ? "Drafting…" : "Draft as email"}
                            </Button>
                        </div>
                        <Textarea rows={10} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} className="rounded-xl" data-testid="news-body-input" />
                    </div>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div><Label>Cover image URL</Label><Input value={form.cover_image} onChange={(e) => setForm({ ...form, cover_image: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Tags (comma separated)</Label><Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="news-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Pages -------- */
function PagesAdmin() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/pages").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(slug) {
        if (!confirm("Delete this page?")) return;
        await api.delete(`/pages/${slug}`);
        load();
    }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <PageDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-page-btn"><Plus className="h-4 w-4 mr-1" />New page</Button>} />
            </div>
            <div className="space-y-3">
                {items.map((p) => (
                    <div key={p.id} className="bg-card border border-border rounded-2xl p-5 flex items-center justify-between" data-testid={`admin-page-${p.slug}`}>
                        <div>
                            <div className="font-heading font-semibold text-lg">{p.title}</div>
                            <div className="text-sm text-muted-foreground mt-1">/page/{p.slug}</div>
                        </div>
                        <div className="flex gap-2">
                            <PageDialog page={p} onSaved={load} trigger={<Button variant="outline" className="rounded-full">Edit</Button>} />
                            <Button variant="ghost" size="icon" onClick={() => del(p.slug)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function PageDialog({ page, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ slug: page?.slug || "", title: page?.title || "", body: page?.body || "" });
    async function save() {
        try {
            if (page) await api.put(`/pages/${page.slug}`, { title: form.title, body: form.body });
            else await api.post("/pages", form);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Save failed");
        }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{page ? "Edit page" : "New page"}</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div><Label>Slug</Label><Input disabled={!!page} value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/\s+/g, "-") })} className="rounded-xl mt-1.5" data-testid="page-slug-input" /></div>
                    <div><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div><Label>Body</Label><Textarea rows={10} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} className="rounded-xl mt-1.5" /></div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="page-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Members admin: with role toggle, chapter/tier assignment -------- */
function MembersAdmin() {
    const [members, setMembers] = useState([]);
    const [chapters, setChapters] = useState([]);
    const [tiers, setTiers] = useState([]);
    const [q, setQ] = useState("");

    const load = async () => {
        const [m, c, t] = await Promise.all([
            api.get("/members", { params: q ? { q } : {} }),
            api.get("/chapters"),
            api.get("/tiers"),
        ]);
        setMembers(m.data);
        setChapters(c.data);
        setTiers(t.data);
    };

    useEffect(() => { const id = setTimeout(load, 200); return () => clearTimeout(id); }, [q]);

    async function toggleRole(m) {
        const newRole = m.role === "admin" ? "member" : "admin";
        if (!confirm(`Change ${m.name} to ${newRole}?`)) return;
        await api.put(`/members/${m.id}/role`, { role: newRole });
        toast.success(`Role updated to ${newRole}`);
        load();
    }
    async function setChapter(m, chapter_id) {
        await api.put(`/members/${m.id}/chapter`, { chapter_id: chapter_id || null });
        toast.success("Chapter assigned");
        load();
    }
    async function setTier(m, tier_id) {
        await api.put(`/members/${m.id}/tier`, { tier_id: tier_id || null });
        toast.success("Tier updated");
        load();
    }
    async function extendMembership(m, days) {
        await api.put(`/members/${m.id}/tier`, { tier_id: m.tier_id, extend_days: days });
        toast.success(`Extended by ${days} days`);
        load();
    }
    async function deleteMember(m) {
        if (!confirm(`Delete ${m.name}? This removes all of their data (RSVPs, hours, awards, transactions).`)) return;
        try {
            await api.delete(`/members/${m.id}`);
            toast.success("Member removed");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    const chapterName = (id) => chapters.find((c) => c.id === id)?.name || "—";
    const tierName = (id) => tiers.find((t) => t.id === id)?.name || "—";

    return (
        <div>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <Input placeholder="Search members…" value={q} onChange={(e) => setQ(e.target.value)} className="rounded-full max-w-sm" data-testid="admin-member-search" />
                <NewMemberDialog chapters={chapters} tiers={tiers} onSaved={load} />
            </div>
            <div className="bg-card rounded-2xl border border-border overflow-x-auto shadow-warm">
                <table className="w-full text-sm min-w-[1000px]">
                    <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                        <tr>
                            <th className="text-left px-4 py-3">Name</th>
                            <th className="text-left px-4 py-3">Role</th>
                            <th className="text-left px-4 py-3">Chapter</th>
                            <th className="text-left px-4 py-3">Tier</th>
                            <th className="text-left px-4 py-3">Status</th>
                            <th className="text-left px-4 py-3">Expires</th>
                            <th className="text-right px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {members.map((m) => (
                            <tr key={m.id} className="border-t border-border hover:bg-muted/30" data-testid={`admin-member-${m.id}`}>
                                <td className="px-4 py-3">
                                    <div className="font-medium">{m.name}{m.line_name && <span className="text-xs ml-2 text-primary font-bold">"{m.line_name}"</span>}</div>
                                    <div className="text-xs text-muted-foreground">{m.email}</div>
                                </td>
                                <td className="px-4 py-3">
                                    <span className={`text-[10px] uppercase tracking-wider font-semibold rounded-full px-2 py-0.5 ${m.role === "admin" ? "bg-primary/15 text-primary" : "bg-muted"}`}>
                                        {m.role}
                                    </span>
                                </td>
                                <td className="px-4 py-3">
                                    <Select value={m.chapter_id || ""} onValueChange={(v) => setChapter(m, v)}>
                                        <SelectTrigger className="h-8 rounded-full text-xs w-40" data-testid={`member-${m.id}-chapter`}>
                                            <SelectValue placeholder={chapterName(m.chapter_id)} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </td>
                                <td className="px-4 py-3">
                                    <Select value={m.tier_id || ""} onValueChange={(v) => setTier(m, v)}>
                                        <SelectTrigger className="h-8 rounded-full text-xs w-32" data-testid={`member-${m.id}-tier`}>
                                            <SelectValue placeholder={tierName(m.tier_id)} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {tiers.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </td>
                                <td className="px-4 py-3">
                                    <StatusPill status={m.status} />
                                </td>
                                <td className="px-4 py-3 text-muted-foreground text-xs">
                                    {m.membership_expires_at ? format(parseISO(m.membership_expires_at), "MMM d, yyyy") : "—"}
                                    {m.within_grace && <span className="ml-2 text-[10px] bg-destructive/15 text-destructive rounded-full px-2 py-0.5">grace</span>}
                                </td>
                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                    <MemberCardDialog member={m} chapters={chapters} tiers={tiers} />
                                    <Button size="sm" variant="outline" className="rounded-full h-7 text-xs mx-1" onClick={() => extendMembership(m, 365)} data-testid={`extend-${m.id}`}>+1yr</Button>
                                    <EditMemberDialog member={m} chapters={chapters} tiers={tiers} onSaved={load} />
                                    <Button size="sm" variant="outline" className="rounded-full h-7 text-xs ml-1" onClick={() => toggleRole(m)} data-testid={`toggle-role-${m.id}`}>
                                        {m.role === "admin" ? "Demote" : "Promote"}
                                    </Button>
                                    <Button size="sm" variant="ghost" className="rounded-full h-7 ml-1 text-destructive hover:bg-destructive/10" onClick={() => deleteMember(m)} data-testid={`delete-member-${m.id}`}>
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function NewMemberDialog({ chapters, tiers, onSaved }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        email: "", password: "", first_name: "", middle_name: "", last_name: "",
        line_name: "", username: "", phone: "", city: "", address: "", birthdate: "",
        branch_of_service: "", role: "member",
        chapter_id: "", tier_id: "", member_status: "active",
    });
    const [busy, setBusy] = useState(false);
    async function save() {
        if (!form.email || !form.password) { toast.error("Email and password required"); return; }
        setBusy(true);
        try {
            const payload = { ...form };
            if (!payload.chapter_id) delete payload.chapter_id;
            if (!payload.tier_id) delete payload.tier_id;
            if (!payload.member_status) delete payload.member_status;
            await api.post("/admin/members", payload);
            toast.success("Member created");
            setOpen(false);
            setForm({ email: "", password: "", first_name: "", middle_name: "", last_name: "", line_name: "", username: "", phone: "", city: "", address: "", birthdate: "", branch_of_service: "", role: "member", chapter_id: "", tier_id: "", member_status: "active" });
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Create failed"); }
        setBusy(false);
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-member-btn">
                    <Plus className="h-4 w-4 mr-1" /> New member
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Add a new member</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Email *</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded-xl mt-1.5" data-testid="nm-email" /></div>
                        <div><Label>Temporary password *</Label><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="rounded-xl mt-1.5" data-testid="nm-password" /></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>First name</Label><Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="nm-first" /></div>
                        <div><Label>Middle</Label><Input value={form.middle_name} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Last name</Label><Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="nm-last" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Line name</Label><Input value={form.line_name} onChange={(e) => setForm({ ...form, line_name: e.target.value })} className="rounded-xl mt-1.5" placeholder="e.g. Patriot" data-testid="nm-line" /></div>
                        <div><Label>Username</Label><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Birthdate</Label><Input type="date" value={form.birthdate} onChange={(e) => setForm({ ...form, birthdate: e.target.value })} className="rounded-xl mt-1.5" data-testid="nm-birthdate" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Address</Label><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} className="rounded-xl mt-1.5" data-testid="nm-address" /></div>
                        <div><Label>City</Label><Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Branch of service</Label><Input value={form.branch_of_service} onChange={(e) => setForm({ ...form, branch_of_service: e.target.value })} className="rounded-xl mt-1.5" placeholder="Army, Navy, Marines…" /></div>
                        <div>
                            <Label>Member status</Label>
                            <Select value={form.member_status} onValueChange={(v) => setForm({ ...form, member_status: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="nm-status"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="active">Active</SelectItem>
                                    <SelectItem value="inactive">Inactive</SelectItem>
                                    <SelectItem value="grace">Grace period</SelectItem>
                                    <SelectItem value="expired">Expired</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <Label>Chapter</Label>
                            <Select value={form.chapter_id} onValueChange={(v) => setForm({ ...form, chapter_id: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="nm-chapter"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>{chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Tier</Label>
                            <Select value={form.tier_id} onValueChange={(v) => setForm({ ...form, tier_id: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="nm-tier"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>{tiers.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Role</Label>
                            <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="member">Member</SelectItem>
                                    <SelectItem value="admin">Admin</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                </div>
                <DialogFooter><Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="nm-save-btn">{busy ? "Creating…" : "Create member"}</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function EditMemberDialog({ member, chapters, tiers, onSaved }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({});
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (open) {
            setForm({
                email: member.email,
                first_name: member.first_name || "",
                middle_name: member.middle_name || "",
                last_name: member.last_name || "",
                line_name: member.line_name || "",
                username: member.username || "",
                phone: member.phone || "",
                city: member.city || "",
                address: member.address || "",
                birthdate: member.birthdate ? member.birthdate.slice(0, 10) : "",
                branch_of_service: member.branch_of_service || "",
                bio: member.bio || "",
                avatar_url: member.avatar_url || "",
                chapter_id: member.chapter_id || "",
                tier_id: member.tier_id || "",
                role: member.role,
                member_status: member.status_override || member.status || "active",
                new_password: "",
            });
        }
    }, [open, member]);

    async function save() {
        setBusy(true);
        try {
            const payload = Object.fromEntries(Object.entries(form).filter(([_, v]) => v !== "" && v !== null && v !== undefined));
            if (!payload.new_password) delete payload.new_password;
            await api.put(`/members/${member.id}`, payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button size="sm" variant="outline" className="rounded-full h-7 text-xs" data-testid={`edit-member-${member.id}`}>Edit</Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Edit {member.name}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Email</Label><Input value={form.email || ""} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-email" /></div>
                        <div><Label>Username</Label><Input value={form.username || ""} onChange={(e) => setForm({ ...form, username: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>First name</Label><Input value={form.first_name || ""} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-first" /></div>
                        <div><Label>Middle</Label><Input value={form.middle_name || ""} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Last name</Label><Input value={form.last_name || ""} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Line name</Label><Input value={form.line_name || ""} onChange={(e) => setForm({ ...form, line_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-line" /></div>
                        <div><Label>Phone</Label><Input value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Address</Label><Input value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-address" /></div>
                        <div><Label>City</Label><Input value={form.city || ""} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>Birthdate</Label><Input type="date" value={form.birthdate || ""} onChange={(e) => setForm({ ...form, birthdate: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-birthdate" /></div>
                        <div><Label>Branch of service</Label><Input value={form.branch_of_service || ""} onChange={(e) => setForm({ ...form, branch_of_service: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div>
                            <Label>Member status</Label>
                            <Select value={form.member_status || "active"} onValueChange={(v) => setForm({ ...form, member_status: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="em-status"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="active">Active</SelectItem>
                                    <SelectItem value="inactive">Inactive</SelectItem>
                                    <SelectItem value="grace">Grace period</SelectItem>
                                    <SelectItem value="expired">Expired</SelectItem>
                                    <SelectItem value="deceased">Deceased (Omega Chapter)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Avatar URL</Label><Input value={form.avatar_url || ""} onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <Label>Chapter</Label>
                            <Select value={form.chapter_id || ""} onValueChange={(v) => setForm({ ...form, chapter_id: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>{chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Tier</Label>
                            <Select value={form.tier_id || ""} onValueChange={(v) => setForm({ ...form, tier_id: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>{tiers.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Role</Label>
                            <Select value={form.role || "member"} onValueChange={(v) => setForm({ ...form, role: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="member">Member</SelectItem>
                                    <SelectItem value="admin">Admin</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div><Label>Bio</Label><Textarea rows={3} value={form.bio || ""} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div><Label>Reset password (optional)</Label><Input type="password" value={form.new_password || ""} onChange={(e) => setForm({ ...form, new_password: e.target.value })} className="rounded-xl mt-1.5" placeholder="Leave blank to keep current" data-testid="em-new-password" /></div>
                </div>
                <DialogFooter><Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="em-save-btn">{busy ? "Saving…" : "Save changes"}</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Chapters -------- */
function ChaptersAdmin() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/chapters").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) {
        if (!confirm("Delete chapter? Members will be unassigned.")) return;
        await api.delete(`/chapters/${id}`);
        toast.success("Deleted");
        load();
    }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <ChapterDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-chapter-btn"><Plus className="h-4 w-4 mr-1" />New chapter</Button>} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
                {items.map((c) => (
                    <div key={c.id} className="bg-card border border-border rounded-2xl p-5" data-testid={`admin-chapter-${c.id}`}>
                        <div className="flex items-start justify-between">
                            <div>
                                <div className="font-heading font-semibold text-lg">{c.name}</div>
                                <div className="text-sm text-muted-foreground">
                                    {c.region && <>{c.region} region</>}
                                    {c.region && c.state ? " · " : ""}
                                    {c.state}
                                </div>
                                <div className="text-xs text-muted-foreground mt-1">Founded {c.founded_year || "—"} · {c.member_count} members</div>
                            </div>
                            <div className="flex gap-1">
                                <ChapterDialog chapter={c} onSaved={load} trigger={<Button variant="outline" size="sm" className="rounded-full">Edit</Button>} />
                                <Button variant="ghost" size="icon" onClick={() => del(c.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>
                        {c.description && <p className="text-sm mt-3 text-muted-foreground">{c.description}</p>}
                    </div>
                ))}
            </div>
        </div>
    );
}

function ChapterDialog({ chapter, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        name: chapter?.name || "",
        region: chapter?.region || "",
        state: chapter?.state || "",
        founded_year: chapter?.founded_year || "",
        description: chapter?.description || "",
    });
    async function save() {
        try {
            const payload = { ...form, founded_year: form.founded_year ? Number(form.founded_year) : null };
            if (chapter) await api.put(`/chapters/${chapter.id}`, payload);
            else await api.post("/chapters", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-lg">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{chapter ? "Edit chapter" : "New chapter"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="chapter-name-input" /></div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Region</Label><Input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="e.g. East, West, South" className="rounded-xl mt-1.5" data-testid="chapter-region-input" /></div>
                        <div><Label>State</Label><Input value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} placeholder="e.g. TX, CA" className="rounded-xl mt-1.5" data-testid="chapter-state-input" /></div>
                    </div>
                    <div><Label>Founded year</Label><Input type="number" value={form.founded_year} onChange={(e) => setForm({ ...form, founded_year: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div><Label>Description</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" /></div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="chapter-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Tiers -------- */
function TiersAdmin() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/tiers").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) { if (!confirm("Delete this tier?")) return; await api.delete(`/tiers/${id}`); load(); }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <TierDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-tier-btn"><Plus className="h-4 w-4 mr-1" />New tier</Button>} />
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {items.map((t) => (
                    <div key={t.id} className="bg-card border border-border rounded-2xl p-5" data-testid={`admin-tier-${t.id}`}>
                        <div className="flex items-start justify-between">
                            <div className="flex items-center gap-3">
                                <div className="w-3 h-12 rounded-full" style={{ backgroundColor: t.color }} />
                                <div>
                                    <div className="font-heading font-semibold">{t.name}</div>
                                    <div className="text-xs text-muted-foreground">${t.annual_dues}/year · {t.member_count} members</div>
                                </div>
                            </div>
                            <div className="flex gap-1">
                                <TierDialog tier={t} onSaved={load} trigger={<Button variant="outline" size="sm" className="rounded-full">Edit</Button>} />
                                <Button variant="ghost" size="icon" onClick={() => del(t.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>
                        {t.description && <p className="text-sm mt-3 text-muted-foreground leading-relaxed">{t.description}</p>}
                    </div>
                ))}
            </div>
        </div>
    );
}

function TierDialog({ tier, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        name: tier?.name || "",
        order: tier?.order || 0,
        color: tier?.color || "#E86A58",
        annual_dues: tier?.annual_dues ?? 60,
        description: tier?.description || "",
    });
    async function save() {
        try {
            const payload = { ...form, order: Number(form.order), annual_dues: Number(form.annual_dues) };
            if (tier) await api.put(`/tiers/${tier.id}`, payload);
            else await api.post("/tiers", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{tier ? "Edit tier" : "New tier"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="tier-name-input" /></div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>Order</Label><Input type="number" value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Dues ($)</Label><Input type="number" value={form.annual_dues} onChange={(e) => setForm({ ...form, annual_dues: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Color</Label><Input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} className="rounded-xl mt-1.5 h-10" /></div>
                    </div>
                    <div><Label>Description</Label><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" /></div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="tier-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Hours queue (admin review) -------- */
function HoursAdmin() {
    const [items, setItems] = useState([]);
    const [filter, setFilter] = useState("pending");
    const load = () => api.get(`/hours${filter !== "all" ? `?status_filter=${filter}` : ""}`).then(({ data }) => setItems(data));
    useEffect(() => { load(); }, [filter]);
    async function review(id, status) { await api.put(`/hours/${id}/review`, { status, note: "" }); toast.success(status); load(); }
    return (
        <div>
            <div className="flex gap-2 mb-4">
                {["pending", "approved", "rejected", "all"].map((s) => (
                    <button key={s} onClick={() => setFilter(s)} className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize ${filter === s ? "bg-primary text-primary-foreground shadow-warm" : "bg-muted hover:bg-muted/70"}`} data-testid={`admin-hours-filter-${s}`}>{s}</button>
                ))}
            </div>
            {items.length === 0 ? <div className="text-muted-foreground">Empty.</div> : (
                <div className="space-y-3">
                    {items.map((h) => (
                        <div key={h.id} className="bg-card border border-border rounded-2xl p-5 flex items-start gap-4" data-testid={`admin-hours-${h.id}`}>
                            <div className="w-12 h-12 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold">{h.hours}</div>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium">{h.user_name}</div>
                                <div className="text-sm leading-relaxed text-muted-foreground">{h.description}</div>
                                <div className="text-xs text-muted-foreground mt-1">{h.date && format(parseISO(h.date), "MMM d, yyyy")} · status: {h.status}</div>
                            </div>
                            {h.status === "pending" && (
                                <div className="flex gap-2">
                                    <Button size="sm" onClick={() => review(h.id, "approved")} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`admin-approve-${h.id}`}>Approve</Button>
                                    <Button size="sm" variant="outline" onClick={() => review(h.id, "rejected")} className="rounded-full">Reject</Button>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

/* -------- Awards admin -------- */
function AwardsAdmin() {
    const [awards, setAwards] = useState([]);
    const [members, setMembers] = useState([]);

    const load = async () => {
        const [a, m] = await Promise.all([api.get("/awards"), api.get("/members")]);
        setAwards(a.data);
        setMembers(m.data);
    };
    useEffect(() => { load(); }, []);

    async function del(id) { if (!confirm("Delete this award?")) return; await api.delete(`/awards/${id}`); load(); }

    return (
        <div>
            <div className="flex justify-end mb-4">
                <AwardDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-award-btn"><Plus className="h-4 w-4 mr-1" />New award</Button>} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
                {awards.map((a) => (
                    <div key={a.id} className="bg-card border border-border rounded-2xl p-5" data-testid={`admin-award-${a.id}`}>
                        <div className="flex items-start justify-between">
                            <div>
                                <div className="font-heading font-semibold text-lg flex items-center gap-2">
                                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: a.color }} /> {a.name}
                                </div>
                                <div className="text-sm text-muted-foreground mt-1">{a.description}</div>
                                <div className="text-xs text-muted-foreground mt-2">Granted {a.granted_count}× · icon: {a.icon}</div>
                            </div>
                            <div className="flex gap-1">
                                <GrantAwardDialog award={a} members={members} onSaved={load} />
                                <AwardDialog award={a} onSaved={load} trigger={<Button variant="outline" size="sm" className="rounded-full">Edit</Button>} />
                                <Button variant="ghost" size="icon" onClick={() => del(a.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function AwardDialog({ award, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        name: award?.name || "",
        description: award?.description || "",
        icon: award?.icon || "trophy",
        color: award?.color || "#F9D466",
    });
    async function save() {
        try {
            if (award) await api.put(`/awards/${award.id}`, form);
            else await api.post("/awards", form);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{award ? "Edit award" : "New award"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="award-name-input" /></div>
                    <div><Label>Description</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Icon</Label>
                            <Select value={form.icon} onValueChange={(v) => setForm({ ...form, icon: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="award-icon-select"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="trophy">Trophy</SelectItem>
                                    <SelectItem value="medal">Medal</SelectItem>
                                    <SelectItem value="star">Star</SelectItem>
                                    <SelectItem value="heart">Heart</SelectItem>
                                    <SelectItem value="graduation-cap">Graduation</SelectItem>
                                    <SelectItem value="sparkles">Sparkles</SelectItem>
                                    <SelectItem value="award">Award</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div><Label>Color</Label><Input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} className="rounded-xl mt-1.5 h-10" /></div>
                    </div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="award-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function GrantAwardDialog({ award, members, onSaved }) {
    const [open, setOpen] = useState(false);
    const [userId, setUserId] = useState("");
    const [reason, setReason] = useState("");
    const [grantedAt, setGrantedAt] = useState("");
    async function grant() {
        if (!userId) { toast.error("Pick a member"); return; }
        try {
            const payload = { user_id: userId, reason };
            if (grantedAt) payload.granted_at = new Date(grantedAt).toISOString();
            await api.post(`/awards/${award.id}/grant`, payload);
            toast.success(`${award.name} granted`);
            setOpen(false);
            setUserId(""); setReason(""); setGrantedAt("");
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button size="sm" className="rounded-full bg-primary/10 text-primary hover:bg-primary/20" data-testid={`grant-btn-${award.id}`}>Grant</Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Grant "{award.name}"</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div>
                        <Label>Member</Label>
                        <Select value={userId} onValueChange={setUserId}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="grant-member-select"><SelectValue placeholder="Choose a member…" /></SelectTrigger>
                            <SelectContent className="max-h-72">
                                {members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} — {m.email}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Date granted <span className="text-xs text-muted-foreground font-normal">(defaults to today)</span></Label>
                        <Input type="date" value={grantedAt} onChange={(e) => setGrantedAt(e.target.value)} className="rounded-xl mt-1.5" data-testid="grant-date-input" />
                    </div>
                    <div><Label>Reason (optional)</Label><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-xl mt-1.5" /></div>
                </div>
                <DialogFooter><Button onClick={grant} className="rounded-full bg-primary hover:bg-primary/90" data-testid="grant-confirm-btn">Grant award</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Member Card (clickable view) -------- */
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

function MemberCardDialog({ member, chapters, tiers, trigger }) {
    const [open, setOpen] = useState(false);
    const [details, setDetails] = useState(member);
    useEffect(() => {
        if (open) {
            api.get(`/members/${member.id}`).then(({ data }) => setDetails(data)).catch(() => {});
        }
    }, [open, member.id]);
    const chapter = chapters?.find((c) => c.id === details.chapter_id);
    const tier = tiers?.find((t) => t.id === details.tier_id);
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                {trigger || <Button size="sm" variant="outline" className="rounded-full h-7 text-xs" data-testid={`view-member-${member.id}`}>View</Button>}
            </DialogTrigger>
            <DialogContent className="max-w-lg">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Member card</DialogTitle></DialogHeader>
                <div className="flex items-center gap-4 mt-1">
                    <div className="w-16 h-16 rounded-full bg-primary/15 text-primary grid place-items-center font-heading font-black text-2xl">
                        {(details.name || details.email)[0]?.toUpperCase()}
                    </div>
                    <div className="flex-1">
                        <div className="font-heading text-xl font-bold">{details.name}</div>
                        {details.line_name && <div className="text-xs font-bold uppercase tracking-widest text-primary">"{details.line_name}"</div>}
                        <div className="mt-1 flex flex-wrap gap-2 items-center">
                            <StatusPill status={details.status} />
                            {details.role === "admin" && <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/15 text-primary">Admin</span>}
                            {tier && <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-accent/40">{tier.name}</span>}
                        </div>
                    </div>
                </div>
                <div className="mt-4 space-y-2 text-sm" data-testid={`member-card-${member.id}-details`}>
                    <DetailRow label="Email" value={details.email} />
                    {details.username && <DetailRow label="Username" value={`@${details.username}`} />}
                    <DetailRow label="Phone" value={details.phone} />
                    <DetailRow label="Address" value={[details.address, details.city].filter(Boolean).join(", ")} />
                    <DetailRow label="Birthdate" value={details.birthdate ? format(parseISO(details.birthdate.length === 10 ? `${details.birthdate}T00:00:00` : details.birthdate), "MMM d, yyyy") : ""} />
                    <DetailRow label="Branch of service" value={details.branch_of_service} />
                    <DetailRow label="Chapter" value={chapter?.name} />
                    <DetailRow label="Joined" value={details.created_at ? format(parseISO(details.created_at), "MMM d, yyyy") : ""} />
                    <DetailRow label="Membership expires" value={details.membership_expires_at ? format(parseISO(details.membership_expires_at), "MMM d, yyyy") : ""} />
                    {details.bio && (
                        <div className="pt-2 border-t">
                            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-1">Bio</div>
                            <p className="text-sm leading-relaxed">{details.bio}</p>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}

function DetailRow({ label, value }) {
    if (!value) return null;
    return (
        <div className="flex items-start gap-3">
            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground w-32 shrink-0 pt-0.5">{label}</div>
            <div className="text-sm flex-1 break-words">{value}</div>
        </div>
    );
}

export { MemberCardDialog, StatusPill };
