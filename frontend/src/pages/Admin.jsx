import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "../components/ui/dialog";
import { Sparkles, Plus, Trash2, Users, Calendar, Newspaper, FileText } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

export default function Admin() {
    const [tab, setTab] = useState("events");

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10">
            <div className="flex items-end justify-between mb-8">
                <div>
                    <h1 className="font-heading text-4xl font-bold tracking-tight">Admin console</h1>
                    <p className="text-muted-foreground mt-2">Manage members, events, news, and pages.</p>
                </div>
                <div className="inline-flex items-center gap-2 bg-secondary/30 rounded-full px-4 py-1.5 text-xs font-semibold">
                    <Sparkles className="h-4 w-4" /> AI tools available
                </div>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap">
                    <TabsTrigger value="events" className="rounded-full" data-testid="admin-tab-events"><Calendar className="h-4 w-4 mr-1.5" />Events</TabsTrigger>
                    <TabsTrigger value="news" className="rounded-full" data-testid="admin-tab-news"><Newspaper className="h-4 w-4 mr-1.5" />News</TabsTrigger>
                    <TabsTrigger value="pages" className="rounded-full" data-testid="admin-tab-pages"><FileText className="h-4 w-4 mr-1.5" />Pages</TabsTrigger>
                    <TabsTrigger value="members" className="rounded-full" data-testid="admin-tab-members"><Users className="h-4 w-4 mr-1.5" />Members</TabsTrigger>
                </TabsList>

                <TabsContent value="events" className="mt-6"><EventsAdmin /></TabsContent>
                <TabsContent value="news" className="mt-6"><NewsAdmin /></TabsContent>
                <TabsContent value="pages" className="mt-6"><PagesAdmin /></TabsContent>
                <TabsContent value="members" className="mt-6"><MembersAdmin /></TabsContent>
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

/* -------- Members (read-only for V1) -------- */
function MembersAdmin() {
    const [members, setMembers] = useState([]);
    useEffect(() => { api.get("/members").then(({ data }) => setMembers(data)); }, []);
    return (
        <div className="bg-card rounded-2xl border border-border overflow-hidden">
            <table className="w-full text-sm">
                <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                        <th className="text-left px-5 py-3">Name</th>
                        <th className="text-left px-5 py-3">Email</th>
                        <th className="text-left px-5 py-3">City</th>
                        <th className="text-left px-5 py-3">Tier</th>
                        <th className="text-left px-5 py-3">Expires</th>
                    </tr>
                </thead>
                <tbody>
                    {members.map((m) => (
                        <tr key={m.id} className="border-t border-border hover:bg-muted/30">
                            <td className="px-5 py-3 font-medium">{m.name}</td>
                            <td className="px-5 py-3 text-muted-foreground">{m.email}</td>
                            <td className="px-5 py-3">{m.city || "—"}</td>
                            <td className="px-5 py-3 capitalize">{m.membership_tier}</td>
                            <td className="px-5 py-3 text-muted-foreground">{m.membership_expires_at ? format(parseISO(m.membership_expires_at), "MMM d, yyyy") : "—"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
