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
import { Clock, Plus, Check, X, Calendar, Building2, User as UserIcon, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { formatCalendarDay } from "../lib/dateUtil";

export default function Hours() {
    const { user } = useAuth();
    const [tab, setTab] = useState("mine");

    if (!user) return null;
    // Iter 122: Only Full Access + Operations Manager admins can review /
    // log hours on behalf of others. Governor Manager and Membership
    // Manager see the same "My hours"-only view as regular members.
    const canManageOthers = user.role === "admin" && ["full", "operations_manager"].includes(user.admin_role || "full");
    return (
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Volunteer hours</h1>
                    <p className="text-muted-foreground mt-2">Log hours, track approvals, celebrate the work.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {canManageOthers && <CsvImportDialog />}
                    <LogHoursDialog />
                </div>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1">
                    <TabsTrigger value="mine" className="rounded-full" data-testid="hours-tab-mine">My hours</TabsTrigger>
                    {canManageOthers && (
                        <TabsTrigger value="review" className="rounded-full" data-testid="hours-tab-review">Review queue</TabsTrigger>
                    )}
                </TabsList>
                <TabsContent value="mine" className="mt-6"><MyHours /></TabsContent>
                {canManageOthers && (
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
    // Iter 122: only Full Access + Operations Manager admins can log hours
    // for OTHER members. Governor Manager and Membership Manager can only
    // log for themselves — the toggle is hidden for them and the dialog
    // is forced into personal-entry mode.
    const _adminRole = user?.admin_role || "full";
    const canManageOthers = isAdmin && ["full", "operations_manager"].includes(_adminRole);
    const [logForMyself, setLogForMyself] = useState(!canManageOthers);
    const inAdminMode = canManageOthers && !logForMyself;
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

    // Admins in "log for others" mode need a roster to pick the target
    // member. Load lazily when the dialog opens so we don't fetch on every
    // page mount. Skip the fetch when the admin is logging for themselves.
    useEffect(() => {
        if (!open || !inAdminMode || members.length) return;
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
    }, [open, inAdminMode, members.length]);

    function emptyForm() {
        return {
            hours: "", date: "", event_type: "aop_related", agency_name: "",
            activity: "", host_name: "", host_email: "", host_phone: "",
        };
    }

    async function save(e) {
        if (e) e.preventDefault();
        if (inAdminMode) {
            // Admins logging for others: only hours + date + ≥1 member are
            // required. Everything else optional.
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
                // Submit the calendar day exactly as the volunteer picked it. The HTML
                // date input gives us "YYYY-MM-DD" with no time, and `new Date(s)` parses
                // it as UTC midnight, which displays as the previous day in any
                // western-hemisphere timezone. Appending "T00:00:00" forces the parser to
                // treat the value as **local** midnight — matches the edit dialog's
                // behavior (which is why the user-reported "edit → save fixes the day"
                // workaround works).
                date: new Date(`${form.date}T00:00:00`).toISOString(),
                event_type: form.event_type,
                agency_name: form.agency_name,
                activity: form.activity,
                description: form.activity,
                host_name: form.host_name,
                host_email: form.host_email,
                host_phone: form.host_phone,
            };
            if (inAdminMode) {
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
                // Member flow (also used by admins who chose "Log for myself").
                await api.post("/hours", payload);
                toast.success(isAdmin ? "Hours logged for you — pending review" : "Hours logged — pending admin review");
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

    const filteredMembers = inAdminMode && memberQuery.trim()
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
                        {inAdminMode ? "Log volunteer hours for members" : "Log volunteer hours"}
                    </DialogTitle>
                </DialogHeader>
                <form onSubmit={save} className="space-y-4 mt-2" data-testid="log-hours-form">
                    {isAdmin && canManageOthers && (
                        <div className="flex items-center gap-2 rounded-2xl border border-border bg-muted/40 p-2.5" data-testid="hours-log-mode-switch">
                            <button
                                type="button"
                                onClick={() => setLogForMyself(false)}
                                className={`flex-1 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${!logForMyself ? "bg-primary text-white shadow-warm" : "text-muted-foreground hover:bg-muted"}`}
                                data-testid="hours-log-mode-others"
                            >
                                Log for others
                            </button>
                            <button
                                type="button"
                                onClick={() => setLogForMyself(true)}
                                className={`flex-1 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${logForMyself ? "bg-primary text-white shadow-warm" : "text-muted-foreground hover:bg-muted"}`}
                                data-testid="hours-log-mode-myself"
                            >
                                Log for myself
                            </button>
                        </div>
                    )}
                    {inAdminMode && (
                        <div className="bg-primary/5 border border-primary/20 rounded-2xl p-3 text-xs text-foreground/80 leading-relaxed" data-testid="hours-admin-banner">
                            <strong className="text-primary">Admin mode:</strong> only Members, Hours, and Date are required. Pick one or many members — the entry will be auto-approved for each.
                        </div>
                    )}
                    {isAdmin && logForMyself && canManageOthers && (
                        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-3 text-xs text-emerald-900 leading-relaxed" data-testid="hours-self-banner">
                            <strong>Personal entry:</strong> logging hours for yourself. Same required fields as any member — the entry will go into the review queue for a Full Access admin to approve.
                        </div>
                    )}
                    {inAdminMode && (
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
                        <Label>Event type {!inAdminMode && "*"}</Label>
                        <Select value={form.event_type} onValueChange={(v) => set("event_type", v)}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="hours-event-type">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="aop_related">AOP-related event</SelectItem>
                                <SelectItem value="trendsetters_spirits">Trendsetters Spirits Event</SelectItem>
                                <SelectItem value="other">Other organization / personal</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Agency / Organization name {!inAdminMode && "*"}</Label>
                        <Input required={!inAdminMode} value={form.agency_name} onChange={(e) => set("agency_name", e.target.value)} placeholder="e.g. Wounded Warrior Project" className="rounded-xl mt-1.5" data-testid="hours-agency-input" />
                    </div>
                    <div>
                        <Label>What did {inAdminMode && selectedIds.length > 1 ? "they" : "you"} do? {!inAdminMode && "*"}</Label>
                        <Textarea required={!inAdminMode} rows={3} value={form.activity} onChange={(e) => set("activity", e.target.value)} placeholder="Trail cleanup at Forest Park, picked up 3 bags of trash." className="rounded-xl mt-1.5" data-testid="hours-activity-input" />
                    </div>
                    <div className="border-t pt-3">
                        <Label className="text-xs uppercase tracking-wider text-muted-foreground">Host / Point of contact {!inAdminMode && "*"}</Label>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-1.5">
                            <Input required={!inAdminMode} value={form.host_name} onChange={(e) => set("host_name", e.target.value)} placeholder={inAdminMode ? "Host name" : "Host name *"} className="rounded-xl" data-testid="hours-host-name-input" />
                            <Input required={!inAdminMode} type="email" value={form.host_email} onChange={(e) => set("host_email", e.target.value)} placeholder={inAdminMode ? "Host email" : "Host email *"} className="rounded-xl" data-testid="hours-host-email-input" />
                            <Input required={!inAdminMode} value={form.host_phone} onChange={(e) => set("host_phone", e.target.value)} placeholder={inAdminMode ? "Host phone" : "Host phone *"} className="rounded-xl" data-testid="hours-host-phone-input" />
                        </div>
                    </div>
                    <Button type="submit" disabled={busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="hours-submit-btn">
                        {busy
                            ? "Saving…"
                            : inAdminMode
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
    const [preview, setPreview] = useState(null); // dry-run response
    const [previewing, setPreviewing] = useState(false);
    const [importing, setImporting] = useState(false);
    const [result, setResult] = useState(null); // final import response
    const [errorBanner, setErrorBanner] = useState("");

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

    async function runPreview(f) {
        if (!f) return;
        setPreviewing(true);
        setPreview(null);
        setResult(null);
        setErrorBanner("");
        try {
            const fd = new FormData();
            fd.append("file", f);
            const { data } = await api.post("/hours/admin/csv?dry_run=true", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setPreview(data);
        } catch (err) {
            setErrorBanner(err.response?.data?.detail || "Could not preview CSV");
        }
        setPreviewing(false);
    }

    async function confirmImport() {
        if (!file) return;
        if (!preview || preview.ready === 0) { toast.error("Nothing ready to import"); return; }
        setImporting(true);
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
            toast.error(err.response?.data?.detail || "Import failed");
        }
        setImporting(false);
    }

    function reset() {
        setFile(null);
        setPreview(null);
        setResult(null);
        setErrorBanner("");
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
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">Bulk import hours from CSV</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 mt-2" data-testid="hours-csv-form">
                    <div className="bg-primary/5 border border-primary/20 rounded-2xl p-3 text-xs leading-relaxed">
                        <div className="font-bold text-primary mb-1">CSV format</div>
                        <div className="text-foreground/80">
                            <strong>Member identifier (one per row):</strong> <code>member_email</code> (preferred) <em>or</em> <code>full_name</code> <em>or</em> both <code>first_name</code>+<code>last_name</code>. Use a name when the on-file email doesn&apos;t match what the member uses today.
                        </div>
                        <div className="text-foreground/80 mt-1">
                            <strong>Other required:</strong> <code>hours</code>, <code>date</code>.
                            Optional: <code>activity</code>, <code>event_type</code>, <code>agency_name</code>,
                            <code>host_name</code>, <code>host_email</code>, <code>host_phone</code>.
                            Every imported row is <strong>auto-approved</strong>. Max 1,000 rows / 1&nbsp;MB.
                        </div>
                        <div className="text-foreground/80 mt-1.5">
                            <strong>Date formats accepted:</strong> <code>YYYY-MM-DD</code> (e.g. 2026-06-15), <code>MM/DD/YYYY</code> (Excel default), <code>M/D/YY</code>, <code>15-Jun-2026</code>.
                        </div>
                        <div className="text-foreground/80 mt-1.5 italic">
                            If two members share the same name, that row will be flagged so you can add an email to disambiguate.
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
                    {!result && (
                        <div>
                            <Label>CSV file</Label>
                            <Input
                                type="file"
                                accept=".csv,text/csv"
                                onChange={(e) => {
                                    const f = e.target.files?.[0] || null;
                                    setFile(f);
                                    setPreview(null);
                                    setResult(null);
                                    setErrorBanner("");
                                    if (f) runPreview(f);
                                }}
                                className="rounded-xl mt-1.5"
                                data-testid="hours-csv-file-input"
                            />
                            {file && <div className="text-xs text-muted-foreground mt-1.5">Selected: <span className="font-mono">{file.name}</span> ({(file.size / 1024).toFixed(1)} KB){previewing && " — analyzing…"}</div>}
                        </div>
                    )}

                    {errorBanner && (
                        <div className="rounded-2xl border border-red-300 bg-red-50 text-red-800 text-sm p-3" data-testid="hours-csv-error-banner">
                            {errorBanner}
                        </div>
                    )}

                    {preview && !result && (
                        <div className="space-y-3" data-testid="hours-csv-preview">
                            <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-3 text-sm">
                                <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Dry-run preview</span>
                                <span className="text-green-700 font-bold" data-testid="hours-csv-preview-ready">✅ {preview.ready} ready</span>
                                {preview.failed > 0 && <span className="text-red-700 font-bold" data-testid="hours-csv-preview-failed">⚠ {preview.failed} error{preview.failed === 1 ? "" : "s"}</span>}
                                <span className="text-muted-foreground text-xs">of {preview.total} row{preview.total === 1 ? "" : "s"}</span>
                            </div>
                            <div className="rounded-2xl border border-border bg-card overflow-hidden">
                                <div className="max-h-80 overflow-auto" data-testid="hours-csv-preview-table">
                                    <table className="w-full text-xs">
                                        <thead className="bg-muted/50 text-[10px] uppercase tracking-wider sticky top-0 z-10">
                                            <tr>
                                                <th className="px-3 py-2 text-left font-bold w-12">Row</th>
                                                <th className="px-3 py-2 text-left font-bold">Status</th>
                                                <th className="px-3 py-2 text-left font-bold">Member</th>
                                                <th className="px-3 py-2 text-left font-bold w-16">Hrs</th>
                                                <th className="px-3 py-2 text-left font-bold w-28">Date</th>
                                                <th className="px-3 py-2 text-left font-bold">Activity / Error</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {preview.preview.map((p) => (
                                                <tr
                                                    key={p.row}
                                                    className={`border-t border-border ${p.status === "error" ? "bg-red-50/60" : "bg-card"}`}
                                                    data-testid={`hours-csv-preview-row-${p.row}`}
                                                >
                                                    <td className="px-3 py-1.5 font-mono text-muted-foreground">{p.row}</td>
                                                    <td className="px-3 py-1.5">
                                                        {p.status === "ready" ? (
                                                            <span className="inline-block text-[10px] font-bold uppercase tracking-wider rounded-full px-2 py-0.5 bg-green-100 text-green-700">Ready</span>
                                                        ) : (
                                                            <span className="inline-block text-[10px] font-bold uppercase tracking-wider rounded-full px-2 py-0.5 bg-red-100 text-red-700">Error</span>
                                                        )}
                                                    </td>
                                                    <td className="px-3 py-1.5">
                                                        <div className="font-semibold truncate max-w-[180px]">{p.member_name || <span className="italic text-muted-foreground">unresolved</span>}</div>
                                                        <div className="text-[11px] text-muted-foreground truncate max-w-[180px]">{p.email}</div>
                                                    </td>
                                                    <td className="px-3 py-1.5 font-mono">{p.hours || "—"}</td>
                                                    <td className="px-3 py-1.5 font-mono">{p.date || "—"}</td>
                                                    <td className="px-3 py-1.5">
                                                        {p.status === "error" ? (
                                                            <span className="text-red-700">{p.message}</span>
                                                        ) : (
                                                            <span className="text-foreground/90 truncate block max-w-[260px]">{p.activity}</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                                {preview.preview_truncated && (
                                    <div className="px-3 py-2 text-[11px] text-muted-foreground bg-muted/30 border-t border-border">
                                        Showing first 200 rows. Confirming the import will still process every row in the file.
                                    </div>
                                )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 pt-1">
                                <Button
                                    type="button"
                                    onClick={confirmImport}
                                    disabled={importing || preview.ready === 0}
                                    className="rounded-full bg-primary hover:bg-primary/90 flex-1 min-w-[200px]"
                                    data-testid="hours-csv-confirm-btn"
                                >
                                    {importing ? "Importing…" : `Confirm import (${preview.ready} row${preview.ready === 1 ? "" : "s"})`}
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={reset}
                                    disabled={importing}
                                    className="rounded-full"
                                    data-testid="hours-csv-reset-btn"
                                >
                                    Choose different file
                                </Button>
                            </div>
                            {preview.ready === 0 && (
                                <div className="text-xs text-red-700 italic">No rows are ready to import. Fix the errors above and re-upload.</div>
                            )}
                        </div>
                    )}

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
                            <Button type="button" onClick={reset} variant="outline" className="rounded-full mt-3" data-testid="hours-csv-import-another">
                                Import another file
                            </Button>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}

function MyHours() {
    const [entries, setEntries] = useState([]);
    const now = new Date();
    // year is "all" or a stringified 4-digit year. We keep it as a string to
    // simplify the Select binding and the URL-param logic below.
    const [year, setYear] = useState(String(now.getFullYear()));
    const [period, setPeriod] = useState("all"); // all | q1..q4 | m1..m12

    const load = () => {
        const params = new URLSearchParams();
        // "all" → omit year filter entirely so the backend returns every
        // submission in the member's history. Period filters are ignored when
        // year is "all" because Q1/Jan only make sense within a single year.
        if (year !== "all") {
            params.set("year", year);
            if (period.startsWith("q")) params.set("quarter", period.slice(1));
            else if (period.startsWith("m")) params.set("month", period.slice(1));
        }
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

    // Year options: from 2017 back to current year (matches Reports + Transactions).
    const _cy = now.getFullYear();
    const years = [];
    for (let y = _cy; y >= 2017; y--) years.push(y);
    const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    return (
        <div>
            {/* Period filters */}
            <div className="mb-5 bg-muted/30 rounded-2xl p-4 border border-border" data-testid="my-hours-filters">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                    <div className="flex items-center gap-2">
                        <Label className="text-xs uppercase tracking-wider font-bold text-muted-foreground">Year</Label>
                        <Select value={year} onValueChange={setYear}>
                            <SelectTrigger className="rounded-full h-9 w-32 text-sm" data-testid="my-hours-year"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all" data-testid="my-hours-year-all">All years</SelectItem>
                                {years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                        <Label className="text-xs uppercase tracking-wider font-bold text-muted-foreground shrink-0">Period</Label>
                        <Select value={period} onValueChange={setPeriod} disabled={year === "all"}>
                            <SelectTrigger className="rounded-full h-9 text-sm flex-1" data-testid="my-hours-period"><SelectValue placeholder={year === "all" ? "—" : ""} /></SelectTrigger>
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
                    {entries.map((h) => (
                        <HoursCard key={h.id} h={h}>
                            <MyHoursActions h={h} onDeleted={load} />
                        </HoursCard>
                    ))}
                </div>
            )}
        </div>
    );
}

/**
 * Per-row actions on the member's own Hours list — status badge + a Delete
 * button. Members can remove any of their own submissions (pending, approved,
 * or rejected) — the backend `DELETE /hours/{id}` already enforces that the
 * caller owns the record. We surface an extra confirmation step on approved
 * entries since deleting an approved record means giving up credited hours.
 */
function MyHoursActions({ h, onDeleted }) {
    async function del() {
        const dateLabel = h.date ? formatCalendarDay(h.date, "MMM d, yyyy") : "this entry";
        const msg = h.status === "approved"
            ? `Permanently delete your APPROVED ${h.hours}h entry on ${dateLabel}?\n\nThese hours will be removed from your record. This cannot be undone.`
            : `Delete your ${h.hours}h entry on ${dateLabel}?\n\nThis cannot be undone.`;
        if (!confirm(msg)) return;
        try {
            await api.delete(`/hours/${h.id}`);
            toast.success("Hours entry deleted");
            onDeleted();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not delete");
        }
    }
    return (
        <div className="flex flex-col items-end gap-1.5 shrink-0">
            <StatusBadge status={h.status} />
            <button
                type="button"
                onClick={del}
                className="text-[11px] text-destructive hover:underline font-semibold inline-flex items-center gap-1"
                data-testid={`my-hours-delete-${h.id}`}
                title={h.status === "approved" ? "Delete this approved entry (cannot be undone)" : "Delete this entry"}
            >
                <Trash2 className="h-3 w-3" />Delete
            </button>
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
                    <span><Calendar className="h-3 w-3 inline mr-1" />{h.date && formatCalendarDay(h.date, "MMM d, yyyy")}</span>
                    <span className={`uppercase tracking-wider font-semibold rounded-full px-2 py-0.5 ${h.event_type === "aop_related" ? "bg-primary/15 text-primary" : h.event_type === "trendsetters_spirits" ? "bg-secondary/20 text-secondary-foreground" : "bg-muted"}`}>
                        {h.event_type === "aop_related" ? "AOP event" : h.event_type === "trendsetters_spirits" ? "Trendsetters Spirits" : "Other"}
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

    async function remove(h) {
        if (!confirm(`Permanently remove ${h.hours} hour${h.hours === 1 ? "" : "s"} from ${h.user_name}? This cannot be undone.`)) return;
        try {
            await api.delete(`/hours/${h.id}`);
            toast.success("Hours removed");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not remove");
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
                            <AdminHoursActions h={h} onReview={review} onRemove={remove} onSaved={load} />
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
function AdminHoursActions({ h, onReview, onRemove, onSaved }) {
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
                {!editing && <FullEditHoursDialog h={h} onSaved={onSaved} />}
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
            {onRemove && !editing && (
                <button
                    type="button"
                    onClick={() => onRemove(h)}
                    className="text-[11px] text-destructive hover:underline font-semibold"
                    data-testid={`remove-hours-${h.id}`}
                    title="Permanently delete this entry"
                >
                    🗑 Remove
                </button>
            )}
            {h.hours_adjusted_by_name && (
                <div className="text-[10px] text-muted-foreground italic">adjusted by {h.hours_adjusted_by_name}</div>
            )}
        </div>
    );
}


/**
 * Full-edit dialog — admins can update every field on an existing hours
 * record (activity, agency, host details, event type, hours, date, status,
 * description, note). Posts to `PUT /api/hours/{id}` which writes only the
 * fields that actually changed and stamps the appropriate audit columns.
 */
export function FullEditHoursDialog({ h, onSaved, trigger }) {
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const [form, setForm] = useState({});

    useEffect(() => {
        if (!open) return;
        const d = h.date ? h.date.slice(0, 10) : "";
        setForm({
            activity: h.activity || "",
            description: h.description || "",
            event_type: h.event_type || "other",
            agency_name: h.agency_name || "",
            host_name: h.host_name || "",
            host_email: h.host_email || "",
            host_phone: h.host_phone || "",
            hours: String(h.hours ?? ""),
            date: d,
            status: h.status || "pending",
            note: h.note || "",
        });
    }, [open, h]);

    function set(field, value) {
        setForm((prev) => ({ ...prev, [field]: value }));
    }

    async function save() {
        const hoursNum = Number(form.hours);
        if (!hoursNum || hoursNum <= 0 || hoursNum > 1000) {
            toast.error("Hours must be between 0 and 1000");
            return;
        }
        if (!form.activity || form.activity.trim().length < 2) {
            toast.error("Activity is required (min 2 chars)");
            return;
        }
        setBusy(true);
        try {
            const payload = {
                activity: form.activity.trim(),
                description: form.description.trim(),
                event_type: form.event_type,
                agency_name: form.agency_name.trim(),
                host_name: form.host_name.trim(),
                host_email: form.host_email.trim(),
                host_phone: form.host_phone.trim(),
                hours: hoursNum,
                status: form.status,
                note: form.note.trim(),
            };
            if (form.date) {
                payload.date = new Date(`${form.date}T00:00:00`).toISOString();
            }
            await api.put(`/hours/${h.id}`, payload);
            toast.success("Hours entry updated");
            setOpen(false);
            if (onSaved) await onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not save");
        } finally {
            setBusy(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            {trigger ? (
                <span onClick={() => setOpen(true)} style={{ display: "inline-flex" }}>{trigger}</span>
            ) : (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="text-[11px] text-primary hover:underline font-semibold"
                    data-testid={`edit-all-${h.id}`}
                    title="Edit every field on this entry"
                >
                    ⚙ Edit all
                </button>
            )}
            <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto" data-testid={`edit-all-dialog-${h.id}`}>
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">Edit hours entry</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 mt-2">
                    {h.user_name && (
                        <div className="rounded-xl bg-muted/40 p-3 text-sm">
                            <span className="text-muted-foreground">Member: </span>
                            <span className="font-semibold">{h.user_name}</span>
                        </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Hours *</Label>
                            <Input
                                type="number"
                                min="0"
                                max="1000"
                                step="0.25"
                                value={form.hours || ""}
                                onChange={(e) => set("hours", e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid={`edit-all-hours-${h.id}`}
                            />
                        </div>
                        <div>
                            <Label>Date *</Label>
                            <Input
                                type="date"
                                value={form.date || ""}
                                onChange={(e) => set("date", e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid={`edit-all-date-${h.id}`}
                            />
                        </div>
                    </div>
                    <div>
                        <Label>Activity *</Label>
                        <Input
                            value={form.activity || ""}
                            onChange={(e) => set("activity", e.target.value)}
                            className="rounded-xl mt-1.5"
                            data-testid={`edit-all-activity-${h.id}`}
                        />
                    </div>
                    <div>
                        <Label>Description</Label>
                        <Textarea
                            rows={2}
                            value={form.description || ""}
                            onChange={(e) => set("description", e.target.value)}
                            className="rounded-xl mt-1.5"
                            data-testid={`edit-all-description-${h.id}`}
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Event type *</Label>
                            <Select value={form.event_type || "other"} onValueChange={(v) => set("event_type", v)}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid={`edit-all-event-type-${h.id}`}>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="aop_related">AOP event</SelectItem>
                                    <SelectItem value="trendsetters_spirits">Trendsetters Spirits</SelectItem>
                                    <SelectItem value="other">Other</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Status</Label>
                            <Select value={form.status || "pending"} onValueChange={(v) => set("status", v)}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid={`edit-all-status-${h.id}`}>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="pending">Pending</SelectItem>
                                    <SelectItem value="approved">Approved</SelectItem>
                                    <SelectItem value="rejected">Rejected</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div>
                        <Label>Agency / organization</Label>
                        <Input
                            value={form.agency_name || ""}
                            onChange={(e) => set("agency_name", e.target.value)}
                            className="rounded-xl mt-1.5"
                            data-testid={`edit-all-agency-${h.id}`}
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Host name</Label>
                            <Input
                                value={form.host_name || ""}
                                onChange={(e) => set("host_name", e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid={`edit-all-host-name-${h.id}`}
                            />
                        </div>
                        <div>
                            <Label>Host phone</Label>
                            <Input
                                value={form.host_phone || ""}
                                onChange={(e) => set("host_phone", e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid={`edit-all-host-phone-${h.id}`}
                            />
                        </div>
                    </div>
                    <div>
                        <Label>Host email</Label>
                        <Input
                            type="email"
                            value={form.host_email || ""}
                            onChange={(e) => set("host_email", e.target.value)}
                            className="rounded-xl mt-1.5"
                            data-testid={`edit-all-host-email-${h.id}`}
                        />
                    </div>
                    <div>
                        <Label>Admin note <span className="text-xs text-muted-foreground font-normal">(visible to admins only)</span></Label>
                        <Textarea
                            rows={2}
                            value={form.note || ""}
                            onChange={(e) => set("note", e.target.value)}
                            className="rounded-xl mt-1.5"
                            data-testid={`edit-all-note-${h.id}`}
                        />
                    </div>
                </div>
                <div className="flex justify-end gap-2 mt-4">
                    <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Cancel</Button>
                    <Button
                        onClick={save}
                        disabled={busy}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid={`edit-all-save-${h.id}`}
                    >
                        {busy ? "Saving…" : "Save changes"}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
