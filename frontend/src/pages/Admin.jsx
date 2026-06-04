import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Sparkles, Plus, Trash2, Users, Calendar, Newspaper, FileText, LayoutDashboard, Building2, Layers, Trophy, Clock, ShoppingBag, Heart, BarChart3, Mail, Send, PenSquare, Upload, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import AdminDashboard from "./AdminDashboard";
import Reports from "./Reports";
import RichEditor from "../components/RichEditor";
import AutomatedEmailsAdmin from "../components/AutomatedEmailsAdmin";
import SiteSettingsAdmin from "../components/SiteSettingsAdmin";
import PageBuilder from "../components/cms/PageBuilder";
import BulkImportMembersDialog from "../components/BulkImportMembersDialog";
import AssignmentHistoryEditor from "../components/AssignmentHistoryEditor";

export default function Admin() {
    const [tab, setTab] = useState("dashboard");
    const [perms, setPerms] = useState(null);

    useEffect(() => {
        api.get("/admin/permissions").then(({ data }) => setPerms(data)).catch(() => setPerms({ tabs: [], admin_role: "" }));
    }, []);

    // Default to first allowed tab if current tab isn't allowed
    useEffect(() => {
        if (perms && perms.tabs.length && !perms.tabs.includes(tab)) setTab(perms.tabs[0]);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [perms]);

    if (!perms) return <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10 text-muted-foreground">Loading…</div>;
    const allowed = (t) => perms.tabs.includes(t);

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10">
            <div className="flex items-end justify-between mb-8">
                <div>
                    <h1 className="font-heading text-4xl font-bold tracking-tight">Admin console</h1>
                    <p className="text-muted-foreground mt-2">
                        {perms.admin_role && perms.admin_role !== "full" ? (
                            <>You're logged in as <strong className="capitalize">{perms.admin_role.replace(/_/g, " ")}</strong>{perms.chapter_scoped ? " · chapter-scoped" : ""}.</>
                        ) : "Members, chapters, tiers, events, hours, awards, and content."}
                    </p>
                </div>
                <div className="inline-flex items-center gap-2 bg-secondary/30 rounded-full px-4 py-1.5 text-xs font-semibold">
                    <Sparkles className="h-4 w-4" /> AI tools available
                </div>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <div className="-mx-2 px-2 sm:mx-0 sm:px-0 overflow-x-auto sm:overflow-x-visible scrollbar-hide max-w-full">
                    <TabsList className="rounded-full bg-muted p-1 inline-flex sm:flex sm:flex-wrap sm:h-auto whitespace-nowrap w-max sm:w-full">
                        {allowed("dashboard") && <TabsTrigger value="dashboard" className="rounded-full" data-testid="admin-tab-dashboard"><LayoutDashboard className="h-4 w-4 mr-1.5" />Dashboard</TabsTrigger>}
                        {allowed("members") && <TabsTrigger value="members" className="rounded-full" data-testid="admin-tab-members"><Users className="h-4 w-4 mr-1.5" />Members</TabsTrigger>}
                        {allowed("chapters") && <TabsTrigger value="chapters" className="rounded-full" data-testid="admin-tab-chapters"><Building2 className="h-4 w-4 mr-1.5" />Chapters</TabsTrigger>}
                        {allowed("tiers") && <TabsTrigger value="tiers" className="rounded-full" data-testid="admin-tab-tiers"><Layers className="h-4 w-4 mr-1.5" />Tiers</TabsTrigger>}
                        {allowed("events") && <TabsTrigger value="events" className="rounded-full" data-testid="admin-tab-events"><Calendar className="h-4 w-4 mr-1.5" />Events</TabsTrigger>}
                        {allowed("hours") && <TabsTrigger value="hours" className="rounded-full" data-testid="admin-tab-hours"><Clock className="h-4 w-4 mr-1.5" />Hours</TabsTrigger>}
                        {allowed("awards") && <TabsTrigger value="awards" className="rounded-full" data-testid="admin-tab-awards"><Trophy className="h-4 w-4 mr-1.5" />Awards</TabsTrigger>}
                        {allowed("gear") && <TabsTrigger value="gear" className="rounded-full" data-testid="admin-tab-gear"><ShoppingBag className="h-4 w-4 mr-1.5" />Gear</TabsTrigger>}
                        {allowed("causes") && <TabsTrigger value="causes" className="rounded-full" data-testid="admin-tab-causes"><Heart className="h-4 w-4 mr-1.5" />Causes</TabsTrigger>}
                        {allowed("reports") && <TabsTrigger value="reports" className="rounded-full" data-testid="admin-tab-reports"><BarChart3 className="h-4 w-4 mr-1.5" />Reports</TabsTrigger>}
                        {allowed("email") && <TabsTrigger value="email" className="rounded-full" data-testid="admin-tab-email"><Mail className="h-4 w-4 mr-1.5" />Email</TabsTrigger>}
                        {allowed("news") && <TabsTrigger value="news" className="rounded-full" data-testid="admin-tab-news"><Newspaper className="h-4 w-4 mr-1.5" />News</TabsTrigger>}
                        {allowed("pages") && <TabsTrigger value="pages" className="rounded-full" data-testid="admin-tab-pages"><FileText className="h-4 w-4 mr-1.5" />Pages</TabsTrigger>}
                    </TabsList>
                </div>

                {allowed("dashboard") && <TabsContent value="dashboard" className="mt-6"><AdminDashboard scopedChapterId={perms.scoped_chapter_id} /></TabsContent>}
                {allowed("members") && <TabsContent value="members" className="mt-6"><MembersAdmin /></TabsContent>}
                {allowed("chapters") && <TabsContent value="chapters" className="mt-6"><ChaptersAdmin /></TabsContent>}
                {allowed("tiers") && <TabsContent value="tiers" className="mt-6"><TiersAdmin /></TabsContent>}
                {allowed("events") && <TabsContent value="events" className="mt-6"><EventsAdmin /></TabsContent>}
                {allowed("hours") && <TabsContent value="hours" className="mt-6"><HoursAdmin scopedChapterId={perms.scoped_chapter_id} /></TabsContent>}
                {allowed("awards") && <TabsContent value="awards" className="mt-6"><AwardsAdmin /></TabsContent>}
                {allowed("gear") && <TabsContent value="gear" className="mt-6"><GearAdmin /></TabsContent>}
                {allowed("causes") && <TabsContent value="causes" className="mt-6"><CausesAdmin scopedChapterId={perms.scoped_chapter_id} /></TabsContent>}
                {allowed("reports") && <TabsContent value="reports" className="mt-6"><Reports scopedChapterId={perms.scoped_chapter_id} /></TabsContent>}
                {allowed("email") && <TabsContent value="email" className="mt-6"><EmailBlastAdmin /></TabsContent>}
                {allowed("news") && <TabsContent value="news" className="mt-6"><NewsAdmin /></TabsContent>}
                {allowed("pages") && <TabsContent value="pages" className="mt-6"><PagesAdmin /></TabsContent>}
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
                            <EventDialog event={e} onSaved={load} trigger={<Button variant="outline" className="rounded-full" data-testid={`edit-event-${e.id}`}>Edit</Button>} />
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
        cancelled: event?.cancelled || false,
        cancellation_note: event?.cancellation_note || "",
        is_paid: event?.is_paid || false,
        payment_url: event?.payment_url || "",
        payment_amount: event?.payment_amount || 0,
        allows_ticket_types: event?.allows_ticket_types || false,
        enabled_ticket_types: event?.enabled_ticket_types || [],
    });
    const [aiBusy, setAiBusy] = useState(false);
    const [coverUploading, setCoverUploading] = useState(false);

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
                        <div className="sm:col-span-2">
                            <Label>Cover photo</Label>
                            <div className="mt-1.5 grid sm:grid-cols-[1fr_180px] gap-3 items-start">
                                <label className="rounded-xl border-2 border-dashed border-slate-300 px-4 py-3 text-sm font-semibold cursor-pointer hover:bg-white hover:border-primary transition-colors flex items-center gap-2 justify-center" data-testid="event-cover-upload">
                                    {coverUploading ? "Uploading…" : (<>📷 {form.cover_image ? "Replace cover photo" : "Upload cover photo"}</>)}
                                    <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
                                        const f = e.target.files?.[0]; if (!f) return;
                                        setCoverUploading(true);
                                        try {
                                            const fd = new FormData(); fd.append("file", f);
                                            const { data } = await api.post("/events/upload-cover", fd, { headers: { "Content-Type": "multipart/form-data" } });
                                            setForm((p) => ({ ...p, cover_image: data.url }));
                                            toast.success("Cover uploaded");
                                        } catch (err) { toast.error(err.response?.data?.detail || "Upload failed"); }
                                        setCoverUploading(false);
                                    }} />
                                </label>
                                {form.cover_image ? (
                                    <div className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50">
                                        <img src={form.cover_image} alt="Cover preview" className="block w-full h-32 object-contain" onError={(e) => { e.currentTarget.style.opacity = "0.3"; }} />
                                    </div>
                                ) : (
                                    <div className="border border-dashed border-slate-300 rounded-xl bg-white h-32 grid place-items-center text-[10px] text-slate-400 uppercase tracking-wider">Preview</div>
                                )}
                            </div>
                        </div>
                    </div>
                    {/* Ticket types selector — admin picks which subset applies for this event */}
                    <div className="rounded-2xl border-2 border-slate-200 bg-slate-50 p-4">
                        <label className="flex items-center gap-3 cursor-pointer mb-2">
                            <input
                                type="checkbox"
                                checked={!!form.allows_ticket_types}
                                onChange={(e) => setForm({ ...form, allows_ticket_types: e.target.checked, enabled_ticket_types: e.target.checked && (form.enabled_ticket_types?.length === 0) ? ["general"] : form.enabled_ticket_types })}
                                className="h-4 w-4 rounded border-2 border-slate-300 accent-primary"
                                data-testid="event-allows-tickets-toggle"
                            />
                            <span className="font-semibold text-sm">Use ticket types for this event</span>
                        </label>
                        {form.allows_ticket_types && (
                            <div className="mt-2">
                                <p className="text-xs text-muted-foreground mb-2">Select which ticket types members can pick from:</p>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                                    {["vip", "all_access", "general", "guest", "speaker", "volunteer"].map((t) => (
                                        <label key={t} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 cursor-pointer hover:border-primary text-sm">
                                            <input
                                                type="checkbox"
                                                checked={(form.enabled_ticket_types || []).includes(t)}
                                                onChange={(e) => {
                                                    const cur = new Set(form.enabled_ticket_types || []);
                                                    if (e.target.checked) cur.add(t); else cur.delete(t);
                                                    setForm({ ...form, enabled_ticket_types: Array.from(cur) });
                                                }}
                                                className="h-3.5 w-3.5 accent-primary"
                                                data-testid={`event-ticket-type-${t}`}
                                            />
                                            <span className="capitalize">{t.replace("_", " ")}</span>
                                        </label>
                                    ))}
                                </div>
                                {(form.enabled_ticket_types || []).length === 0 && (
                                    <p className="text-[11px] text-amber-700 mt-2">Pick at least one type — otherwise members can't RSVP.</p>
                                )}
                            </div>
                        )}
                        {!form.allows_ticket_types && (
                            <p className="text-[11px] text-muted-foreground">Members will RSVP without choosing a ticket type. Best for casual gatherings.</p>
                        )}
                    </div>
                    {/* Paid event toggle */}
                    <div className={`rounded-2xl border-2 p-4 ${form.is_paid ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}>
                        <label className="flex items-center gap-3 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={!!form.is_paid}
                                onChange={(e) => setForm({ ...form, is_paid: e.target.checked })}
                                className="h-4 w-4 rounded border-2 border-slate-300 accent-emerald-600"
                                data-testid="event-paid-toggle"
                            />
                            <span className="font-semibold text-sm">
                                {form.is_paid ? "💲 Paid event — members must pay via Zeffy before RSVP" : "Free event"}
                            </span>
                        </label>
                        {form.is_paid && (
                            <div className="mt-3 grid sm:grid-cols-[1fr_140px] gap-3">
                                <div>
                                    <Label className="text-xs">Zeffy payment URL</Label>
                                    <Input
                                        value={form.payment_url}
                                        onChange={(e) => setForm({ ...form, payment_url: e.target.value })}
                                        placeholder="https://www.zeffy.com/en-US/ticketing/your-event"
                                        className="rounded-xl mt-1.5"
                                        data-testid="event-payment-url"
                                    />
                                </div>
                                <div>
                                    <Label className="text-xs">Amount (USD)</Label>
                                    <Input
                                        type="number"
                                        min="0"
                                        step="0.01"
                                        value={form.payment_amount}
                                        onChange={(e) => setForm({ ...form, payment_amount: Number(e.target.value) })}
                                        className="rounded-xl mt-1.5"
                                        data-testid="event-payment-amount"
                                    />
                                </div>
                                <p className="sm:col-span-2 text-[11px] text-emerald-800 leading-snug">
                                    Members pay through Zeffy and submit their receipt #. RSVP is confirmed once an admin approves the receipt (or auto-approved for trusted members). Same flow as annual dues.
                                </p>
                            </div>
                        )}
                    </div>
                    {event && (
                        <div className={`rounded-2xl border-2 p-4 ${form.cancelled ? "border-red-300 bg-red-50" : "border-slate-200 bg-slate-50"}`}>
                            <label className="flex items-center gap-3 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={form.cancelled}
                                    onChange={(e) => setForm({ ...form, cancelled: e.target.checked })}
                                    className="h-4 w-4 rounded border-2 border-slate-300 accent-red-600"
                                    data-testid="event-cancelled-toggle"
                                />
                                <span className="font-semibold text-sm">
                                    {form.cancelled ? "🚫 Event is cancelled — RSVPs are blocked" : "Mark this event as cancelled"}
                                </span>
                            </label>
                            {form.cancelled && (
                                <div className="mt-3">
                                    <Label className="text-xs">Reason (optional, shown on the event page)</Label>
                                    <Input
                                        value={form.cancellation_note}
                                        onChange={(e) => setForm({ ...form, cancellation_note: e.target.value })}
                                        placeholder="e.g. Severe weather"
                                        className="rounded-xl mt-1.5"
                                        data-testid="event-cancellation-note"
                                    />
                                    <p className="text-[11px] text-red-700 mt-2 leading-snug">
                                        Members will see a CANCELLED banner. The event will still appear on the calendar but the RSVP button will be disabled.
                                    </p>
                                </div>
                            )}
                        </div>
                    )}
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
                        <div>
                            <Label>Cover photo</Label>
                            <label className="mt-1.5 rounded-xl border-2 border-dashed border-slate-300 px-4 py-3 text-sm font-semibold cursor-pointer hover:bg-white hover:border-primary transition-colors flex items-center gap-2 justify-center" data-testid="news-image-upload-btn">
                                <Upload className="h-4 w-4" />{form.cover_image ? "Replace cover photo" : "Upload cover photo"}
                                <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
                                    const f = e.target.files?.[0]; if (!f) return;
                                    const fd = new FormData(); fd.append("file", f);
                                    try {
                                        const { data } = await api.post("/news/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
                                        setForm((p) => ({ ...p, cover_image: data.url }));
                                        toast.success("Cover photo uploaded");
                                    } catch (err) { toast.error(err.response?.data?.detail || "Upload failed"); }
                                }} />
                            </label>
                            {form.cover_image && (
                                <img src={mediaUrl(form.cover_image)} alt="Preview" className="mt-2 w-full max-h-32 object-contain rounded-xl border border-border bg-slate-50" />
                            )}
                        </div>
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
        <div className="space-y-8">
            <SiteSettingsAdmin />
            <div>
                <div className="flex items-end justify-between mb-4">
                    <div>
                        <h3 className="font-heading text-xl font-bold">Custom pages</h3>
                        <p className="text-xs text-muted-foreground">Author standalone pages at <code>/page/&lt;slug&gt;</code>.</p>
                    </div>
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
        </div>
    );
}

function PageDialog({ page, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ slug: page?.slug || "", title: page?.title || "", body: page?.body || "", blocks: page?.blocks || [] });
    const [mode, setMode] = useState((page?.blocks && page.blocks.length > 0) ? "blocks" : "blocks");
    async function save() {
        try {
            const payload = { title: form.title, body: form.body, blocks: form.blocks };
            if (page) {
                await api.put(`/pages/${page.slug}`, payload);
            } else {
                await api.post("/pages", { slug: form.slug, ...payload });
            }
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
            <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">{page ? "Edit page" : "New page"}</DialogTitle>
                    <DialogDescription className="sr-only">Create or edit a custom page. Use the visual editor to add drag-and-drop blocks, or switch to the legacy text mode.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4 mt-2">
                    <div className="grid sm:grid-cols-2 gap-3">
                        <div><Label>Slug</Label><Input disabled={!!page} value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/\s+/g, "-") })} className="rounded-xl mt-1.5" data-testid="page-slug-input" /></div>
                        <div><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" data-testid="page-title-input" /></div>
                    </div>
                    <div className="flex items-center gap-2 border-b pb-2">
                        <Button size="sm" variant={mode === "blocks" ? "default" : "outline"} onClick={() => setMode("blocks")} className="rounded-full" data-testid="page-mode-blocks">Visual editor</Button>
                        <Button size="sm" variant={mode === "body" ? "default" : "outline"} onClick={() => setMode("body")} className="rounded-full" data-testid="page-mode-body">Legacy text</Button>
                    </div>
                    {mode === "blocks" ? (
                        <PageBuilder blocks={form.blocks} onChange={(blocks) => setForm({ ...form, blocks })} testIdPrefix="page-dialog-builder" />
                    ) : (
                        <div><Label>Body</Label><Textarea rows={10} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    )}
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="page-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Members admin: with role toggle, chapter/tier assignment -------- */
function ApplicationsPanel({ onApproved }) {
    const [apps, setApps] = useState([]);
    const [busy, setBusy] = useState({});

    async function load() {
        try {
            const { data } = await api.get("/admin/applications", { params: { status_filter: "pending" } });
            setApps(data);
        } catch { /* ignore */ }
    }
    useEffect(() => { load(); }, []);

    async function review(id, action) {
        const note = action === "reject" ? (prompt("Optional reason for rejection (sent in email):") || "") : "";
        setBusy({ ...busy, [id]: true });
        try {
            const { data } = await api.post(`/admin/applications/${id}/review`, { action, note });
            if (action === "approve") {
                if (data?.welcome_email_sent) {
                    toast.success("Approved — Welcome email delivered to the applicant.");
                } else {
                    toast.warning(`Approved, but welcome email did NOT send: ${data?.welcome_email_detail || "unknown error"}. Check Resend domain config.`, { duration: 8000 });
                }
            } else {
                toast.success("Application rejected");
            }
            await load();
            if (action === "approve") onApproved?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        }
        setBusy({ ...busy, [id]: false });
    }

    if (apps.length === 0) return null;
    return (
        <div className="bg-card rounded-2xl border-2 border-primary/20 shadow-warm p-5 mb-6" data-testid="applications-panel">
            <div className="flex items-end justify-between mb-3 gap-3 flex-wrap">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] font-bold text-primary">Pending applications</div>
                    <h3 className="font-heading text-xl font-bold mt-1">{apps.length} awaiting review</h3>
                </div>
            </div>
            <div className="space-y-2">
                {apps.map((a) => (
                    <div key={a.id} className="border border-border rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`application-${a.id}`}>
                        <div className="flex-1 min-w-0">
                            <div className="font-heading text-base font-bold truncate">{a.name}</div>
                            <div className="text-xs text-muted-foreground truncate">{a.email} · {a.intake_line || "no line"}{a.intake_completed_at ? ` · Intake ${a.intake_completed_at}` : ""}</div>
                            <div className="text-xs text-muted-foreground mt-0.5 truncate">{[a.address, a.city, a.state, a.zip_code, a.country].filter(Boolean).join(", ")}</div>
                        </div>
                        <div className="flex gap-2 shrink-0">
                            <Button size="sm" variant="outline" disabled={busy[a.id]} onClick={() => review(a.id, "reject")} className="rounded-full" data-testid={`reject-application-${a.id}`}>Reject</Button>
                            <Button size="sm" disabled={busy[a.id]} onClick={() => review(a.id, "approve")} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`approve-application-${a.id}`}>Approve</Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function PendingIntakeChangesPanel({ onChanged }) {
    const [items, setItems] = useState([]);
    const [busy, setBusy] = useState({});

    async function load() {
        try {
            const { data } = await api.get("/admin/pending-intake-changes");
            setItems(data || []);
        } catch { setItems([]); }
    }
    useEffect(() => { load(); }, []);

    async function review(id, action) {
        const note = action === "reject" ? (prompt("Optional reason for rejection:") || "") : "";
        setBusy({ ...busy, [id]: true });
        try {
            await api.post(`/admin/members/${id}/intake-completion-review`, { action, note });
            toast.success(action === "approve" ? "Intake date approved" : "Intake date change rejected");
            await load();
            onChanged?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        }
        setBusy({ ...busy, [id]: false });
    }

    if (items.length === 0) return null;
    return (
        <div className="bg-amber-50 dark:bg-amber-950/20 rounded-2xl border-2 border-amber-300 shadow-warm p-5 mb-6" data-testid="pending-intake-panel">
            <div className="flex items-end justify-between mb-3 gap-3 flex-wrap">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] font-bold text-amber-700">Pending intake date changes</div>
                    <h3 className="font-heading text-xl font-bold mt-1">{items.length} awaiting review</h3>
                </div>
            </div>
            <div className="space-y-2">
                {items.map((m) => (
                    <div key={m.id} className="border border-amber-200 bg-white rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`intake-change-${m.id}`}>
                        <div className="flex-1 min-w-0">
                            <div className="font-heading text-base font-bold truncate">{m.name}</div>
                            <div className="text-xs text-muted-foreground truncate">{m.email}{m.line_name && ` · "${m.line_name}"`}</div>
                            <div className="text-xs mt-1">
                                Current: <strong>{m.current_intake_completed_at || "—"}</strong>
                                <span className="mx-2 opacity-60">→</span>
                                Requested: <strong className="text-amber-700">{m.pending_intake_completed_at}</strong>
                            </div>
                        </div>
                        <div className="flex gap-2 shrink-0">
                            <Button size="sm" variant="outline" disabled={busy[m.id]} onClick={() => review(m.id, "reject")} className="rounded-full" data-testid={`reject-intake-${m.id}`}>Reject</Button>
                            <Button size="sm" disabled={busy[m.id]} onClick={() => review(m.id, "approve")} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`approve-intake-${m.id}`}>Approve</Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}


function MembersAdmin() {
    const { user: me } = useAuth();
    const isFullAdmin = (me?.admin_role || "full") === "full";
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
            <ApplicationsPanel onApproved={load} />
            <PendingIntakeChangesPanel onChanged={load} />
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <Input placeholder="Search members…" value={q} onChange={(e) => setQ(e.target.value)} className="rounded-full max-w-sm" data-testid="admin-member-search" />
                <div className="flex items-center gap-2">
                    <BulkImportMembersDialog chapters={chapters.filter(officialOnly)} onImported={load} />
                    <NewMemberDialog chapters={chapters} tiers={tiers} onSaved={load} />
                </div>
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
                                            {chapters.filter(officialOnly).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </td>
                                <td className="px-4 py-3">
                                    <Select value={m.tier_id || ""} onValueChange={(v) => setTier(m, v)} disabled={!isFullAdmin}>
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
                                    {m.is_lifetime_member ? (
                                        <span className="text-primary font-semibold">Lifetime</span>
                                    ) : (
                                        <>
                                            {m.membership_expires_at ? format(parseISO(m.membership_expires_at), "MMM d, yyyy") : "—"}
                                            {m.within_grace && <span className="ml-2 text-[10px] bg-destructive/15 text-destructive rounded-full px-2 py-0.5">grace</span>}
                                        </>
                                    )}
                                </td>
                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                    <MemberCardDialog member={m} chapters={chapters} tiers={tiers} />
                                    {!m.is_lifetime_member && (
                                        <Button size="sm" variant="outline" className="rounded-full h-7 text-xs mx-1" onClick={() => extendMembership(m, 365)} data-testid={`extend-${m.id}`}>+1yr</Button>
                                    )}
                                    <EditMemberDialog member={m} chapters={chapters} tiers={tiers} isFullAdmin={isFullAdmin} onSaved={load} />
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
        email: "", password: "", title: "", first_name: "", middle_name: "", last_name: "",
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
            setForm({ email: "", password: "", title: "", first_name: "", middle_name: "", last_name: "", line_name: "", username: "", phone: "", city: "", address: "", birthdate: "", branch_of_service: "", role: "member", chapter_id: "", tier_id: "", member_status: "active" });
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
                    <div className="grid grid-cols-[110px_1fr_100px_1fr] gap-3">
                        <div>
                            <Label>Title</Label>
                            <Select value={form.title} onValueChange={(v) => setForm({ ...form, title: v === "__none__" ? "" : v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="nm-title"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__none__">— None —</SelectItem>
                                    {["Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Rev.", "Hon.", "Mx."].map((t) => (
                                        <SelectItem key={t} value={t}>{t}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
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
                                <SelectContent>{chapters.filter(officialOnly).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
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

function EditMemberDialog({ member, chapters, tiers, isFullAdmin = true, onSaved }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({});
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (open) {
            setForm({
                email: member.email,
                title: member.title || "",
                first_name: member.first_name || "",
                middle_name: member.middle_name || "",
                last_name: member.last_name || "",
                line_name: member.line_name || "",
                intake_line: member.intake_line || "",
                intake_completed_at: member.intake_completed_at || "",
                username: member.username || "",
                phone: member.phone || "",
                city: member.city || "",
                address: member.address || "",
                state: member.state || "",
                zip_code: member.zip_code || "",
                country: member.country || "",
                birthdate: member.birthdate ? member.birthdate.slice(0, 10) : "",
                branch_of_service: member.branch_of_service || "",
                bio: member.bio || "",
                avatar_url: member.avatar_url || "",
                chapter_id: member.chapter_id || "",
                tier_id: member.tier_id || "",
                role: member.role,
                admin_role: member.admin_role || "full",
                join_date: member.join_date ? member.join_date.slice(0, 10) : "",
                membership_expires_at: member.membership_expires_at ? member.membership_expires_at.slice(0, 10) : "",
                member_status: member.status_override || member.status || "active",
                new_password: "",
                assignment_history: member.assignment_history || [],
            });
        }
    }, [open, member]);

    async function save() {
        setBusy(true);
        try {
            const payload = Object.fromEntries(Object.entries(form).filter(([_, v]) => v !== "" && v !== null && v !== undefined));
            if (!payload.new_password) delete payload.new_password;
            // Always send assignment_history even when empty so admins can clear all rows.
            payload.assignment_history = form.assignment_history || [];
            // Convert join_date YYYY-MM-DD to ISO timestamp so backend recomputes membership_expires_at
            if (payload.join_date && payload.join_date.length === 10) {
                payload.join_date = new Date(`${payload.join_date}T00:00:00Z`).toISOString();
            }
            // Convert membership_expires_at YYYY-MM-DD to ISO so backend stores it
            // verbatim (overriding the auto-calculation from join_date)
            if (payload.membership_expires_at && payload.membership_expires_at.length === 10) {
                payload.membership_expires_at = new Date(`${payload.membership_expires_at}T00:00:00Z`).toISOString();
            }
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
                    <div className="grid grid-cols-[110px_1fr_100px_1fr] gap-3">
                        <div>
                            <Label>Title</Label>
                            <Select value={form.title || "__none__"} onValueChange={(v) => setForm({ ...form, title: v === "__none__" ? "" : v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="em-title"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__none__">— None —</SelectItem>
                                    {["Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Rev.", "Hon.", "Mx."].map((t) => (
                                        <SelectItem key={t} value={t}>{t}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div><Label>First name</Label><Input value={form.first_name || ""} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-first" /></div>
                        <div><Label>Middle</Label><Input value={form.middle_name || ""} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>Last name</Label><Input value={form.last_name || ""} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Line name</Label><Input value={form.line_name || ""} onChange={(e) => setForm({ ...form, line_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-line" /></div>
                        <div><Label>Phone</Label><Input value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Intake line</Label><Input value={form.intake_line || ""} onChange={(e) => setForm({ ...form, intake_line: e.target.value })} className="rounded-xl mt-1.5" placeholder="Spring '24 — A1" data-testid="em-intake-line" /></div>
                        <div><Label>Intake completion date <span className="text-xs text-muted-foreground font-normal">(Month/Year)</span></Label><Input type="month" value={form.intake_completed_at || ""} onChange={(e) => setForm({ ...form, intake_completed_at: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-intake-completed-at" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Address</Label><Input value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-address" /></div>
                        <div><Label>City</Label><Input value={form.city || ""} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>State</Label><Input value={form.state || ""} onChange={(e) => setForm({ ...form, state: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-state" placeholder="TX" /></div>
                        <div><Label>Zip code</Label><Input value={form.zip_code || ""} onChange={(e) => setForm({ ...form, zip_code: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-zip" placeholder="77001" /></div>
                        <div><Label>Country</Label><Input value={form.country || ""} onChange={(e) => setForm({ ...form, country: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-country" placeholder="USA" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Date joined <span className="text-xs text-muted-foreground font-normal">(recomputes renewal date)</span></Label>
                            <Input type="date" value={form.join_date || ""} onChange={(e) => setForm({ ...form, join_date: e.target.value })} className="rounded-xl mt-1.5" data-testid="em-join-date" />
                        </div>
                        <div>
                            <Label>Membership expires <span className="text-xs text-muted-foreground font-normal">{isFullAdmin ? "(editable — overrides auto from join date)" : "(auto from join date)"}</span></Label>
                            {isFullAdmin ? (
                                <Input
                                    type="date"
                                    value={form.membership_expires_at || ""}
                                    onChange={(e) => setForm({ ...form, membership_expires_at: e.target.value })}
                                    className="rounded-xl mt-1.5"
                                    data-testid="em-membership-expires"
                                />
                            ) : (
                                <div className="rounded-xl mt-1.5 px-3 py-2 bg-muted/40 text-sm text-muted-foreground" data-testid="em-expires-preview">
                                    {(() => {
                                        const selectedTier = tiers.find((t) => t.id === form.tier_id);
                                        if (selectedTier?.is_lifetime) return <span className="text-primary font-semibold">Lifetime · no expiration</span>;
                                        if (form.join_date) return format(new Date(new Date(`${form.join_date}T00:00:00Z`).getTime() + 365 * 86400000), "MMM d, yyyy");
                                        return member.membership_expires_at ? format(parseISO(member.membership_expires_at), "MMM d, yyyy") : "—";
                                    })()}
                                </div>
                            )}
                            {isFullAdmin && form.membership_expires_at && (() => {
                                const selectedTier = tiers.find((t) => t.id === form.tier_id);
                                return selectedTier?.is_lifetime
                                    ? <div className="text-xs text-primary mt-1 font-semibold">Lifetime tier — expiration ignored.</div>
                                    : null;
                            })()}
                        </div>
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
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="em-chapter"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>{chapters.filter(officialOnly).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Tier {!isFullAdmin && <span className="text-xs font-normal text-muted-foreground">(only full Admins can change)</span>}</Label>
                            <Select value={form.tier_id || ""} onValueChange={(v) => setForm({ ...form, tier_id: v })} disabled={!isFullAdmin}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>{tiers.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Role</Label>
                            <Select value={form.role || "member"} onValueChange={(v) => setForm({ ...form, role: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="em-role"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="member">Member</SelectItem>
                                    <SelectItem value="admin">Admin</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    {form.role === "admin" && (
                        <div>
                            <Label>Admin permissions</Label>
                            <Select value={form.admin_role || "full"} onValueChange={(v) => setForm({ ...form, admin_role: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="em-admin-role"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="full">Admin (full access)</SelectItem>
                                    <SelectItem value="membership_manager">Membership Manager</SelectItem>
                                    <SelectItem value="operations_manager">Operations Manager</SelectItem>
                                    <SelectItem value="governor_manager">Governor Manager (chapter-scoped)</SelectItem>
                                </SelectContent>
                            </Select>
                            <div className="text-xs text-muted-foreground mt-1.5">
                                Membership Manager: dashboard, members, chapters, tiers, events, awards, reports, email.<br />
                                Operations Manager: dashboard, members, chapters, events, hours, causes, reports, news.<br />
                                Governor Manager: only their own chapter — dashboard, hours, causes, reports.
                            </div>
                        </div>
                    )}
                    <div><Label>Bio</Label><Textarea rows={3} value={form.bio || ""} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
                        <label className="flex items-start gap-2 cursor-pointer">
                            <input
                                type="checkbox"
                                className="mt-1 h-4 w-4 rounded"
                                checked={!!form.trust_zeffy}
                                onChange={(e) => setForm({ ...form, trust_zeffy: e.target.checked })}
                                data-testid="em-trust-zeffy"
                            />
                            <div className="flex-1">
                                <div className="text-sm font-semibold">Auto-approve Zeffy dues payments</div>
                                <div className="text-xs text-muted-foreground">When ON, dues submissions with a valid-looking Zeffy receipt # are immediately approved and membership is extended 365 days — no admin review needed.</div>
                            </div>
                        </label>
                    </div>
                    <div><Label>Reset password (optional)</Label><Input type="password" value={form.new_password || ""} onChange={(e) => setForm({ ...form, new_password: e.target.value })} className="rounded-xl mt-1.5" placeholder="Leave blank to keep current" data-testid="em-new-password" /></div>
                    <AssignmentHistoryEditor
                        value={form.assignment_history}
                        onChange={(v) => setForm({ ...form, assignment_history: v })}
                        chapters={chapters}
                    />
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
                        <div className="flex items-start gap-3">
                            {c.logo_url && <img src={mediaUrl(c.logo_url)} alt={c.name} className="w-12 h-12 rounded-xl object-cover border border-border shrink-0" />}
                            <div className="flex-1 min-w-0">
                                <div className="font-heading font-semibold text-lg">{c.name}</div>
                                <div className="text-sm text-muted-foreground">
                                    {c.region && <>{c.region} region</>}
                                    {c.region && c.state ? " · " : ""}
                                    {c.state}
                                </div>
                                <div className="text-xs text-muted-foreground mt-1">Founded {c.founded_year || "—"} · {c.member_count} members</div>
                            </div>
                            <div className="flex gap-1 shrink-0">
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
        logo_url: chapter?.logo_url || "",
    });
    async function save() {
        if (!form.name) { toast.error("Pick a chapter from the list"); return; }
        try {
            const payload = { ...form, founded_year: form.founded_year ? Number(form.founded_year) : null };
            if (chapter) await api.put(`/chapters/${chapter.id}`, payload);
            else await api.post("/chapters", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    async function uploadLogo(file) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { toast.error("Image must be under 10 MB"); return; }
        const fd = new FormData(); fd.append("file", file);
        try {
            const { data } = await api.post("/chapters/upload-logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setForm((p) => ({ ...p, logo_url: data.url }));
            toast.success("Logo uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{chapter ? "Edit chapter" : "New chapter"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div>
                        <Label>Chapter name *</Label>
                        <Input
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            placeholder="e.g. Texas, Florida, Tri-South, DMV, Carolinas, Pacific Northwest"
                            className="rounded-xl mt-1.5"
                            data-testid="chapter-name-input"
                        />
                        <div className="text-xs text-muted-foreground mt-1.5">Type any name. Existing official chapters: Texas, Florida, Tri-South, DMV.</div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Region</Label><Input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="e.g. South, Mid-Atlantic" className="rounded-xl mt-1.5" data-testid="chapter-region-input" /></div>
                        <div><Label>State</Label><Input value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} placeholder="e.g. TX, FL, Multi" className="rounded-xl mt-1.5" data-testid="chapter-state-input" /></div>
                    </div>
                    <div><Label>Founded year</Label><Input type="number" value={form.founded_year} onChange={(e) => setForm({ ...form, founded_year: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div><Label>Description</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div>
                        <Label>Chapter logo</Label>
                        <div className="flex items-center gap-2 mt-1.5">
                            <Input value={form.logo_url} onChange={(e) => setForm({ ...form, logo_url: e.target.value })} className="rounded-xl flex-1" placeholder="https://… or upload" data-testid="chapter-logo-url" />
                            <label className="cursor-pointer">
                                <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                    <span data-testid="chapter-logo-upload-btn"><Upload className="h-3.5 w-3.5 mr-1" />Upload</span>
                                </Button>
                                <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadLogo(e.target.files?.[0])} />
                            </label>
                        </div>
                        {form.logo_url && (
                            <img src={mediaUrl(form.logo_url)} alt="Logo preview" className="mt-2 w-24 h-24 rounded-2xl object-cover border border-border" />
                        )}
                    </div>
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
                            <div className="w-14 h-14 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold text-lg shrink-0">{h.hours}<span className="text-[10px] font-normal -mt-0.5">hrs</span></div>
                            <div className="flex-1 min-w-0">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                    <div className="font-heading font-bold text-base">{h.user_name}</div>
                                    <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-accent/40">{h.event_type === "aop_related" ? "AOP-related" : "Other"}</span>
                                    <span className={`text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 ${h.status === "approved" ? "bg-green-100 text-green-700" : h.status === "rejected" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>{h.status}</span>
                                </div>
                                <div className="text-xs text-muted-foreground">{h.date && format(parseISO(h.date), "EEE, MMM d, yyyy")}</div>
                                {h.agency_name && (
                                    <div className="mt-2 text-sm"><span className="text-xs uppercase tracking-wider text-muted-foreground font-bold">Agency:</span> <span className="font-medium">{h.agency_name}</span></div>
                                )}
                                {(h.description || h.activity) && (
                                    <div className="mt-1.5 text-sm bg-muted/40 rounded-xl p-2.5">
                                        <div className="text-xs uppercase tracking-wider text-muted-foreground font-bold mb-1">What did they do</div>
                                        <div className="leading-relaxed">{h.description || h.activity}</div>
                                    </div>
                                )}
                                {(h.host_name || h.host_email || h.host_phone) && (
                                    <div className="mt-1.5 text-xs grid sm:grid-cols-3 gap-1.5 bg-card border border-border rounded-xl p-2.5" data-testid={`admin-hours-host-${h.id}`}>
                                        <div className="text-xs uppercase tracking-wider text-muted-foreground font-bold col-span-full mb-0.5">Verification contact</div>
                                        {h.host_name && <div><span className="font-bold">Host:</span> {h.host_name}</div>}
                                        {h.host_email && <div className="break-all"><span className="font-bold">Email:</span> <a className="text-primary hover:underline" href={`mailto:${h.host_email}`}>{h.host_email}</a></div>}
                                        {h.host_phone && <div><span className="font-bold">Phone:</span> <a className="text-primary hover:underline" href={`tel:${h.host_phone}`}>{h.host_phone}</a></div>}
                                    </div>
                                )}
                            </div>
                            {h.status === "pending" && (
                                <div className="flex flex-col sm:flex-row gap-2 shrink-0">
                                    <Button size="sm" onClick={() => review(h.id, "approved")} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`admin-approve-${h.id}`}>Approve</Button>
                                    <Button size="sm" variant="outline" onClick={() => review(h.id, "rejected")} className="rounded-full" data-testid={`admin-reject-${h.id}`}>Reject</Button>
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
    const [grants, setGrants] = useState([]);
    useEffect(() => {
        if (open) {
            api.get(`/members/${member.id}`).then(({ data }) => setDetails(data)).catch(() => {});
            api.get(`/members/${member.id}/awards`).then(({ data }) => setGrants(data || [])).catch(() => setGrants([]));
        }
    }, [open, member.id]);
    const chapter = chapters?.find((c) => c.id === details.chapter_id);
    const tier = tiers?.find((t) => t.id === details.tier_id);
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                {trigger || <Button size="sm" variant="outline" className="rounded-full h-7 text-xs" data-testid={`view-member-${member.id}`}>View</Button>}
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Member card</DialogTitle></DialogHeader>
                <div className="flex items-center gap-4 mt-1">
                    {details.avatar_url ? (
                        <img src={details.avatar_url} alt={details.name} className="w-20 h-20 rounded-full object-cover border-2 border-white shadow-warm" data-testid={`member-card-${member.id}-avatar`} />
                    ) : (
                        <div className="w-20 h-20 rounded-full bg-primary/15 text-primary grid place-items-center font-heading font-black text-2xl">
                            {(details.name || details.email)[0]?.toUpperCase()}
                        </div>
                    )}
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
                    <DetailRow label="Address" value={[details.address, details.city, details.state, details.zip_code].filter(Boolean).join(", ")} />
                    <DetailRow label="Country" value={details.country} />
                    <DetailRow label="Birthdate" value={details.birthdate ? format(parseISO(details.birthdate.length === 10 ? `${details.birthdate}T00:00:00` : details.birthdate), "MMM d, yyyy") : ""} />
                    <DetailRow label="Branch of service" value={details.branch_of_service} />
                    <DetailRow label="Intake line" value={details.intake_line} />
                    <DetailRow label="Intake completed" value={details.intake_completed_at} />
                    <DetailRow label="Chapter" value={chapter?.name} />
                    <DetailRow label="Member type" value={tier?.name} />
                    <DetailRow label="Date joined" value={details.join_date ? format(parseISO(details.join_date), "MMM d, yyyy") : (details.created_at ? format(parseISO(details.created_at), "MMM d, yyyy") : "")} />
                    {details.is_lifetime_member ? (
                        <div className="flex justify-between gap-3 py-1.5 border-b last:border-0 border-border/40">
                            <span className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">Membership</span>
                            <span className="text-sm font-bold text-primary">Lifetime · no renewal</span>
                        </div>
                    ) : (
                        <DetailRow label="Membership expires" value={details.membership_expires_at ? format(parseISO(details.membership_expires_at), "MMM d, yyyy") : ""} />
                    )}
                    {details.bio && (
                        <div className="pt-2 border-t">
                            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-1">Bio</div>
                            <p className="text-sm leading-relaxed">{details.bio}</p>
                        </div>
                    )}
                    <div className="pt-3 border-t">
                        <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2">
                            Ribbons & Achievements <span className="text-foreground/80">({grants.length})</span>
                        </div>
                        {grants.length === 0 ? (
                            <div className="text-xs text-muted-foreground italic">No ribbons earned yet.</div>
                        ) : (
                            <div className="flex flex-wrap gap-2" data-testid={`member-card-${member.id}-ribbons`}>
                                {grants.map((g) => (
                                    <div
                                        key={g.id}
                                        title={g.granted_at ? format(parseISO(g.granted_at), "MMM d, yyyy") : ""}
                                        className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold bg-primary/10 text-primary border border-primary/20"
                                        data-testid={`ribbon-${g.id}`}
                                    >
                                        <span className="w-2 h-2 rounded-full bg-primary"></span>
                                        {g.award_name || g.name || "Ribbon"}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="pt-2 text-[10px] text-muted-foreground italic">
                        Secure data (passwords, payment methods, transactions) is intentionally hidden.
                    </div>
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

/* -------- Gear Admin -------- */
function GearAdmin() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/gear").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) {
        if (!confirm("Remove this gear item?")) return;
        await api.delete(`/gear/${id}`);
        toast.success("Removed");
        load();
    }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <GearDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-gear-btn"><Plus className="h-4 w-4 mr-1" />New item</Button>} />
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {items.map((g) => (
                    <div key={g.id} className="bg-card border border-border rounded-2xl overflow-hidden" data-testid={`admin-gear-${g.id}`}>
                        <div className="aspect-video bg-muted overflow-hidden">
                            {g.cover_image && <img src={g.cover_image} alt={g.name} className="w-full h-full object-cover" />}
                        </div>
                        <div className="p-4">
                            <div className="flex items-start justify-between gap-3">
                                <div className="font-heading font-semibold leading-tight">{g.name}</div>
                                <div className="font-bold shrink-0">${g.price?.toFixed(0)}</div>
                            </div>
                            <div className="text-xs text-muted-foreground mt-1">{g.category} · {g.sku || "—"} · {g.in_stock ? "In stock" : "Sold out"}</div>
                            <div className="mt-3 flex gap-1">
                                <GearDialog item={g} onSaved={load} trigger={<Button variant="outline" size="sm" className="rounded-full text-xs">Edit</Button>} />
                                <Button variant="ghost" size="icon" onClick={() => del(g.id)} data-testid={`delete-gear-${g.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>
                    </div>
                ))}
                {items.length === 0 && <div className="col-span-full text-muted-foreground text-center py-8">No gear yet.</div>}
            </div>
        </div>
    );
}

function GearDialog({ item, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState(emptyGear());
    useEffect(() => {
        if (open) {
            setForm(item ? {
                ...item,
                price: item.price ?? 0,
                sizes: (item.sizes || []).join(", "),
                colors: (item.colors || []).join(", "),
            } : emptyGear());
        }
    }, [open, item]);

    async function save() {
        try {
            const payload = {
                ...form,
                price: Number(form.price) || 0,
                sizes: form.sizes.split(",").map((s) => s.trim()).filter(Boolean),
                colors: form.colors.split(",").map((s) => s.trim()).filter(Boolean),
            };
            if (item) await api.put(`/gear/${item.id}`, payload);
            else await api.post("/gear", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{item ? "Edit gear" : "New gear item"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="gear-name-input" /></div>
                    <div><Label>Description</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>Price ($)</Label><Input type="number" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div><Label>SKU</Label><Input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div>
                            <Label>Category</Label>
                            <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="apparel">Apparel</SelectItem>
                                    <SelectItem value="accessory">Accessory</SelectItem>
                                    <SelectItem value="memorabilia">Memorabilia</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div><Label>Cover image URL</Label><Input value={form.cover_image} onChange={(e) => setForm({ ...form, cover_image: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://…" /></div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Sizes (comma)</Label><Input value={form.sizes} onChange={(e) => setForm({ ...form, sizes: e.target.value })} className="rounded-xl mt-1.5" placeholder="S, M, L, XL" /></div>
                        <div><Label>Colors (comma)</Label><Input value={form.colors} onChange={(e) => setForm({ ...form, colors: e.target.value })} className="rounded-xl mt-1.5" placeholder="Navy, Red, White" /></div>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={form.in_stock} onChange={(e) => setForm({ ...form, in_stock: e.target.checked })} /> In stock
                    </label>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="gear-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
function emptyGear() {
    return { name: "", description: "", price: 0, sku: "", category: "apparel", cover_image: "", sizes: "", colors: "", in_stock: true };
}

/* -------- Causes Admin -------- */
function CausesAdmin() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/causes").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) {
        if (!confirm("Delete this cause?")) return;
        await api.delete(`/causes/${id}`);
        toast.success("Deleted");
        load();
    }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <CauseDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-cause-btn"><Plus className="h-4 w-4 mr-1" />New cause</Button>} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
                {items.map((c) => {
                    const pct = c.goal_amount > 0 ? Math.min(100, Math.round((c.raised_amount / c.goal_amount) * 100)) : 0;
                    return (
                        <div key={c.id} className="bg-card border border-border rounded-2xl overflow-hidden" data-testid={`admin-cause-${c.id}`}>
                            {c.cover_image && <div className="aspect-[3/1] bg-muted overflow-hidden"><img src={c.cover_image} alt={c.title} className="w-full h-full object-cover" /></div>}
                            <div className="p-5">
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <div className="font-heading font-semibold text-lg">{c.title}</div>
                                        <div className="text-xs text-muted-foreground mt-1">${c.raised_amount.toFixed(0)} / ${c.goal_amount.toFixed(0)} ({pct}%) · {c.donor_count} donors · {c.is_active ? "active" : "paused"}</div>
                                    </div>
                                    <div className="flex gap-1 shrink-0">
                                        <CauseDialog cause={c} onSaved={load} trigger={<Button variant="outline" size="sm" className="rounded-full">Edit</Button>} />
                                        <Button variant="ghost" size="icon" onClick={() => del(c.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                    </div>
                                </div>
                                <div className="mt-3 w-full bg-muted rounded-full h-2 overflow-hidden">
                                    <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                                </div>
                            </div>
                        </div>
                    );
                })}
                {items.length === 0 && <div className="col-span-full text-muted-foreground text-center py-8">No causes yet.</div>}
            </div>
        </div>
    );
}

function CauseDialog({ cause, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState(emptyCause());
    useEffect(() => {
        if (open) setForm(cause ? { ...cause, goal_amount: cause.goal_amount ?? 0 } : emptyCause());
    }, [open, cause]);

    async function save() {
        try {
            const payload = { ...form, goal_amount: Number(form.goal_amount) || 0 };
            if (cause) await api.put(`/causes/${cause.id}`, payload);
            else await api.post("/causes", payload);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{cause ? "Edit cause" : "New cause"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" data-testid="cause-title-input" /></div>
                    <div><Label>Description</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Goal ($)</Label><Input type="number" step="100" value={form.goal_amount} onChange={(e) => setForm({ ...form, goal_amount: e.target.value })} className="rounded-xl mt-1.5" /></div>
                        <div>
                            <Label>Category</Label>
                            <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="general">General</SelectItem>
                                    <SelectItem value="veteran">Veteran</SelectItem>
                                    <SelectItem value="education">Education</SelectItem>
                                    <SelectItem value="anniversary">Anniversary</SelectItem>
                                    <SelectItem value="emergency">Emergency</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div>
                        <Label>Cover photo</Label>
                        <label className="mt-1.5 rounded-xl border-2 border-dashed border-slate-300 px-4 py-3 text-sm font-semibold cursor-pointer hover:bg-white hover:border-primary transition-colors flex items-center gap-2 justify-center" data-testid="cause-image-upload-btn">
                            <Upload className="h-4 w-4" />{form.cover_image ? "Replace cover photo" : "Upload cover photo"}
                            <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
                                const f = e.target.files?.[0]; if (!f) return;
                                if (f.size > 10 * 1024 * 1024) { toast.error("Image must be under 10 MB"); return; }
                                const fd = new FormData(); fd.append("file", f);
                                try {
                                    const { data } = await api.post("/causes/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
                                    setForm((p) => ({ ...p, cover_image: data.url }));
                                    toast.success("Cover photo uploaded");
                                } catch (err) { toast.error(err.response?.data?.detail || "Upload failed"); }
                            }} />
                        </label>
                        {form.cover_image && (
                            <img src={mediaUrl(form.cover_image)} alt="Cause preview" className="mt-2 w-full max-h-32 object-contain rounded-xl border border-border bg-slate-50" />
                        )}
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active
                    </label>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="cause-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
function emptyCause() {
    return { title: "", description: "", goal_amount: 0, cover_image: "", category: "general", is_active: true };
}

/* -------- Email Blast Admin (Resend) -------- */
function EmailBlastAdmin() {
    const [view, setView] = useState("compose");
    return (
        <Tabs value={view} onValueChange={setView}>
            <div className="-mx-2 px-2 sm:mx-0 sm:px-0 overflow-x-auto sm:overflow-x-visible scrollbar-hide max-w-full">
                <TabsList className="rounded-full bg-muted p-1 inline-flex sm:flex sm:flex-wrap sm:h-auto whitespace-nowrap w-max sm:w-full">
                    <TabsTrigger value="compose" className="rounded-full" data-testid="email-tab-compose"><Send className="h-4 w-4 mr-1.5" />Compose</TabsTrigger>
                    <TabsTrigger value="templates" className="rounded-full" data-testid="email-tab-templates"><FileText className="h-4 w-4 mr-1.5" />Templates</TabsTrigger>
                    <TabsTrigger value="signatures" className="rounded-full" data-testid="email-tab-signatures"><PenSquare className="h-4 w-4 mr-1.5" />Signatures</TabsTrigger>
                    <TabsTrigger value="history" className="rounded-full" data-testid="email-tab-history"><Clock className="h-4 w-4 mr-1.5" />History</TabsTrigger>
                    <TabsTrigger value="test-send" className="rounded-full" data-testid="email-tab-test-send"><Send className="h-4 w-4 mr-1.5" />Test send</TabsTrigger>
                    <TabsTrigger value="automated" className="rounded-full" data-testid="email-tab-automated"><Clock className="h-4 w-4 mr-1.5" />Automated</TabsTrigger>
                </TabsList>
            </div>
            <TabsContent value="compose" className="mt-6"><ComposeBlast /></TabsContent>
            <TabsContent value="templates" className="mt-6"><EmailTemplates /></TabsContent>
            <TabsContent value="signatures" className="mt-6"><EmailSignatures /></TabsContent>
            <TabsContent value="history" className="mt-6"><BlastHistory /></TabsContent>
            <TabsContent value="test-send" className="mt-6"><EmailTestSend /></TabsContent>
            <TabsContent value="automated" className="mt-6"><AutomatedEmailsAdmin /></TabsContent>
        </Tabs>
    );
}

function EmailTestSend() {
    const [toEmail, setToEmail] = useState("");
    const [subject, setSubject] = useState("");
    const [templateId, setTemplateId] = useState("");
    const [templates, setTemplates] = useState([]);
    const [busy, setBusy] = useState(false);
    const [lastResult, setLastResult] = useState(null);

    useEffect(() => {
        api.get("/email/templates").then(({ data }) => setTemplates(data || [])).catch(() => setTemplates([]));
    }, []);

    const selectedTemplate = templates.find((t) => t.id === templateId);

    async function send() {
        if (!toEmail.trim() || !toEmail.includes("@")) {
            toast.error("Enter a valid email address.");
            return;
        }
        setBusy(true);
        setLastResult(null);
        try {
            const payload = { to_email: toEmail.trim() };
            if (subject.trim()) payload.subject = subject.trim();
            if (templateId) payload.template_id = templateId;
            const { data } = await api.post("/email/test-send", payload);
            setLastResult(data);
            if (data.ok) {
                toast.success(`Test email accepted by Resend (to ${data.to}).`);
            } else {
                toast.error(`Resend rejected the test: ${data.detail || "unknown error"}`, { duration: 10000 });
            }
        } catch (e) {
            const detail = e.response?.data?.detail || "Failed to send test email";
            setLastResult({ ok: false, detail });
            toast.error(detail);
        }
        setBusy(false);
    }

    return (
        <div className="max-w-xl space-y-5" data-testid="email-test-send-panel">
            <div className="bg-card border border-border rounded-2xl p-5">
                <h3 className="font-heading text-xl font-bold mb-1">Send a test email</h3>
                <p className="text-sm text-muted-foreground">Validate that Resend is configured and your verified sending domain is reaching inboxes — without having to approve a real applicant or queue a blast.</p>
            </div>
            <div>
                <Label>Recipient email *</Label>
                <Input
                    type="email"
                    value={toEmail}
                    onChange={(e) => setToEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="rounded-xl mt-1.5"
                    data-testid="test-email-to-input"
                />
                <p className="text-xs text-muted-foreground mt-1.5">Tip: Send to a separate inbox (Gmail, Yahoo, Outlook) to confirm external deliverability.</p>
            </div>
            <div>
                <Label>Use a saved template <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                <Select value={templateId || "__none__"} onValueChange={(v) => setTemplateId(v === "__none__" ? "" : v)}>
                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="test-email-template-select">
                        <SelectValue placeholder="No template — send the deliverability check" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="__none__">No template — send the deliverability check</SelectItem>
                        {templates.map((t) => (
                            <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {selectedTemplate && (
                    <p className="text-xs text-muted-foreground mt-1.5">
                        Template subject: <em>{selectedTemplate.subject || "(none)"}</em>. Variables like <code>{"{{first_name}}"}</code> will render with <strong>your</strong> profile values so the preview is realistic.
                    </p>
                )}
            </div>
            <div>
                <Label>Subject override <span className="text-xs text-muted-foreground font-normal">(optional — leave blank to use the template's subject)</span></Label>
                <Input
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder={selectedTemplate?.subject || "Alpha Omega Phi — Test email"}
                    className="rounded-xl mt-1.5"
                    data-testid="test-email-subject-input"
                />
            </div>
            <Button onClick={send} disabled={busy || !toEmail.trim()} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="test-email-send-btn">
                <Send className="h-4 w-4 mr-1.5" />{busy ? "Sending…" : "Send test email"}
            </Button>
            {lastResult && (
                <div
                    className={`rounded-2xl border p-4 text-sm ${lastResult.ok ? "border-green-300 bg-green-50 text-green-900" : "border-red-300 bg-red-50 text-red-900"}`}
                    data-testid="test-email-result"
                >
                    <div className="font-semibold mb-1">{lastResult.ok ? "Resend accepted the test." : "Resend rejected the test."}</div>
                    <div className="text-xs leading-relaxed">{lastResult.detail}</div>
                    {lastResult.template_name && <div className="text-xs mt-2 opacity-80">Template: <code>{lastResult.template_name}</code></div>}
                    {lastResult.subject && <div className="text-xs opacity-80">Subject: <code>{lastResult.subject}</code></div>}
                    {lastResult.from && <div className="text-xs opacity-80">From: <code>{lastResult.from}</code></div>}
                    {lastResult.to && <div className="text-xs opacity-80">To: <code>{lastResult.to}</code></div>}
                    {lastResult.message_id && <div className="text-xs opacity-80">Message id: <code>{lastResult.message_id}</code></div>}
                </div>
            )}
        </div>
    );
}

function ComposeBlast() {
    const [subject, setSubject] = useState("");
    const [body_html, setBody] = useState("<p>Hello {{first_name}},</p><p>Write your message here. Use the toolbar — bold, lists, images, links — no code needed.</p><p>— Alpha Omega Phi</p>");
    const [segment, setSegment] = useState("active");
    const [tier_id, setTierId] = useState("");
    const [chapter_id, setChapterId] = useState("");
    const [individualId, setIndividualId] = useState("");
    const [memberSearch, setMemberSearch] = useState("");
    const [tiers, setTiers] = useState([]);
    const [chapters, setChapters] = useState([]);
    const [members, setMembers] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [signatures, setSignatures] = useState([]);
    const [preview, setPreview] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get("/tiers").then(({ data }) => setTiers(data)).catch(() => {});
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
        api.get("/email/templates").then(({ data }) => setTemplates(data)).catch(() => {});
        api.get("/email/signatures").then(({ data }) => setSignatures(data)).catch(() => {});
    }, []);

    function applyTemplate(tid) {
        const t = templates.find((x) => x.id === tid);
        if (!t) return;
        setSubject(t.subject);
        setBody(t.body_html);
    }

    function insertSignature(sid) {
        const s = signatures.find((x) => x.id === sid);
        if (!s) return;
        setBody((prev) => {
            const sep = '<p>—</p>';
            return (prev || "") + sep + (s.body_html || "");
        });
        toast.success(`Inserted "${s.name}"`);
    }

    function buildPayload() {
        const payload = { subject, body_html, segment, tier_id: tier_id || undefined, chapter_id: chapter_id || undefined };
        if (segment === "individual") {
            payload.segment = "custom";
            payload.custom_user_ids = individualId ? [individualId] : [];
        }
        return payload;
    }

    async function runPreview() {
        try {
            const { data } = await api.post("/email/preview", buildPayload());
            setPreview(data);
        } catch (e) { toast.error(e.response?.data?.detail || "Preview failed"); }
    }

    async function sendBlast(test_only = false) {
        if (!subject || !body_html) { toast.error("Subject and body required"); return; }
        if (!test_only && !confirm(`Send to ${preview?.recipient_count ?? "all matching"} recipients?`)) return;
        setBusy(true);
        try {
            const { data } = await api.post("/email/blast", { ...buildPayload(), test_only });
            toast.success(`Sent: ${data.sent}, failed: ${data.failed}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Send failed");
        }
        setBusy(false);
    }

    return (
        <div className="grid lg:grid-cols-[1fr_400px] gap-6">
            <div className="bg-card rounded-2xl border border-border p-6 space-y-4 shadow-warm">
                <div className="grid sm:grid-cols-2 gap-3">
                    {templates.length > 0 && (
                        <div>
                            <Label>Start from template</Label>
                            <Select value="" onValueChange={applyTemplate}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="email-template-picker"><SelectValue placeholder="Pick a template…" /></SelectTrigger>
                                <SelectContent>{templates.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                    )}
                    {signatures.length > 0 && (
                        <div>
                            <Label>Insert signature</Label>
                            <Select value="" onValueChange={insertSignature}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="email-signature-picker"><SelectValue placeholder="Append a signature…" /></SelectTrigger>
                                <SelectContent>{signatures.map((s) => <SelectItem key={s.id} value={s.id}>{s.name} {s.kind === "org" ? "(shared)" : "(personal)"}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                    )}
                </div>
                <div>
                    <Label>Subject *</Label>
                    <Input value={subject} onChange={(e) => setSubject(e.target.value)} className="rounded-xl mt-1.5" placeholder="Hi {{first_name}}, news from your chapter" data-testid="email-subject" />
                </div>
                <div>
                    <Label>Body *</Label>
                    <div className="mt-1.5">
                        <RichEditor value={body_html} onChange={setBody} placeholder="Write your message — press Enter for new lines, use toolbar for images." minHeight={300} />
                    </div>
                    <div className="text-xs text-muted-foreground mt-1.5">Variables: <code>{"{{name}}"}</code>, <code>{"{{first_name}}"}</code>, <code>{"{{last_name}}"}</code>, <code>{"{{line_name}}"}</code>, <code>{"{{email}}"}</code></div>
                </div>
                <div className="grid sm:grid-cols-3 gap-3">
                    <div>
                        <Label>Segment</Label>
                        <Select value={segment} onValueChange={setSegment}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="email-segment"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="active">All active members</SelectItem>
                                <SelectItem value="all">Everyone (incl. Omega)</SelectItem>
                                <SelectItem value="admins">Admins only</SelectItem>
                                <SelectItem value="tier">By tier</SelectItem>
                                <SelectItem value="chapter">By chapter</SelectItem>
                                <SelectItem value="individual">Individual member</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    {segment === "tier" && (
                        <div>
                            <Label>Tier</Label>
                            <Select value={tier_id} onValueChange={setTierId}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue placeholder="Pick" /></SelectTrigger>
                                <SelectContent>{tiers.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                    )}
                    {segment === "chapter" && (
                        <div>
                            <Label>Chapter</Label>
                            <Select value={chapter_id} onValueChange={setChapterId}>
                                <SelectTrigger className="rounded-xl mt-1.5"><SelectValue placeholder="Pick" /></SelectTrigger>
                                <SelectContent>{chapters.filter(officialOnly).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                    )}
                    {segment === "individual" && (
                        <div className="sm:col-span-2">
                            <Label>Member</Label>
                            <Input
                                placeholder="Search by name or email…"
                                value={memberSearch}
                                onChange={(e) => setMemberSearch(e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid="email-individual-search"
                            />
                            <div className="max-h-40 overflow-y-auto mt-2 border border-border rounded-xl bg-muted/20">
                                {members
                                    .filter((m) => {
                                        if (!memberSearch) return true;
                                        const q = memberSearch.toLowerCase();
                                        return m.name?.toLowerCase().includes(q) || m.email?.toLowerCase().includes(q);
                                    })
                                    .slice(0, 30)
                                    .map((m) => (
                                        <button
                                            key={m.id}
                                            type="button"
                                            onClick={() => setIndividualId(m.id)}
                                            className={`w-full text-left px-3 py-2 hover:bg-muted/60 border-b last:border-0 ${individualId === m.id ? "bg-primary/10" : ""}`}
                                            data-testid={`email-individual-pick-${m.id}`}
                                        >
                                            <div className="text-sm font-medium">{m.name}</div>
                                            <div className="text-xs text-muted-foreground">{m.email}</div>
                                        </button>
                                    ))}
                            </div>
                        </div>
                    )}
                </div>
                <div className="flex flex-wrap gap-2 pt-2 border-t">
                    <Button variant="outline" onClick={runPreview} className="rounded-full" data-testid="email-preview-btn">Preview</Button>
                    <Button variant="outline" onClick={() => sendBlast(true)} disabled={busy} className="rounded-full" data-testid="email-test-btn">Send test to me</Button>
                    <Button onClick={() => sendBlast(false)} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 ml-auto" data-testid="email-send-btn">
                        <Send className="h-4 w-4 mr-1.5" /> {busy ? "Sending…" : `Send blast${preview ? ` (${preview.recipient_count})` : ""}`}
                    </Button>
                </div>
            </div>
            <div className="bg-card rounded-2xl border border-border p-5 shadow-warm sticky top-20 h-fit">
                <div className="text-xs uppercase tracking-widest font-bold text-muted-foreground mb-2">Live preview</div>
                {preview ? (
                    <div className="text-sm">
                        <div className="text-xs text-muted-foreground mb-1">
                            Recipients: <strong>{preview.recipient_count}</strong><br />
                            Sample: {preview.sample_recipient.name} &lt;{preview.sample_recipient.email}&gt;
                        </div>
                        <div className="font-bold mt-3 mb-2">{preview.subject}</div>
                        <div className="border rounded-xl p-3 bg-white max-h-96 overflow-auto prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: preview.html }} />
                    </div>
                ) : (
                    <div className="text-sm text-muted-foreground">Click <strong>Preview</strong> to render against a sample recipient.</div>
                )}
            </div>
        </div>
    );
}

// Official chapter filter — used in member-facing chapter pickers.
const OFFICIAL_CHAPTER_NAMES = ["Texas", "Florida", "Tri-South", "DMV"];
const officialOnly = (c) => OFFICIAL_CHAPTER_NAMES.includes(c.name);

function EmailTemplates() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/email/templates").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) {
        if (!confirm("Delete this template?")) return;
        await api.delete(`/email/templates/${id}`);
        load();
    }
    return (
        <div>
            <div className="flex justify-end mb-4">
                <TemplateDialog onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-template-btn"><Plus className="h-4 w-4 mr-1" />New template</Button>} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
                {items.map((t) => (
                    <div key={t.id} className="bg-card border border-border rounded-2xl p-5" data-testid={`template-${t.id}`}>
                        <div className="flex items-start justify-between">
                            <div>
                                <div className="font-heading font-semibold text-lg">{t.name}</div>
                                <div className="text-xs text-muted-foreground mt-1">{t.subject}</div>
                            </div>
                            <div className="flex gap-1">
                                <TemplateDialog template={t} onSaved={load} trigger={<Button variant="outline" size="sm" className="rounded-full">Edit</Button>} />
                                <Button variant="ghost" size="icon" onClick={() => del(t.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>
                        {t.description && <p className="text-sm text-muted-foreground mt-2">{t.description}</p>}
                    </div>
                ))}
                {items.length === 0 && <div className="col-span-full text-muted-foreground text-center py-8">No templates yet. Create reusable email layouts.</div>}
            </div>
        </div>
    );
}

function TemplateDialog({ template, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ name: "", subject: "", body_html: "", description: "" });
    useEffect(() => {
        if (open) setForm(template ? { ...template } : { name: "", subject: "", body_html: "", description: "" });
    }, [open, template]);

    async function save() {
        try {
            if (template) await api.put(`/email/templates/${template.id}`, form);
            else await api.post("/email/templates", form);
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{template ? "Edit template" : "New email template"}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="template-name-input" /></div>
                    <div><Label>Subject</Label><Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} className="rounded-xl mt-1.5" /></div>
                    <div><Label>Description</Label><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" placeholder="What this template is for" /></div>
                    <div>
                        <Label>Body</Label>
                        <div className="mt-1.5">
                            <RichEditor value={form.body_html} onChange={(html) => setForm((f) => ({ ...f, body_html: html }))} placeholder="Write the template body — add images, lists, links from the toolbar." minHeight={260} />
                        </div>
                    </div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="template-save-btn">Save</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* -------- Email Signatures (personal + org) -------- */
function EmailSignatures() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/email/signatures").then(({ data }) => setItems(data));
    useEffect(() => { load(); }, []);
    async function del(id) {
        if (!confirm("Delete this signature?")) return;
        await api.delete(`/email/signatures/${id}`);
        toast.success("Deleted");
        load();
    }
    const personal = items.filter((s) => s.kind === "personal");
    const org = items.filter((s) => s.kind === "org");
    return (
        <div className="space-y-8">
            <div>
                <div className="flex items-center justify-between mb-3">
                    <div>
                        <h3 className="font-heading text-xl font-bold">My signatures</h3>
                        <p className="text-xs text-muted-foreground">Only you can see and edit these.</p>
                    </div>
                    <SignatureDialog kind="personal" onSaved={load} trigger={<Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-personal-sig-btn"><Plus className="h-4 w-4 mr-1" />New personal signature</Button>} />
                </div>
                <SignatureGrid items={personal} onSaved={load} onDelete={del} />
            </div>
            <div>
                <div className="flex items-center justify-between mb-3">
                    <div>
                        <h3 className="font-heading text-xl font-bold">Shared signatures</h3>
                        <p className="text-xs text-muted-foreground">Any admin can use these (President's closing, Chapter footer, etc.)</p>
                    </div>
                    <SignatureDialog kind="org" onSaved={load} trigger={<Button variant="outline" className="rounded-full" data-testid="new-org-sig-btn"><Plus className="h-4 w-4 mr-1" />New shared signature</Button>} />
                </div>
                <SignatureGrid items={org} onSaved={load} onDelete={del} />
            </div>
        </div>
    );
}

function SignatureGrid({ items, onSaved, onDelete }) {
    if (items.length === 0) return <div className="text-sm text-muted-foreground py-6 text-center bg-muted/30 rounded-2xl border-2 border-dashed border-border">No signatures yet — add your name, title, and a photo so members instantly recognize who wrote.</div>;
    return (
        <div className="grid md:grid-cols-2 gap-4">
            {items.map((s) => (
                <div key={s.id} className="bg-card border border-border rounded-2xl p-5" data-testid={`signature-${s.id}`}>
                    <div className="flex items-start justify-between gap-3">
                        <div className="font-heading font-semibold text-lg">{s.name}</div>
                        <div className="flex gap-1 shrink-0">
                            <SignatureDialog signature={s} onSaved={onSaved} trigger={<Button variant="outline" size="sm" className="rounded-full">Edit</Button>} />
                            <Button variant="ghost" size="icon" onClick={() => onDelete(s.id)} data-testid={`delete-signature-${s.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                        </div>
                    </div>
                    <div className="mt-3 border rounded-xl p-3 bg-slate-50 max-h-48 overflow-auto prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: s.body_html }} />
                </div>
            ))}
        </div>
    );
}

function SignatureDialog({ signature, kind, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ name: "", body_html: "", kind: kind || "personal" });
    useEffect(() => {
        if (open) {
            setForm(signature
                ? { name: signature.name, body_html: signature.body_html, kind: signature.kind }
                : { name: "", body_html: "<p><strong>Your Name</strong><br>Title · Chapter</p><p>email@aop.org · 555-0100</p>", kind: kind || "personal" }
            );
        }
    }, [open, signature, kind]);

    async function save() {
        if (!form.name.trim()) { toast.error("Name required"); return; }
        try {
            if (signature) {
                await api.put(`/email/signatures/${signature.id}`, { name: form.name, body_html: form.body_html });
            } else {
                await api.post("/email/signatures", form);
            }
            toast.success("Saved");
            setOpen(false);
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl">{signature ? "Edit signature" : `New ${form.kind === "org" ? "shared" : "personal"} signature`}</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div>
                        <Label>Signature name</Label>
                        <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. President closing, My default" className="rounded-xl mt-1.5" data-testid="signature-name-input" />
                    </div>
                    <div>
                        <Label>Signature content</Label>
                        <div className="mt-1.5">
                            <RichEditor value={form.body_html} onChange={(html) => setForm((f) => ({ ...f, body_html: html }))} placeholder="Type your name, title, contact info. Click the image button to add a photo or logo." minHeight={220} />
                        </div>
                        <div className="text-xs text-muted-foreground mt-1.5">Tip: drag a photo into the editor for a portrait, or paste from your clipboard.</div>
                    </div>
                </div>
                <DialogFooter><Button onClick={save} className="rounded-full bg-primary hover:bg-primary/90" data-testid="signature-save-btn">Save signature</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function BlastHistory() {
    const [items, setItems] = useState([]);
    useEffect(() => { api.get("/email/blasts").then(({ data }) => setItems(data)).catch(() => {}); }, []);
    return (
        <div className="bg-card rounded-2xl border overflow-x-auto">
            <table className="w-full text-sm">
                <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                    <tr><th className="text-left px-4 py-2.5">Sent</th><th className="text-left px-4 py-2.5">Subject</th><th className="text-left px-4 py-2.5">Segment</th><th className="text-left px-4 py-2.5">Sent</th><th className="text-left px-4 py-2.5">Failed</th><th className="text-left px-4 py-2.5">Opens</th></tr>
                </thead>
                <tbody>
                    {items.map((b) => (
                        <tr key={b.id} className="border-t border-border" data-testid={`blast-${b.id}`}>
                            <td className="px-4 py-2.5 text-muted-foreground">{b.sent_at && format(parseISO(b.sent_at), "MMM d, yyyy h:mm a")}</td>
                            <td className="px-4 py-2.5 font-medium">{b.subject}</td>
                            <td className="px-4 py-2.5 text-xs">{b.segment}{b.test_only ? " · test" : ""}</td>
                            <td className="px-4 py-2.5">{b.sent_count}</td>
                            <td className="px-4 py-2.5">{b.failed_count || 0}</td>
                            <td className="px-4 py-2.5">{b.opens || 0}</td>
                        </tr>
                    ))}
                    {items.length === 0 && <tr><td colSpan={6} className="text-center text-muted-foreground py-6">No blasts yet.</td></tr>}
                </tbody>
            </table>
        </div>
    );
}
