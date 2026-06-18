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
import { Clock, Plus, Check, X, Calendar, Building2, User as UserIcon } from "lucide-react";
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
                <div className="flex flex-wrap items-center gap-2">
                    {user.role === "admin" && <CsvImportDialog />}
                    <LogHoursDialog />
                </div>
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
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    const [open, setOpen] = useState(false);
    const [members, setMembers] = useState([]);
    const [memberQuery, setMemberQuery] = useState("");
    const [selectedIds, setSelectedIds] = useState([]);
    const [form, setForm] = useState({
        hours: "",
        date: "",
        event_type: "aop_related",
        agency_name: "",
        activity: "",
        host_name: "",
        host_email: "",
        host_phone: "",
    });
    const [busy, setBusy] = useState(false);

    function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }
    function toggleMember(id) {
        setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
    }

    // Admins need a roster to pick the target member. Load lazily when the
    // dialog opens so we don't fetch on every page mount.
    useEffect(() => {
        if (!open || !isAdmin || members.length) return;
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
    }, [open, isAdmin, members.length]);

    function emptyForm() {
        return {
            hours: "", date: "", event_type: "aop_related", agency_name: "",
            activity: "", host_name: "", host_email: "", host_phone: "",
        };
    }

    async function save(e) {
        if (e) e.preventDefault();
        if (isAdmin) {
            // Admins: only hours + date + ≥1 member are required. Everything else optional.
            if (!form.hours || !form.date || selectedIds.length === 0) {
                toast.error("Pick at least one member and enter hours + date");
                return;
            }
        } else if (!form.hours || !form.date || !form.activity.trim() || !form.agency_name.trim() || !form.host_name.trim() || !form.host_email.trim() || !form.host_phone.trim()) {
            toast.error("Every field is required");
            return;
        }
        setBusy(true);
        try {
            const payload = {
                hours: Number(form.hours),
                date: new Date(form.date).toISOString(),
                event_type: form.event_type,
                agency_name: form.agency_name,
                activity: form.activity,
                description: form.activity,
                host_name: form.host_name,
                host_email: form.host_email,
                host_phone: form.host_phone,
            };
            if (isAdmin) {
                if (selectedIds.length > 1) {
                    payload.user_ids = selectedIds;
                    const { data } = await api.post("/hours/admin/bulk", payload);
                    if (data.failed > 0) {
                        toast.success(`Logged ${data.created} of ${data.total} members (${data.failed} skipped)`);
                    } else {
                        toast.success(`Hours logged for ${data.created} members ✅`);
                    }
                } else {
                    payload.user_id = selectedIds[0];
                    await api.post("/hours/admin", payload);
                    toast.success("Hours logged & approved");
                }
            } else {
                await api.post("/hours", payload);
                toast.success("Hours logged — pending admin review");
            }
            setOpen(false);
            setForm(emptyForm());
            setSelectedIds([]);
            setMemberQuery("");
            window.dispatchEvent(new Event("hours-logged"));
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        }
        setBusy(false);
    }

    const filteredMembers = isAdmin && memberQuery.trim()
        ? members.filter((m) => {
            const q = memberQuery.trim().toLowerCase();
            return (m.name || "").toLowerCase().includes(q) || (m.email || "").toLowerCase().includes(q);
        })
        : members;

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <Button onClick={() => setOpen(true)} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="log-hours-btn">
                <Plus className="h-4 w-4 mr-1.5" /> Log hours
            </Button>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">
                        {isAdmin ? "Log volunteer hours for members" : "Log volunteer hours"}
                    </DialogTitle>
                </DialogHeader>
                <form onSubmit={save} className="space-y-4 mt-2" data-testid="log-hours-form">
                    {isAdmin && (
                        <div className="bg-primary/5 border border-primary/20 rounded-2xl p-3 text-xs text-foreground/80 leading-relaxed" data-testid="hours-admin-banner">
                            <strong className="text-primary">Admin mode:</strong> only Members, Hours, and Date are required. Pick one or many members — the entry will be auto-approved for each.
                        </div>
                    )}
                    {isAdmin && (
                        <div>
                            <Label>Members * <span className="text-xs font-normal text-muted-foreground">({selectedIds.length} selected)</span></Label>
                            <Input
                                placeholder="Search members by name or email…"
                                value={memberQuery}
                                onChange={(e) => setMemberQuery(e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid="hours-admin-member-search"
                            />
                            {selectedIds.length > 0 && (
                                <div className="mt-2 flex items-center justify-between text-xs">
                                    <span className="text-muted-foreground" data-testid="hours-admin-selected-summary">
                                        {selectedIds.length} member{selectedIds.length === 1 ? "" : "s"} selected
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => setSelectedIds([])}
                                        className="text-primary font-semibold hover:underline"
                                        data-testid="hours-admin-clear-selected"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                            <div className="mt-1.5 max-h-48 overflow-y-auto rounded-xl border border-border bg-card divide-y divide-border" data-testid="hours-admin-member-list">
                                {filteredMembers.length === 0 ? (
                                    <div className="px-3 py-4 text-xs text-muted-foreground italic">No members match.</div>
                                ) : (
                                    filteredMembers.map((m) => {
                                        const checked = selectedIds.includes(m.id);
                                        return (
                                            <label
                                                key={m.id}
                                                className={`flex items-center gap-2 px-3 py-2 cursor-pointer text-sm hover:bg-muted/40 ${checked ? "bg-primary/5" : ""}`}
                                                data-testid={`hours-admin-member-row-${m.id}`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={checked}
                                                    onChange={() => toggleMember(m.id)}
                                                    className="h-4 w-4 accent-primary shrink-0"
                                                    data-testid={`hours-admin-member-checkbox-${m.id}`}
                                                />
                                                <span className="font-medium truncate">{m.name}</span>
                                                {m.email && <span className="text-xs text-muted-foreground truncate">· {m.email}</span>}
                                            </label>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Hours *</Label>
                            <Input required type="number" step="0.25" min="0.25" value={form.hours} onChange={(e) => set("hours", e.target.value)} placeholder="e.g. 2.5" className="rounded-xl mt-1.5" data-testid="hours-amount-input" />
                        </div>
                        <div>
                            <Label>Date *</Label>
                            <Input required type="date" value={form.date} onChange={(e) => set("date", e.target.value)} className="rounded-xl mt-1.5" data-testid="hours-date-input" />
                        </div>
                    </div>
                    <div>
                        <Label>Event type {!isAdmin && "*"}</Label>
                        <Select value={form.event_type} onValueChange={(v) => set("event_type", v)}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="hours-event-type">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="aop_related">AOP-related event</SelectItem>
                                <SelectItem value="other">Other organization / personal</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Agency / Organization name {!isAdmin && "*"}</Label>
                        <Input required={!isAdmin} value={form.agency_name} onChange={(e) => set("agency_name", e.target.value)} placeholder="e.g. Wounded Warrior Project" className="rounded-xl mt-1.5" data-testid="hours-agency-input" />
                    </div>
                    <div>
                        <Label>What did {isAdmin && selectedIds.length > 1 ? "they" : "you"} do? {!isAdmin && "*"}</Label>
                        <Textarea required={!isAdmin} rows={3} value={form.activity} onChange={(e) => set("activity", e.target.value)} placeholder="Trail cleanup at Forest Park, picked up 3 bags of trash." className="rounded-xl mt-1.5" data-testid="hours-activity-input" />
                    </div>
                    <div className="border-t pt-3">
                        <Label className="text-xs uppercase tracking-wider text-muted-foreground">Host / Point of contact {!isAdmin && "*"}</Label>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-1.5">
                            <Input required={!isAdmin} value={form.host_name} onChange={(e) => set("host_name", e.target.value)} placeholder={isAdmin ? "Host name" : "Host name *"} className="rounded-xl" data-testid="hours-host-name-input" />
                            <Input required={!isAdmin} type="email" value={form.host_email} onChange={(e) => set("host_email", e.target.value)} placeholder={isAdmin ? "Host email" : "Host email *"} className="rounded-xl" data-testid="hours-host-email-input" />
                            <Input required={!isAdmin} value={form.host_phone} onChange={(e) => set("host_phone", e.target.value)} placeholder={isAdmin ? "Host phone" : "Host phone *"} className="rounded-xl" data-testid="hours-host-phone-input" />
                        </div>
                    </div>
                    <Button type="submit" disabled={busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="hours-submit-btn">
                        {busy
                            ? "Saving…"
                            : isAdmin
                                ? (selectedIds.length > 1
                                    ? `Log hours for ${selectedIds.length} members (auto-approved)`
                                    : "Log hours (auto-approved)")
                                : "Submit for approval"}
                    </Button>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function CsvImportDialog() {
    const [open, setOpen] = useState(false);
    const [file, setFile] = useState(null);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    async function downloadTemplate() {
        try {
            const { data } = await api.get("/hours/admin/csv/template", { responseType: "blob" });
            const url = URL.createObjectURL(data);
            const a = document.createElement("a");
            a.href = url;
            a.download = "aop-hours-template.csv";
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) { toast.error("Couldn't download template"); }
    }

    async function upload(e) {
        e.preventDefault();
        if (!file) { toast.error("Pick a .csv file first"); return; }
        setBusy(true);
        setResult(null);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/hours/admin/csv", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setResult(data);
            if (data.created > 0) toast.success(`Imported ${data.created} of ${data.total} rows`);
            else toast.error("No rows imported — see errors below");
            window.dispatchEvent(new Event("hours-logged"));
        } catch (err) {
            toast.error(err.response?.data?.detail || "Upload failed");
        }
        setBusy(false);
    }

    function reset() {
        setFile(null);
        setResult(null);
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
            <Button
                type="button"
                onClick={() => setOpen(true)}
                variant="outline"
                className="rounded-full border-primary text-primary hover:bg-primary hover:text-white"
                data-testid="hours-import-csv-btn"
            >
                Import CSV
            </Button>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">Bulk import hours from CSV</DialogTitle>
                </DialogHeader>
                <form onSubmit={upload} className="space-y-4 mt-2" data-testid="hours-csv-form">
                    <div className="bg-primary/5 border border-primary/20 rounded-2xl p-3 text-xs leading-relaxed">
                        <div className="font-bold text-primary mb-1">CSV format</div>
                        <div className="text-foreground/80">
                            Required columns: <code>member_email</code>, <code>hours</code>, <code>date</code>.
                            Optional: <code>activity</code>, <code>event_type</code>, <code>agency_name</code>,
                            <code>host_name</code>, <code>host_email</code>, <code>host_phone</code>.
                            Every imported row is <strong>auto-approved</strong>. Max 1,000 rows / 1&nbsp;MB.
                        </div>
                        <button
                            type="button"
                            onClick={downloadTemplate}
                            className="mt-2 text-primary font-bold hover:underline"
                            data-testid="hours-csv-download-template"
                        >
                            ⬇ Download template
                        </button>
                    </div>
                    <div>
                        <Label>CSV file</Label>
                        <Input
                            type="file"
                            accept=".csv,text/csv"
                            onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }}
                            className="rounded-xl mt-1.5"
                            data-testid="hours-csv-file-input"
                        />
                        {file && <div className="text-xs text-muted-foreground mt-1.5">Selected: <span className="font-mono">{file.name}</span> ({(file.size / 1024).toFixed(1)} KB)</div>}
                    </div>
                    <Button type="submit" disabled={busy || !file} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="hours-csv-upload-btn">
                        {busy ? "Importing…" : "Import + auto-approve"}
                    </Button>
                    {result && (
                        <div className="rounded-2xl border border-border bg-muted/30 p-3 text-sm" data-testid="hours-csv-result">
                            <div className="flex items-center gap-3 mb-2">
                                <span className="text-green-700 font-bold">✅ {result.created} imported</span>
                                {result.failed > 0 && <span className="text-red-700 font-bold">⚠ {result.failed} skipped</span>}
                                <span className="text-muted-foreground text-xs">of {result.total} row{result.total === 1 ? "" : "s"}</span>
                            </div>
                            {result.errors && result.errors.length > 0 && (
                                <div className="max-h-40 overflow-y-auto bg-card rounded-xl border border-red-200 p-2 text-xs space-y-1" data-testid="hours-csv-errors">
                                    <div className="font-bold text-red-700 uppercase text-[10px] tracking-wider">Errors</div>
                                    {result.errors.map((err, i) => (
                                        <div key={i} className="flex gap-2">
                                            <span className="font-mono text-muted-foreground shrink-0">Row {err.row}:</span>
                                            <span>{err.message}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </form>
            </DialogContent>
        </Dialog>
    );
}

function MyHours() {
    const [entries, setEntries] = useState([]);
    const now = new Date();
    const [year, setYear] = useState(now.getFullYear());
    const [period, setPeriod] = useState("all"); // all | q1..q4 | m1..m12

    const load = () => {
        const params = new URLSearchParams();
        params.set("year", year);
        if (period.startsWith("q")) params.set("quarter", period.slice(1));
        else if (period.startsWith("m")) params.set("month", period.slice(1));
        api.get(`/me/hours?${params.toString()}`).then(({ data }) => setEntries(data));
    };
    useEffect(() => {
        load();
        const h = () => load();
        window.addEventListener("hours-logged", h);
        return () => window.removeEventListener("hours-logged", h);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [year, period]);

    const approved = entries.filter((e) => e.status === "approved").reduce((s, e) => s + e.hours, 0);
    const pending = entries.filter((e) => e.status === "pending").reduce((s, e) => s + e.hours, 0);

    // Year options: current year and 4 prior
    const years = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2, now.getFullYear() - 3, now.getFullYear() - 4];
    const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    return (
        <div>
            {/* Period filters */}
            <div className="mb-5 bg-muted/30 rounded-2xl p-4 border border-border" data-testid="my-hours-filters">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                    <div className="flex items-center gap-2">
                        <Label className="text-xs uppercase tracking-wider font-bold text-muted-foreground">Year</Label>
                        <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
                            <SelectTrigger className="rounded-full h-9 w-28 text-sm" data-testid="my-hours-year"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                        <Label className="text-xs uppercase tracking-wider font-bold text-muted-foreground shrink-0">Period</Label>
                        <Select value={period} onValueChange={setPeriod}>
                            <SelectTrigger className="rounded-full h-9 text-sm flex-1" data-testid="my-hours-period"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Entire year</SelectItem>
                                <SelectItem value="q1">Q1 (Jan–Mar)</SelectItem>
                                <SelectItem value="q2">Q2 (Apr–Jun)</SelectItem>
                                <SelectItem value="q3">Q3 (Jul–Sep)</SelectItem>
                                <SelectItem value="q4">Q4 (Oct–Dec)</SelectItem>
                                {MONTH_NAMES.map((mn, i) => <SelectItem key={i + 1} value={`m${i + 1}`}>{mn}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-3 sm:gap-4 mb-6">
                <StatBox label="Approved" value={`${approved.toFixed(1)}h`} tint="bg-accent/40" testid="stat-approved" />
                <StatBox label="Pending" value={`${pending.toFixed(1)}h`} tint="bg-secondary/40" testid="stat-pending" />
                <StatBox label="Entries" value={entries.length} tint="bg-primary/15" testid="stat-entries" />
            </div>

            {entries.length === 0 ? (
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-3xl p-12 text-center" data-testid="my-hours-empty">
                    <Clock className="h-10 w-10 mx-auto text-muted-foreground/50" />
                    <p className="mt-4 font-heading text-lg">No hours in this period</p>
                    <p className="text-sm text-muted-foreground">Adjust the year/period filters, or log new hours.</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {entries.map((h) => <HoursCard key={h.id} h={h} />)}
                </div>
            )}
        </div>
    );
}

function HoursCard({ h, children }) {
    return (
        <div className="bg-card rounded-2xl border border-border p-5 flex items-start gap-4" data-testid={`hours-${h.id}`}>
            <div className="w-12 h-12 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold shrink-0">
                {h.hours}
            </div>
            <div className="flex-1 min-w-0">
                {h.user_name && <div className="text-sm font-semibold">{h.user_name}</div>}
                <div className="text-sm leading-relaxed">{h.activity || h.description}</div>
                <div className="text-xs text-muted-foreground mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span><Calendar className="h-3 w-3 inline mr-1" />{h.date && format(parseISO(h.date), "MMM d, yyyy")}</span>
                    <span className={`uppercase tracking-wider font-semibold rounded-full px-2 py-0.5 ${h.event_type === "aop_related" ? "bg-primary/15 text-primary" : "bg-muted"}`}>
                        {h.event_type === "aop_related" ? "AOP event" : "Other"}
                    </span>
                    {h.agency_name && <span className="inline-flex items-center gap-1"><Building2 className="h-3 w-3" />{h.agency_name}</span>}
                    {h.host_name && <span className="inline-flex items-center gap-1"><UserIcon className="h-3 w-3" />Host: {h.host_name}</span>}
                </div>
                {h.note && <div className="text-xs italic text-muted-foreground mt-1">Note: {h.note}</div>}
            </div>
            {children || <StatusBadge status={h.status} />}
        </div>
    );
}

function ReviewQueue() {
    const [entries, setEntries] = useState([]);
    const [filter, setFilter] = useState("pending");

    const load = () => api.get(`/hours${filter !== "all" ? `?status_filter=${filter}` : ""}`).then(({ data }) => setEntries(data));
    useEffect(() => { load(); }, [filter]);

    async function review(id, status, hours = null) {
        try {
            const payload = { status, note: "" };
            if (hours !== null) payload.hours = Number(hours);
            await api.put(`/hours/${id}/review`, payload);
            toast.success(status === "approved" ? "Approved ✅" : status === "rejected" ? "Rejected" : "Updated");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        }
    }

    return (
        <div>
            <div className="flex gap-2 mb-4 flex-wrap">
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
                        <HoursCard key={h.id} h={h}>
                            <AdminHoursActions h={h} onReview={review} />
                        </HoursCard>
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
        <span className={`text-xs uppercase tracking-wider font-semibold rounded-full px-3 py-1 shrink-0 ${map[status] || "bg-muted"}`}>
            {status}
        </span>
    );
}


/**
 * Inline editor + action buttons for the admin hours queue.
 * Admins need to (a) approve / reject pending submissions AND (b) correct the
 * recorded hours value at any time — even after approval. Members occasionally
 * over- or under-report; rather than asking them to resubmit, the admin can
 * tweak the value in place and the audit trail (hours_adjusted_by_name +
 * hours_adjusted_at) gets stamped server-side.
 */
function AdminHoursActions({ h, onReview }) {
    const [editing, setEditing] = useState(false);
    const [val, setVal] = useState(String(h.hours));

    async function save() {
        const n = Number(val);
        if (!n || n <= 0 || n > 1000) { toast.error("Enter a valid hours value (0–1000)"); return; }
        await onReview(h.id, h.status === "pending" ? "approved" : h.status, n);
        setEditing(false);
    }

    return (
        <div className="flex flex-col items-end gap-1.5 shrink-0">
            <div className="flex items-center gap-2">
                <StatusBadge status={h.status} />
                {!editing && (
                    <button
                        type="button"
                        onClick={() => { setVal(String(h.hours)); setEditing(true); }}
                        className="text-[11px] text-primary hover:underline font-semibold"
                        data-testid={`edit-hours-${h.id}`}
                    >
                        ✏️ Edit hrs
                    </button>
                )}
            </div>
            {editing && (
                <div className="flex items-center gap-1.5 bg-amber-50 border border-amber-300 rounded-full px-2 py-1">
                    <Input
                        type="number"
                        min="0"
                        max="1000"
                        step="0.25"
                        value={val}
                        onChange={(e) => setVal(e.target.value)}
                        className="h-7 w-20 text-xs rounded-full"
                        data-testid={`edit-hours-input-${h.id}`}
                        autoFocus
                    />
                    <Button size="sm" onClick={save} className="h-7 rounded-full text-xs bg-amber-600 hover:bg-amber-700 text-white px-3" data-testid={`save-hours-${h.id}`}>Save</Button>
                    <button type="button" onClick={() => setEditing(false)} className="text-[11px] text-slate-600 hover:underline">cancel</button>
                </div>
            )}
            {h.status === "pending" && !editing && (
                <div className="flex gap-2">
                    <Button size="sm" onClick={() => onReview(h.id, "approved")} className="rounded-full bg-primary hover:bg-primary/90" data-testid={`approve-${h.id}`}>
                        <Check className="h-4 w-4 mr-1" /> Approve
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => onReview(h.id, "rejected")} className="rounded-full" data-testid={`reject-${h.id}`}>
                        <X className="h-4 w-4 mr-1" /> Reject
                    </Button>
                </div>
            )}
            {h.hours_adjusted_by_name && (
                <div className="text-[10px] text-muted-foreground italic">adjusted by {h.hours_adjusted_by_name}</div>
            )}
        </div>
    );
}
