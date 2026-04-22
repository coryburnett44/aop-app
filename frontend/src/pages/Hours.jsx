import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Clock, Plus, Check, X, Calendar } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

export default function Hours() {
    const { user } = useAuth();
    const [tab, setTab] = useState("mine");

    if (!user) return null;
    return (
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Volunteer hours</h1>
                    <p className="text-muted-foreground mt-2">Log hours, track approvals, celebrate the work.</p>
                </div>
                <LogHoursDialog />
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1">
                    <TabsTrigger value="mine" className="rounded-full" data-testid="hours-tab-mine">My hours</TabsTrigger>
                    {user.role === "admin" && (
                        <TabsTrigger value="review" className="rounded-full" data-testid="hours-tab-review">Review queue</TabsTrigger>
                    )}
                </TabsList>
                <TabsContent value="mine" className="mt-6"><MyHours /></TabsContent>
                {user.role === "admin" && (
                    <TabsContent value="review" className="mt-6"><ReviewQueue /></TabsContent>
                )}
            </Tabs>
        </div>
    );
}

function LogHoursDialog() {
    const [open, setOpen] = useState(false);
    const [hours, setHours] = useState("");
    const [description, setDescription] = useState("");
    const [date, setDate] = useState("");
    const [busy, setBusy] = useState(false);

    async function save() {
        if (!hours || !description || !date) { toast.error("Fill all fields"); return; }
        setBusy(true);
        try {
            await api.post("/hours", {
                hours: Number(hours),
                description,
                date: new Date(date).toISOString(),
            });
            toast.success("Hours logged — pending admin review");
            setOpen(false);
            setHours(""); setDescription(""); setDate("");
            window.dispatchEvent(new Event("hours-logged"));
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <Button onClick={() => setOpen(true)} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="log-hours-btn">
                <Plus className="h-4 w-4 mr-1.5" /> Log hours
            </Button>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Log volunteer hours</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div>
                        <Label>Hours</Label>
                        <Input type="number" step="0.25" value={hours} onChange={(e) => setHours(e.target.value)} placeholder="e.g. 2.5" className="rounded-xl mt-1.5" data-testid="hours-amount-input" />
                    </div>
                    <div>
                        <Label>Date</Label>
                        <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="rounded-xl mt-1.5" data-testid="hours-date-input" />
                    </div>
                    <div>
                        <Label>What did you do?</Label>
                        <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Trail cleanup at Forest Park, picked up 3 bags of trash." className="rounded-xl mt-1.5" data-testid="hours-desc-input" />
                    </div>
                    <Button onClick={save} disabled={busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="hours-submit-btn">
                        {busy ? "Saving…" : "Submit for approval"}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function MyHours() {
    const [entries, setEntries] = useState([]);

    const load = () => api.get("/me/hours").then(({ data }) => setEntries(data));
    useEffect(() => {
        load();
        const h = () => load();
        window.addEventListener("hours-logged", h);
        return () => window.removeEventListener("hours-logged", h);
    }, []);

    const approved = entries.filter((e) => e.status === "approved").reduce((s, e) => s + e.hours, 0);
    const pending = entries.filter((e) => e.status === "pending").reduce((s, e) => s + e.hours, 0);

    return (
        <div>
            <div className="grid grid-cols-3 gap-4 mb-6">
                <StatBox label="Approved" value={`${approved.toFixed(1)}h`} tint="bg-accent/40" testid="stat-approved" />
                <StatBox label="Pending" value={`${pending.toFixed(1)}h`} tint="bg-secondary/40" testid="stat-pending" />
                <StatBox label="Entries" value={entries.length} tint="bg-primary/15" testid="stat-entries" />
            </div>

            {entries.length === 0 ? (
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-3xl p-12 text-center">
                    <Clock className="h-10 w-10 mx-auto text-muted-foreground/50" />
                    <p className="mt-4 font-heading text-lg">No hours logged yet</p>
                    <p className="text-sm text-muted-foreground">Your service goes here. Log it to get it counted.</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {entries.map((h) => (
                        <div key={h.id} className="bg-card rounded-2xl border border-border p-5 flex items-start gap-4" data-testid={`hours-${h.id}`}>
                            <div className="w-12 h-12 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold">
                                {h.hours}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm leading-relaxed">{h.description}</div>
                                <div className="text-xs text-muted-foreground mt-2 flex items-center gap-3">
                                    <span><Calendar className="h-3 w-3 inline mr-1" />{h.date && format(parseISO(h.date), "MMM d, yyyy")}</span>
                                    {h.reviewed_by_name && <span>reviewed by {h.reviewed_by_name}</span>}
                                </div>
                                {h.note && <div className="text-xs italic text-muted-foreground mt-1">Note: {h.note}</div>}
                            </div>
                            <StatusBadge status={h.status} />
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function ReviewQueue() {
    const [entries, setEntries] = useState([]);
    const [filter, setFilter] = useState("pending");

    const load = () => api.get(`/hours${filter !== "all" ? `?status_filter=${filter}` : ""}`).then(({ data }) => setEntries(data));
    useEffect(() => { load(); }, [filter]);

    async function review(id, status) {
        try {
            await api.put(`/hours/${id}/review`, { status, note: "" });
            toast.success(status === "approved" ? "Approved ✅" : "Rejected");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        }
    }

    return (
        <div>
            <div className="flex gap-2 mb-4">
                {["pending", "approved", "rejected", "all"].map((s) => (
                    <button
                        key={s}
                        onClick={() => setFilter(s)}
                        className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize ${filter === s ? "bg-primary text-primary-foreground shadow-warm" : "bg-muted hover:bg-muted/70"}`}
                        data-testid={`hours-filter-${s}`}
                    >
                        {s}
                    </button>
                ))}
            </div>

            {entries.length === 0 ? (
                <div className="text-muted-foreground">Nothing in this queue.</div>
            ) : (
                <div className="space-y-3">
                    {entries.map((h) => (
                        <div key={h.id} className="bg-card rounded-2xl border border-border p-5 flex items-start gap-4" data-testid={`review-hours-${h.id}`}>
                            <div className="w-12 h-12 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold">
                                {h.hours}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium">{h.user_name}</div>
                                <div className="text-sm leading-relaxed text-muted-foreground">{h.description}</div>
                                <div className="text-xs text-muted-foreground mt-2">
                                    {h.date && format(parseISO(h.date), "MMM d, yyyy")}
                                </div>
                            </div>
                            {h.status === "pending" ? (
                                <div className="flex gap-2">
                                    <Button size="sm" onClick={() => review(h.id, "approved")} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`approve-${h.id}`}>
                                        <Check className="h-4 w-4 mr-1" /> Approve
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => review(h.id, "rejected")} className="rounded-full" data-testid={`reject-${h.id}`}>
                                        <X className="h-4 w-4 mr-1" /> Reject
                                    </Button>
                                </div>
                            ) : (
                                <StatusBadge status={h.status} />
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function StatBox({ label, value, tint, testid }) {
    return (
        <div className={`rounded-2xl p-5 border border-border ${tint}`} data-testid={testid}>
            <div className="text-xs uppercase tracking-wider font-semibold">{label}</div>
            <div className="font-heading text-3xl font-black mt-1">{value}</div>
        </div>
    );
}

function StatusBadge({ status }) {
    const map = {
        pending: "bg-secondary/40 text-[hsl(34_8%_16%)]",
        approved: "bg-accent/40 text-[hsl(34_8%_16%)]",
        rejected: "bg-destructive/15 text-destructive",
    };
    return (
        <span className={`text-xs uppercase tracking-wider font-semibold rounded-full px-3 py-1 ${map[status] || "bg-muted"}`}>
            {status}
        </span>
    );
}
