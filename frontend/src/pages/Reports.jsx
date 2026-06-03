import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Download, FileText, Filter, Printer } from "lucide-react";
import { format, parseISO } from "date-fns";

function csvify(rows, headers) {
    const escape = (v) => {
        const s = v == null ? "" : String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const head = headers.map((h) => escape(h.label)).join(",");
    const body = rows.map((r) => headers.map((h) => escape(h.get(r))).join(",")).join("\n");
    return head + "\n" + body;
}

function downloadCSV(filename, csv) {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export default function Reports() {
    return (
        <Tabs defaultValue="members">
            <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                <TabsTrigger value="members" className="rounded-full" data-testid="reports-tab-members">Members</TabsTrigger>
                <TabsTrigger value="rsvps" className="rounded-full" data-testid="reports-tab-rsvps">RSVPs</TabsTrigger>
                <TabsTrigger value="hours" className="rounded-full" data-testid="reports-tab-hours">Hours</TabsTrigger>
                <TabsTrigger value="donations" className="rounded-full" data-testid="reports-tab-donations">Donations</TabsTrigger>
                <TabsTrigger value="dues" className="rounded-full" data-testid="reports-tab-dues">Dues approvals</TabsTrigger>
                <TabsTrigger value="brief" className="rounded-full" data-testid="reports-tab-brief">Personnel Brief</TabsTrigger>
            </TabsList>
            <TabsContent value="members" className="mt-6"><MembersReport /></TabsContent>
            <TabsContent value="rsvps" className="mt-6"><RsvpsReport /></TabsContent>
            <TabsContent value="hours" className="mt-6"><HoursReport /></TabsContent>
            <TabsContent value="donations" className="mt-6"><DonationsReport /></TabsContent>
            <TabsContent value="dues" className="mt-6"><ZeffyDuesApprovals /></TabsContent>
            <TabsContent value="brief" className="mt-6"><PersonnelBriefSection /></TabsContent>
        </Tabs>
    );
}

function MembersReport() {
    const [rows, setRows] = useState([]);
    const [filters, setFilters] = useState({ status_filter: "", chapter_id: "", tier_id: "", role: "" });
    const [chapters, setChapters] = useState([]);
    const [tiers, setTiers] = useState([]);

    useEffect(() => {
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
        api.get("/tiers").then(({ data }) => setTiers(data)).catch(() => {});
    }, []);

    async function run() {
        const params = Object.fromEntries(Object.entries(filters).filter(([_, v]) => v));
        const { data } = await api.get("/reports/members", { params });
        setRows(data);
    }
    useEffect(() => { run(); }, []); // eslint-disable-line

    function exportCSV() {
        downloadCSV(`members-report-${new Date().toISOString().slice(0, 10)}.csv`, csvify(rows, [
            { label: "Name", get: (m) => m.name },
            { label: "Email", get: (m) => m.email },
            { label: "Phone", get: (m) => m.phone },
            { label: "Address", get: (m) => m.address },
            { label: "City", get: (m) => m.city },
            { label: "State", get: (m) => m.state },
            { label: "Zip", get: (m) => m.zip_code },
            { label: "Country", get: (m) => m.country },
            { label: "Status", get: (m) => m.status },
            { label: "Role", get: (m) => m.role },
            { label: "Chapter", get: (m) => chapters.find((c) => c.id === m.chapter_id)?.name || "" },
            { label: "Tier", get: (m) => m.membership_tier },
            { label: "Joined", get: (m) => (m.join_date || m.created_at)?.slice(0, 10) || "" },
            { label: "Expires", get: (m) => m.membership_expires_at?.slice(0, 10) || "" },
            { label: "Events attended (count)", get: (m) => m.events_attended_count ?? 0 },
            { label: "Events attended", get: (m) => (m.events_attended || []).map((e) => `${e.title} [${e.ticket_type || "?"}]`).join("; ") },
            { label: "Guests registered (count)", get: (m) => m.guests_registered_count ?? 0 },
            { label: "Guests registered", get: (m) => (m.guests_registered || []).map((g) => g.name).join("; ") },
        ]));
    }

    return (
        <div>
            <div className="bg-card rounded-2xl border border-border p-5 mb-4">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><Filter className="h-4 w-4" /> Filters</div>
                <div className="grid sm:grid-cols-4 gap-3">
                    <FilterSelect label="Status" value={filters.status_filter} onChange={(v) => setFilters({ ...filters, status_filter: v })} options={[
                        { value: "", label: "Any" },
                        { value: "active", label: "Active" },
                        { value: "inactive", label: "Inactive" },
                        { value: "grace", label: "Grace" },
                        { value: "expired", label: "Expired" },
                        { value: "deceased", label: "Omega" },
                    ]} testid="report-filter-status" />
                    <FilterSelect label="Chapter" value={filters.chapter_id} onChange={(v) => setFilters({ ...filters, chapter_id: v })} options={[{ value: "", label: "Any" }, ...chapters.map((c) => ({ value: c.id, label: c.name }))]} testid="report-filter-chapter" />
                    <FilterSelect label="Tier" value={filters.tier_id} onChange={(v) => setFilters({ ...filters, tier_id: v })} options={[{ value: "", label: "Any" }, ...tiers.map((t) => ({ value: t.id, label: t.name }))]} testid="report-filter-tier" />
                    <FilterSelect label="Role" value={filters.role} onChange={(v) => setFilters({ ...filters, role: v })} options={[
                        { value: "", label: "Any" },
                        { value: "member", label: "Member" },
                        { value: "admin", label: "Admin" },
                    ]} testid="report-filter-role" />
                </div>
                <div className="flex justify-end gap-2 mt-4">
                    <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="report-run-btn">Run report</Button>
                    <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="report-csv-btn"><Download className="h-4 w-4 mr-1.5" />Export CSV</Button>
                </div>
            </div>
            <div className="text-sm text-muted-foreground mb-2">{rows.length} member{rows.length !== 1 ? "s" : ""}</div>
            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                        <tr><th className="text-left px-4 py-2.5">Name</th><th className="text-left px-4 py-2.5">Email</th><th className="text-left px-4 py-2.5">Status</th><th className="text-left px-4 py-2.5">Chapter</th><th className="text-left px-4 py-2.5">Tier</th><th className="text-left px-4 py-2.5">Joined</th><th className="text-left px-4 py-2.5">Events attended</th><th className="text-left px-4 py-2.5">Guests</th></tr>
                    </thead>
                    <tbody>
                        {rows.map((m) => (
                            <tr key={m.id} className="border-t border-border align-top" data-testid={`report-row-${m.id}`}>
                                <td className="px-4 py-2.5">{m.name}</td>
                                <td className="px-4 py-2.5 text-muted-foreground">{m.email}</td>
                                <td className="px-4 py-2.5 text-xs uppercase tracking-wider font-semibold">{m.status}</td>
                                <td className="px-4 py-2.5 text-muted-foreground">{chapters.find((c) => c.id === m.chapter_id)?.name || "—"}</td>
                                <td className="px-4 py-2.5 text-muted-foreground">{m.membership_tier}</td>
                                <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">{(m.join_date || m.created_at) && format(parseISO(m.join_date || m.created_at), "MMM d, yyyy")}</td>
                                <td className="px-4 py-2.5">
                                    <div className="font-semibold">{m.events_attended_count ?? 0}</div>
                                    {(m.events_attended || []).length > 0 && (
                                        <div className="text-xs text-muted-foreground mt-0.5 leading-snug">{m.events_attended.map((e) => `${e.title}${e.ticket_type ? ` (${e.ticket_type})` : ""}`).join(", ")}</div>
                                    )}
                                </td>
                                <td className="px-4 py-2.5">
                                    <div className="font-semibold">{m.guests_registered_count ?? 0}</div>
                                    {(m.guests_registered || []).length > 0 && (
                                        <div className="text-xs text-muted-foreground mt-0.5 leading-snug">{m.guests_registered.map((g) => g.name).join(", ")}</div>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function RsvpsReport() {
    const [rows, setRows] = useState([]);
    const [events, setEvents] = useState([]);
    const [eventId, setEventId] = useState("");
    const [parentId, setParentId] = useState("");

    useEffect(() => {
        api.get("/events").then(({ data }) => setEvents(data)).catch(() => {});
    }, []);

    async function run() {
        const params = {};
        if (eventId) params.event_id = eventId;
        else if (parentId) params.parent_event_id = parentId;
        const { data } = await api.get("/reports/rsvps", { params });
        setRows(data);
    }
    useEffect(() => { run(); }, []); // eslint-disable-line

    function exportCSV() {
        downloadCSV(`rsvps-report-${new Date().toISOString().slice(0, 10)}.csv`, csvify(rows, [
            { label: "Event", get: (r) => r.event_title },
            { label: "Event date", get: (r) => r.event_start_at?.slice(0, 10) || "" },
            { label: "Member", get: (r) => r.user_name },
            { label: "RSVPed at", get: (r) => r.rsvped_at?.slice(0, 16).replace("T", " ") || "" },
            { label: "Ticket type", get: (r) => r.ticket_type || "" },
            { label: "Checked in at", get: (r) => r.checked_in_at?.slice(0, 16).replace("T", " ") || "" },
            { label: "Guest count", get: (r) => r.guest_count },
            { label: "Guests", get: (r) => (r.guests || []).map((g) => `${g.name}${g.email ? ` <${g.email}>` : ""}`).join("; ") },
        ]));
    }

    const parentCandidates = events.filter((e) => !e.parent_event_id);

    return (
        <div data-testid="rsvps-report">
            <div className="bg-card rounded-2xl border border-border p-5 mb-4">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><Filter className="h-4 w-4" /> Filters</div>
                <div className="grid sm:grid-cols-3 gap-3">
                    <FilterSelect label="Specific event" value={eventId} onChange={(v) => { setEventId(v); if (v) setParentId(""); }} options={[{ value: "", label: "Any" }, ...events.map((e) => ({ value: e.id, label: e.title }))]} testid="rsvps-filter-event" />
                    <FilterSelect label="Or parent event (all sub-events)" value={parentId} onChange={(v) => { setParentId(v); if (v) setEventId(""); }} options={[{ value: "", label: "Any" }, ...parentCandidates.map((e) => ({ value: e.id, label: e.title }))]} testid="rsvps-filter-parent" />
                </div>
                <div className="flex justify-end gap-2 mt-4">
                    <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="rsvps-report-run-btn">Run report</Button>
                    <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="rsvps-report-csv-btn"><Download className="h-4 w-4 mr-1.5" />Export CSV</Button>
                </div>
            </div>
            <div className="text-sm text-muted-foreground mb-2">
                {rows.length} RSVP{rows.length !== 1 ? "s" : ""}
                {" · "}
                {rows.reduce((acc, r) => acc + (r.guest_count || 0), 0)} guests
            </div>
            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                        <tr>
                            <th className="text-left px-4 py-2.5">Event</th>
                            <th className="text-left px-4 py-2.5">Member</th>
                            <th className="text-left px-4 py-2.5">RSVP'd</th>
                            <th className="text-left px-4 py-2.5">Ticket</th>
                            <th className="text-left px-4 py-2.5">Checked in</th>
                            <th className="text-left px-4 py-2.5">Guests</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={r.rsvp_id} className="border-t border-border align-top" data-testid={`rsvps-report-row-${r.rsvp_id}`}>
                                <td className="px-4 py-2.5">
                                    <div className="font-medium">{r.event_title}</div>
                                    {r.event_start_at && <div className="text-xs text-muted-foreground">{format(parseISO(r.event_start_at), "MMM d, yyyy")}</div>}
                                </td>
                                <td className="px-4 py-2.5">{r.user_name}</td>
                                <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap text-xs">{r.rsvped_at ? format(parseISO(r.rsvped_at), "MMM d, yyyy h:mm a") : "—"}</td>
                                <td className="px-4 py-2.5">{r.ticket_type ? <span className="text-xs uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary">{r.ticket_type.replace("_", " ")}</span> : <span className="text-xs text-muted-foreground italic">—</span>}</td>
                                <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">{r.checked_in_at ? format(parseISO(r.checked_in_at), "MMM d, h:mm a") : "—"}</td>
                                <td className="px-4 py-2.5">
                                    <div className="font-semibold">{r.guest_count}</div>
                                    {(r.guests || []).length > 0 && <div className="text-xs text-muted-foreground leading-snug">{r.guests.map((g) => g.name).join(", ")}</div>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function HoursReport() {
    const now = new Date();
    const [view, setView] = useState("entries"); // entries | by_member | by_chapter | by_period
    const [chapters, setChapters] = useState([]);
    const [year, setYear] = useState(now.getFullYear());
    const [period, setPeriod] = useState("all"); // all | q1..q4 | m1..m12
    const [chapterId, setChapterId] = useState("");
    const [eventType, setEventType] = useState("");
    const [status, setStatus] = useState("");
    const [rows, setRows] = useState([]);
    const [summary, setSummary] = useState(null);

    useEffect(() => { api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {}); }, []);

    function buildParams() {
        const p = { year };
        if (period.startsWith("q")) p.quarter = period.slice(1);
        else if (period.startsWith("m")) p.month = period.slice(1);
        if (chapterId) p.chapter_id = chapterId;
        if (eventType) p.event_type = eventType;
        if (status) p.status_filter = status;
        return p;
    }

    async function run() {
        const params = buildParams();
        if (view === "entries") {
            const { data } = await api.get("/reports/hours", { params });
            setRows(data); setSummary(null);
        } else {
            const groupBy = view === "by_member" ? "member" : view === "by_chapter" ? "chapter" : "month";
            const { data } = await api.get("/reports/hours/summary", { params: { ...params, group_by: groupBy } });
            setRows(data.rows || []); setSummary(data);
        }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        // Clear rows immediately when the view changes so we don't render stale rows
        // (which have a different shape/keys) against the new table headers.
        setRows([]);
        run();
    }, [view, year, period, chapterId, eventType, status]);

    function exportCSV() {
        let headers;
        let fname = `hours-${view}-${year}${period !== "all" ? "-" + period : ""}.csv`;
        if (view === "entries") {
            headers = [
                { label: "Member", get: (h) => h.user_name },
                { label: "Hours", get: (h) => h.hours },
                { label: "Event type", get: (h) => h.event_type },
                { label: "Agency", get: (h) => h.agency_name },
                { label: "Activity", get: (h) => h.activity || h.description },
                { label: "Host", get: (h) => h.host_name },
                { label: "Date", get: (h) => h.date?.slice(0, 10) || "" },
                { label: "Status", get: (h) => h.status },
            ];
        } else if (view === "by_member") {
            headers = [
                { label: "Member", get: (r) => r.user_name },
                { label: "Chapter", get: (r) => r.chapter_name || "Unassigned" },
                { label: "Approved hours", get: (r) => r.hours },
                { label: "Entries", get: (r) => r.count },
            ];
        } else if (view === "by_chapter") {
            headers = [
                { label: "Chapter", get: (r) => r.chapter_name },
                { label: "Approved hours", get: (r) => r.hours },
                { label: "Entries", get: (r) => r.count },
                { label: "Active members", get: (r) => r.member_count },
            ];
        } else {
            headers = [
                { label: "Period", get: (r) => r.period_label },
                { label: "Approved hours", get: (r) => r.hours },
                { label: "Entries", get: (r) => r.count },
            ];
        }
        downloadCSV(fname, csvify(rows, headers));
    }

    const years = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2, now.getFullYear() - 3, now.getFullYear() - 4];
    const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    return (
        <div data-testid="hours-report">
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><Filter className="h-4 w-4" /> Filters</div>
                <div className="grid sm:grid-cols-3 lg:grid-cols-5 gap-3">
                    <FilterSelect label="Year" value={String(year)} onChange={(v) => setYear(Number(v))} options={years.map((y) => ({ value: String(y), label: String(y) }))} testid="hours-filter-year" />
                    <div>
                        <Label className="text-xs">Period</Label>
                        <Select value={period} onValueChange={setPeriod}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="hours-filter-period"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Entire year</SelectItem>
                                <SelectItem value="q1">Q1</SelectItem>
                                <SelectItem value="q2">Q2</SelectItem>
                                <SelectItem value="q3">Q3</SelectItem>
                                <SelectItem value="q4">Q4</SelectItem>
                                {MONTH_NAMES.map((mn, i) => <SelectItem key={i + 1} value={`m${i + 1}`}>{mn}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <FilterSelect label="Chapter" value={chapterId} onChange={setChapterId} options={[{ value: "", label: "All chapters" }, ...chapters.map((c) => ({ value: c.id, label: c.name }))]} testid="hours-filter-chapter" />
                    <FilterSelect label="Status" value={status} onChange={setStatus} options={[
                        { value: "", label: "Any" }, { value: "approved", label: "Approved" }, { value: "pending", label: "Pending" }, { value: "rejected", label: "Rejected" },
                    ]} testid="hours-filter-status" />
                    <FilterSelect label="Event type" value={eventType} onChange={setEventType} options={[
                        { value: "", label: "Any" }, { value: "aop_related", label: "AOP event" }, { value: "other", label: "Other" },
                    ]} testid="hours-filter-type" />
                </div>
                <div className="flex flex-wrap justify-end gap-2 mt-4">
                    <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="hours-report-run">Run report</Button>
                    <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="hours-report-csv"><Download className="h-4 w-4 mr-1.5" />Export CSV</Button>
                </div>
            </div>

            {/* View switcher */}
            <Tabs value={view} onValueChange={setView}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="entries" className="rounded-full" data-testid="hours-view-entries">Individual entries</TabsTrigger>
                    <TabsTrigger value="by_member" className="rounded-full" data-testid="hours-view-by-member">By member</TabsTrigger>
                    <TabsTrigger value="by_chapter" className="rounded-full" data-testid="hours-view-by-chapter">By chapter</TabsTrigger>
                    <TabsTrigger value="by_period" className="rounded-full" data-testid="hours-view-by-period">By period</TabsTrigger>
                </TabsList>
            </Tabs>

            {/* Totals */}
            {summary?.totals && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4" data-testid="hours-totals">
                    <Stat label="Approved" value={`${summary.totals.approved_hours?.toFixed(1)}h`} />
                    <Stat label="Approved entries" value={summary.totals.approved_count} />
                    <Stat label="Pending" value={`${summary.totals.pending_hours?.toFixed(1)}h`} />
                    <Stat label="Rejected" value={`${summary.totals.rejected_hours?.toFixed(1)}h`} />
                </div>
            )}

            <div className="text-sm text-muted-foreground mt-4 mb-2">{rows.length} row{rows.length !== 1 ? "s" : ""}</div>

            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    {view === "entries" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Member</th><th className="text-left px-4 py-2.5">Hrs</th><th className="text-left px-4 py-2.5">Type</th><th className="text-left px-4 py-2.5">Activity</th><th className="text-left px-4 py-2.5">Date</th><th className="text-left px-4 py-2.5">Status</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((h) => (
                                    <tr key={h.id} className="border-t border-border" data-testid={`hours-report-row-${h.id}`}>
                                        <td className="px-4 py-2.5">{h.user_name}</td>
                                        <td className="px-4 py-2.5 font-bold">{h.hours}</td>
                                        <td className="px-4 py-2.5 text-xs">{h.event_type}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground max-w-sm truncate">{h.activity || h.description}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground">{h.date && format(parseISO(h.date), "MMM d, yyyy")}</td>
                                        <td className="px-4 py-2.5 text-xs uppercase tracking-wider font-semibold">{h.status}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_member" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Member</th><th className="text-left px-4 py-2.5">Chapter</th><th className="text-right px-4 py-2.5">Approved hours</th><th className="text-right px-4 py-2.5">Entries</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.user_id} className="border-t border-border" data-testid={`hours-by-member-row-${r.user_id}`}>
                                        <td className="px-4 py-2.5 font-medium">{r.user_name}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground">{r.chapter_name || "Unassigned"}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{r.hours.toFixed(1)}h</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_chapter" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Chapter</th><th className="text-right px-4 py-2.5">Active members</th><th className="text-right px-4 py-2.5">Approved hours</th><th className="text-right px-4 py-2.5">Entries</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((r, i) => (
                                    <tr key={r.chapter_id || `unassigned-${i}`} className="border-t border-border" data-testid={`hours-by-chapter-row-${r.chapter_id || "unassigned"}`}>
                                        <td className="px-4 py-2.5 font-medium">{r.chapter_name}</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.member_count}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{r.hours.toFixed(1)}h</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_period" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Period</th><th className="text-right px-4 py-2.5">Approved hours</th><th className="text-right px-4 py-2.5">Entries</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.period_key} className="border-t border-border" data-testid={`hours-by-period-row-${r.period_key}`}>
                                        <td className="px-4 py-2.5 font-medium">{r.period_label}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{r.hours.toFixed(1)}h</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                </table>
                {rows.length === 0 && <div className="p-6 text-center text-sm text-muted-foreground">No hours match these filters.</div>}
            </div>
        </div>
    );
}

function DonationsReport() {
    const [rows, setRows] = useState([]);
    const [causes, setCauses] = useState([]);
    const [filters, setFilters] = useState({ cause_id: "", status_filter: "" });

    async function run() {
        const params = Object.fromEntries(Object.entries(filters).filter(([_, v]) => v));
        const { data } = await api.get("/reports/donations", { params });
        setRows(data);
    }
    useEffect(() => {
        api.get("/causes").then(({ data }) => setCauses(data)).catch(() => {});
        run();
    }, []); // eslint-disable-line

    function exportCSV() {
        downloadCSV(`donations-${new Date().toISOString().slice(0, 10)}.csv`, csvify(rows, [
            { label: "Date", get: (t) => t.created_at?.slice(0, 10) || "" },
            { label: "Member", get: (t) => t.user_name },
            { label: "Amount", get: (t) => t.amount },
            { label: "Cause", get: (t) => causes.find((c) => c.id === t.cause_id)?.title || "" },
            { label: "Status", get: (t) => t.status },
            { label: "Note", get: (t) => t.description },
        ]));
    }

    const total = rows.filter((t) => t.status === "completed").reduce((s, t) => s + (t.amount || 0), 0);

    return (
        <div>
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="grid sm:grid-cols-3 gap-3">
                    <FilterSelect label="Cause" value={filters.cause_id} onChange={(v) => setFilters({ ...filters, cause_id: v })} options={[{ value: "", label: "Any" }, ...causes.map((c) => ({ value: c.id, label: c.title }))]} testid="donations-filter-cause" />
                    <FilterSelect label="Status" value={filters.status_filter} onChange={(v) => setFilters({ ...filters, status_filter: v })} options={[
                        { value: "", label: "Any" }, { value: "completed", label: "Completed" }, { value: "pending", label: "Pending" }, { value: "refunded", label: "Refunded" },
                    ]} testid="donations-filter-status" />
                    <div className="flex items-end gap-2">
                        <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="donations-report-run">Run</Button>
                        <Button onClick={exportCSV} variant="outline" className="rounded-full"><Download className="h-4 w-4 mr-1.5" />CSV</Button>
                    </div>
                </div>
            </div>
            <div className="text-sm text-muted-foreground mb-2">{rows.length} donations · ${total.toFixed(2)} completed</div>
            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                        <tr><th className="text-left px-4 py-2.5">Date</th><th className="text-left px-4 py-2.5">Donor</th><th className="text-left px-4 py-2.5">Amount</th><th className="text-left px-4 py-2.5">Cause</th><th className="text-left px-4 py-2.5">Status</th></tr>
                    </thead>
                    <tbody>
                        {rows.map((t) => (
                            <tr key={t.id} className="border-t border-border">
                                <td className="px-4 py-2.5 text-muted-foreground">{t.created_at && format(parseISO(t.created_at), "MMM d, yyyy")}</td>
                                <td className="px-4 py-2.5">{t.user_name || (t.anonymous ? "Anonymous" : "—")}</td>
                                <td className="px-4 py-2.5 font-bold">${t.amount?.toFixed(2)}</td>
                                <td className="px-4 py-2.5 text-muted-foreground">{causes.find((c) => c.id === t.cause_id)?.title || "—"}</td>
                                <td className="px-4 py-2.5 text-xs uppercase tracking-wider font-semibold">{t.status}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function PersonnelBriefSection() {
    const [members, setMembers] = useState([]);
    const [chosen, setChosen] = useState("");
    const [brief, setBrief] = useState(null);
    const [open, setOpen] = useState(false);

    useEffect(() => {
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => {});
    }, []);

    async function load() {
        if (!chosen) return;
        const { data } = await api.get(`/reports/personnel-brief/${chosen}`);
        setBrief(data);
        setOpen(true);
    }

    async function downloadPdf(userId) {
        if (!userId) return;
        try {
            const res = await api.get(`/reports/personnel-brief/${userId}/pdf`, { responseType: "blob" });
            const blob = new Blob([res.data], { type: "application/pdf" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            const m = members.find((x) => x.id === userId);
            const safe = (m?.name || "member").replace(/\s+/g, "_");
            a.download = `personnel-brief-${safe}.pdf`;
            a.click();
            URL.revokeObjectURL(url);
        } catch {
            // server error already toasts via interceptor
        }
    }

    return (
        <div>
            <div className="bg-card rounded-2xl border p-5 max-w-xl">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><FileText className="h-4 w-4" /> Generate brief</div>
                <Label className="text-xs">Member</Label>
                <Select value={chosen} onValueChange={setChosen}>
                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="brief-member-select"><SelectValue placeholder="Pick a member…" /></SelectTrigger>
                    <SelectContent className="max-h-80">
                        {members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} — {m.email}</SelectItem>)}
                    </SelectContent>
                </Select>
                <Button onClick={load} disabled={!chosen} className="mt-4 rounded-full bg-primary hover:bg-primary/90" data-testid="brief-generate-btn">
                    Generate brief
                </Button>
            </div>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="brief-dialog">
                    <DialogHeader className="print:pb-2 print:border-b print:border-black">
                        <DialogTitle className="font-heading text-2xl flex items-center justify-between gap-3">
                            Personnel Brief
                            <div className="flex gap-2 print:hidden">
                                <Button size="sm" onClick={() => downloadPdf(chosen)} variant="outline" className="rounded-full" data-testid="brief-pdf-btn">
                                    <Download className="h-4 w-4 mr-1.5" />Download PDF
                                </Button>
                                <Button size="sm" onClick={() => window.print()} variant="outline" className="rounded-full" data-testid="brief-print-btn">
                                    <Printer className="h-4 w-4 mr-1.5" />Print
                                </Button>
                            </div>
                        </DialogTitle>
                    </DialogHeader>
                    {brief && <BriefBody b={brief} />}
                </DialogContent>
            </Dialog>
        </div>
    );
}

function BriefBody({ b }) {
    const m = b.member;
    return (
        <div className="space-y-5 print:text-black" data-testid="brief-body">
            <div className="flex items-start gap-4">
                <div className="w-16 h-16 rounded-full bg-primary/15 text-primary grid place-items-center font-heading font-black text-2xl shrink-0">
                    {(m.name || m.email)[0]?.toUpperCase()}
                </div>
                <div>
                    <div className="font-heading text-2xl font-black">{m.name}</div>
                    {m.line_name && <div className="text-xs font-bold uppercase tracking-widest text-primary">"{m.line_name}"</div>}
                    <div className="text-sm text-muted-foreground mt-1">{m.email}</div>
                    <div className="text-xs text-muted-foreground">Status: <strong className="uppercase">{m.status}</strong> · Role: {m.role}</div>
                </div>
            </div>

            <Section title="Identity">
                <Kvp k="Phone" v={m.phone} />
                <Kvp k="Address" v={[m.address, m.city].filter(Boolean).join(", ")} />
                <Kvp k="Birthdate" v={m.birthdate} />
                <Kvp k="Branch of service" v={m.branch_of_service} />
                <Kvp k="Joined" v={m.created_at?.slice(0, 10)} />
                <Kvp k="Membership expires" v={m.membership_expires_at?.slice(0, 10)} />
            </Section>

            <Section title="Chapter & Tier">
                <Kvp k="Chapter" v={b.chapter?.name} />
                <Kvp k="Region/State" v={[b.chapter?.region, b.chapter?.state].filter(Boolean).join(" / ")} />
                <Kvp k="Tier" v={b.tier?.name} />
                <Kvp k="Annual dues" v={b.tier ? `$${b.tier.annual_dues?.toFixed(2)}` : ""} />
            </Section>

            <div className="grid sm:grid-cols-3 gap-3">
                <Stat label="Approved hours" value={`${b.approved_hours?.toFixed(1)}h`} />
                <Stat label="Awards" value={b.awards_count} />
                <Stat label="Events" value={b.events_count} />
            </div>

            <Section title={`Awards (${b.awards_count})`}>
                {b.awards.length === 0 ? <Empty /> : b.awards.map((g) => (
                    <div key={g.id} className="text-sm border-l-2 border-primary/40 pl-3 py-1">
                        <strong>{g.award_name}</strong> · {g.granted_at?.slice(0, 10)}
                        {g.reason && <div className="text-xs text-muted-foreground italic">{g.reason}</div>}
                    </div>
                ))}
            </Section>

            <Section title={`Volunteer hours (${b.hours.length})`}>
                {b.hours.length === 0 ? <Empty /> : (
                    <div className="text-sm space-y-1.5">
                        {b.hours.slice(0, 20).map((h) => (
                            <div key={h.id} className="flex items-start gap-3 border-l-2 border-accent pl-3 py-1">
                                <div className="font-bold w-12 shrink-0">{h.hours}h</div>
                                <div className="flex-1 min-w-0">
                                    <div>{h.activity || h.description}</div>
                                    <div className="text-xs text-muted-foreground">{h.date?.slice(0, 10)} · {h.event_type} · {h.status}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Section>

            <Section title={`Transactions ($${b.total_paid?.toFixed(2)} lifetime)`}>
                {b.transactions.length === 0 ? <Empty /> : (
                    <div className="text-sm">
                        {b.transactions.slice(0, 10).map((t) => (
                            <div key={t.id} className="flex items-center justify-between py-1.5 border-b border-border last:border-0">
                                <div className="min-w-0">
                                    <div className="text-xs uppercase tracking-wider font-bold">{t.type}</div>
                                    <div className="text-xs text-muted-foreground">{t.created_at?.slice(0, 10)} · {t.description}</div>
                                </div>
                                <div className="text-right shrink-0">
                                    <div className="font-bold">${t.amount?.toFixed(2)}</div>
                                    <div className="text-[10px] uppercase tracking-wider">{t.status}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Section>

            <div className="text-xs text-muted-foreground text-right mt-6 print:mt-12">
                Brief generated {b.generated_at?.slice(0, 16).replace("T", " ")} · Alpha Omega Phi
            </div>
        </div>
    );
}

function Section({ title, children }) {
    return (
        <div>
            <h3 className="font-heading text-xs uppercase tracking-widest text-muted-foreground mb-2 border-b border-border pb-1">{title}</h3>
            <div className="space-y-1.5">{children}</div>
        </div>
    );
}
function Kvp({ k, v }) {
    if (!v) return null;
    return <div className="flex items-start gap-3 text-sm"><div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground w-32 shrink-0 pt-0.5">{k}</div><div className="flex-1">{v}</div></div>;
}
function Stat({ label, value }) {
    return <div className="bg-muted/40 rounded-xl p-3 text-center"><div className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">{label}</div><div className="font-heading font-black text-2xl mt-1">{value}</div></div>;
}
function Empty() { return <div className="text-xs text-muted-foreground italic">None on record.</div>; }

function FilterSelect({ label, value, onChange, options, testid }) {
    return (
        <div>
            <Label className="text-xs">{label}</Label>
            <Select value={value || "__all__"} onValueChange={(v) => onChange(v === "__all__" ? "" : v)}>
                <SelectTrigger className="rounded-xl mt-1.5" data-testid={testid}><SelectValue /></SelectTrigger>
                <SelectContent>
                    {options.map((o) => <SelectItem key={o.value || "__all__"} value={o.value || "__all__"}>{o.label}</SelectItem>)}
                </SelectContent>
            </Select>
        </div>
    );
}

function ZeffyDuesApprovals() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);

    async function load() {
        setLoading(true);
        try {
            const { data } = await api.get("/transactions", { params: { status_filter: "pending" } });
            // Only Zeffy-pending dues transactions need our manual approval
            const pending = (data || []).filter((t) => t.provider === "zeffy" && t.status === "pending");
            setRows(pending);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not load pending transactions");
        }
        setLoading(false);
    }
    useEffect(() => { load(); }, []);

    async function approve(tx) {
        if (!window.confirm(`Approve ${tx.user_name}'s Zeffy dues payment of $${tx.amount}? Their membership will be extended 365 days.`)) return;
        try {
            await api.put(`/transactions/${tx.id}/approve-zeffy`);
            toast.success("Approved — membership extended");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Approval failed");
        }
    }

    async function reject(tx) {
        if (!window.confirm(`Reject ${tx.user_name}'s payment? This will delete the pending transaction.`)) return;
        try {
            await api.delete(`/transactions/${tx.id}`);
            toast.success("Pending transaction deleted");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Delete failed");
        }
    }

    if (loading) return <div className="text-muted-foreground text-center py-10">Loading…</div>;

    return (
        <div data-testid="zeffy-approvals-panel">
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="text-sm font-semibold mb-1">Pending Zeffy dues payments</div>
                <p className="text-xs text-muted-foreground">Members who paid via Zeffy and submitted their receipt for verification. Approving extends their membership 365 days.</p>
            </div>
            {rows.length === 0 ? (
                <div className="bg-card rounded-2xl border border-dashed border-border p-10 text-center" data-testid="zeffy-approvals-empty">
                    <div className="font-heading text-lg">All caught up</div>
                    <div className="text-sm text-muted-foreground mt-1">No pending Zeffy dues payments to verify.</div>
                </div>
            ) : (
                <div className="space-y-3">
                    {rows.map((t) => (
                        <div key={t.id} className="bg-card border-2 border-amber-300 bg-amber-50/40 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`zeffy-approval-row-${t.id}`}>
                            <div className="flex-1 min-w-0">
                                <div className="font-heading font-bold text-lg">{t.user_name}</div>
                                <div className="text-sm text-muted-foreground">${t.amount} · {t.description}</div>
                                <div className="text-xs text-muted-foreground mt-0.5">Submitted {t.created_at && format(parseISO(t.created_at), "MMM d, yyyy")}</div>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button variant="outline" size="sm" onClick={() => reject(t)} className="rounded-full" data-testid={`zeffy-reject-${t.id}`}>Reject</Button>
                                <Button onClick={() => approve(t)} className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`zeffy-approve-${t.id}`}>Approve & extend membership</Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

