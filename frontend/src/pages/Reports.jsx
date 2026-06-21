import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
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
                <TabsTrigger value="dues-reminders" className="rounded-full" data-testid="reports-tab-dues-reminders">Dues reminders</TabsTrigger>
                <TabsTrigger value="event-tickets" className="rounded-full" data-testid="reports-tab-event-tickets">Event tickets</TabsTrigger>
                <TabsTrigger value="awards" className="rounded-full" data-testid="reports-tab-awards">Awards</TabsTrigger>
                <TabsTrigger value="brief" className="rounded-full" data-testid="reports-tab-brief">Personnel Brief</TabsTrigger>
            </TabsList>
            <TabsContent value="members" className="mt-6"><MembersReport /></TabsContent>
            <TabsContent value="rsvps" className="mt-6"><RsvpsReport /></TabsContent>
            <TabsContent value="hours" className="mt-6"><HoursReport /></TabsContent>
            <TabsContent value="donations" className="mt-6"><DonationsReport /></TabsContent>
            <TabsContent value="dues" className="mt-6"><ZeffyDuesApprovals /></TabsContent>
            <TabsContent value="dues-reminders" className="mt-6"><DuesRemindersReport /></TabsContent>
            <TabsContent value="event-tickets" className="mt-6"><EventTicketApprovals /></TabsContent>
            <TabsContent value="awards" className="mt-6"><AwardsReport /></TabsContent>
            <TabsContent value="brief" className="mt-6"><PersonnelBriefSection /></TabsContent>
        </Tabs>
    );
}

function MembersReport() {
    const [rows, setRows] = useState([]);
    const [filters, setFilters] = useState({ status_filter: "", chapter_id: "", tier_id: "", role: "" });
    const [chapters, setChapters] = useState([]);
    const [tiers, setTiers] = useState([]);    useEffect(() => {
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

function Stat({ label, value }) {
    return (
        <div className="bg-muted/30 rounded-xl p-3">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">{label}</div>
            <div className="text-2xl font-heading font-bold mt-1">{value ?? "—"}</div>
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

    const years = (() => {
        const cy = now.getFullYear();
        const list = [];
        for (let y = cy; y >= 2017; y--) list.push(y);
        return list;
    })();
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
    const now = new Date();
    const [view, setView] = useState("entries"); // entries | by_member | by_chapter | by_period
    const [chapters, setChapters] = useState([]);
    const [causes, setCauses] = useState([]);
    const [year, setYear] = useState(now.getFullYear());
    const [period, setPeriod] = useState("all"); // all | q1..q4 | m1..m12
    const [chapterId, setChapterId] = useState("");
    const [causeId, setCauseId] = useState("");
    const [status, setStatus] = useState("");
    const [rows, setRows] = useState([]);
    const [summary, setSummary] = useState(null);

    useEffect(() => {
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
        api.get("/causes").then(({ data }) => setCauses(data)).catch(() => {});
    }, []);

    function buildParams() {
        const p = { year };
        if (period.startsWith("q")) p.quarter = period.slice(1);
        else if (period.startsWith("m")) p.month = period.slice(1);
        if (chapterId) p.chapter_id = chapterId;
        if (causeId) p.cause_id = causeId;
        if (status) p.status_filter = status;
        return p;
    }

    async function run() {
        const params = buildParams();
        if (view === "entries") {
            const { data } = await api.get("/reports/donations", { params });
            setRows(data); setSummary(null);
        } else {
            const groupBy = view === "by_member" ? "member" : view === "by_chapter" ? "chapter" : "month";
            const { data } = await api.get("/reports/donations/summary", { params: { ...params, group_by: groupBy } });
            setRows(data.rows || []); setSummary(data);
        }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        setRows([]);
        run();
    }, [view, year, period, chapterId, causeId, status]);

    function exportCSV() {
        let headers;
        const fname = `donations-${view}-${year}${period !== "all" ? "-" + period : ""}.csv`;
        if (view === "entries") {
            headers = [
                { label: "Date", get: (t) => t.created_at?.slice(0, 10) || "" },
                { label: "Member", get: (t) => t.user_name || (t.anonymous ? "Anonymous" : "") },
                { label: "Amount", get: (t) => t.amount },
                { label: "Cause", get: (t) => causeDisplay(t, causes) },
                { label: "Status", get: (t) => t.status },
                { label: "Note", get: (t) => t.description },
            ];
        } else if (view === "by_member") {
            headers = [
                { label: "Member", get: (r) => r.user_name },
                { label: "Chapter", get: (r) => r.chapter_name || "Unassigned" },
                { label: "Total donated", get: (r) => r.amount },
                { label: "Gifts", get: (r) => r.count },
            ];
        } else if (view === "by_chapter") {
            headers = [
                { label: "Chapter", get: (r) => r.chapter_name },
                { label: "Total donated", get: (r) => r.amount },
                { label: "Gifts", get: (r) => r.count },
                { label: "Distinct donors", get: (r) => r.member_count },
            ];
        } else {
            headers = [
                { label: "Period", get: (r) => r.period_label },
                { label: "Total donated", get: (r) => r.amount },
                { label: "Gifts", get: (r) => r.count },
            ];
        }
        downloadCSV(fname, csvify(rows, headers));
    }

    const years = (() => {
        const cy = now.getFullYear();
        const list = [];
        for (let y = cy; y >= 2017; y--) list.push(y);
        return list;
    })();
    const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const fmtMoney = (n) => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    return (
        <div data-testid="donations-report">
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><Filter className="h-4 w-4" /> Filters</div>
                <div className="grid sm:grid-cols-3 lg:grid-cols-5 gap-3">
                    <FilterSelect label="Year" value={String(year)} onChange={(v) => setYear(Number(v))} options={years.map((y) => ({ value: String(y), label: String(y) }))} testid="donations-filter-year" />
                    <div>
                        <Label className="text-xs">Period</Label>
                        <Select value={period} onValueChange={setPeriod}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="donations-filter-period"><SelectValue /></SelectTrigger>
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
                    <FilterSelect label="Chapter" value={chapterId} onChange={setChapterId} options={[{ value: "", label: "All chapters" }, ...chapters.map((c) => ({ value: c.id, label: c.name }))]} testid="donations-filter-chapter" />
                    <FilterSelect label="Status" value={status} onChange={setStatus} options={[
                        { value: "", label: "Any" }, { value: "completed", label: "Completed" }, { value: "pending", label: "Pending" }, { value: "refunded", label: "Refunded" }, { value: "failed", label: "Failed" },
                    ]} testid="donations-filter-status" />
                    <FilterSelect label="Cause" value={causeId} onChange={setCauseId} options={[{ value: "", label: "Any" }, ...causes.map((c) => ({ value: c.id, label: c.title }))]} testid="donations-filter-cause" />
                </div>
                <div className="flex flex-wrap justify-end gap-2 mt-4">
                    <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="donations-report-run">Run report</Button>
                    <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="donations-report-csv"><Download className="h-4 w-4 mr-1.5" />Export CSV</Button>
                </div>
            </div>

            {/* View switcher */}
            <Tabs value={view} onValueChange={setView}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="entries" className="rounded-full" data-testid="donations-view-entries">Individual entries</TabsTrigger>
                    <TabsTrigger value="by_member" className="rounded-full" data-testid="donations-view-by-member">By member</TabsTrigger>
                    <TabsTrigger value="by_chapter" className="rounded-full" data-testid="donations-view-by-chapter">By chapter</TabsTrigger>
                    <TabsTrigger value="by_period" className="rounded-full" data-testid="donations-view-by-period">By period</TabsTrigger>
                </TabsList>
            </Tabs>

            {/* Totals */}
            {summary?.totals && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4" data-testid="donations-totals">
                    <Stat label="Completed" value={fmtMoney(summary.totals.completed_amount)} />
                    <Stat label="Donors" value={summary.totals.donor_count} />
                    <Stat label="Pending" value={fmtMoney(summary.totals.pending_amount)} />
                    <Stat label="Refunded" value={fmtMoney(summary.totals.refunded_amount)} />
                </div>
            )}

            <div className="text-sm text-muted-foreground mt-4 mb-2">{rows.length} row{rows.length !== 1 ? "s" : ""}</div>

            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    {view === "entries" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Date</th><th className="text-left px-4 py-2.5">Donor</th><th className="text-right px-4 py-2.5">Amount</th><th className="text-left px-4 py-2.5">Cause</th><th className="text-left px-4 py-2.5">Status</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((t) => (
                                    <tr key={t.id} className="border-t border-border" data-testid={`donations-row-${t.id}`}>
                                        <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">{t.created_at && format(parseISO(t.created_at), "MMM d, yyyy")}</td>
                                        <td className="px-4 py-2.5">{t.user_name || (t.anonymous ? "Anonymous" : "—")}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{fmtMoney(t.amount)}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground">{causeDisplay(t, causes)}</td>
                                        <td className="px-4 py-2.5 text-xs uppercase tracking-wider font-semibold">{t.status}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_member" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Member</th><th className="text-left px-4 py-2.5">Chapter</th><th className="text-right px-4 py-2.5">Total donated</th><th className="text-right px-4 py-2.5">Gifts</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.user_id} className="border-t border-border" data-testid={`donations-by-member-row-${r.user_id}`}>
                                        <td className="px-4 py-2.5 font-medium">{r.user_name}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground">{r.chapter_name || "Unassigned"}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{fmtMoney(r.amount)}</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_chapter" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Chapter</th><th className="text-right px-4 py-2.5">Distinct donors</th><th className="text-right px-4 py-2.5">Total donated</th><th className="text-right px-4 py-2.5">Gifts</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((r, i) => (
                                    <tr key={r.chapter_id || `unassigned-${i}`} className="border-t border-border" data-testid={`donations-by-chapter-row-${r.chapter_id || "unassigned"}`}>
                                        <td className="px-4 py-2.5 font-medium">{r.chapter_name}</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.member_count}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{fmtMoney(r.amount)}</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_period" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Period</th><th className="text-right px-4 py-2.5">Total donated</th><th className="text-right px-4 py-2.5">Gifts</th></tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.period_key} className="border-t border-border" data-testid={`donations-by-period-row-${r.period_key}`}>
                                        <td className="px-4 py-2.5 font-medium">{r.period_label}</td>
                                        <td className="px-4 py-2.5 text-right font-bold">{fmtMoney(r.amount)}</td>
                                        <td className="px-4 py-2.5 text-right text-muted-foreground">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                </table>
                {rows.length === 0 && <div className="p-6 text-center text-sm text-muted-foreground">No donations match these filters.</div>}
            </div>
        </div>
    );
}

/** Resolve the cause column for a donation row.
 *   1. If linked → the cause's title.
 *   2. Else if a free-text cause_label was preserved (CSV import) → "<label> (unallocated)".
 *   3. Else → "—".
 */
function causeDisplay(t, causes) {
    if (t.cause_id) {
        const c = causes.find((x) => x.id === t.cause_id);
        if (c) return c.title;
    }
    if (t.cause_label) return `${t.cause_label} (unallocated)`;
    return "—";
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
    const chapter = b.chapter || {};
    const tier = b.tier || {};
    const currentYear = new Date().getFullYear();

    // §3 Education — sort chronologically (oldest → newest) per spec
    const degrees = [...(m.civilian_degrees || [])].sort((a, c) => (
        (a.graduation_year || 0) - (c.graduation_year || 0) ||
        (a.graduation_month || 0) - (c.graduation_month || 0)
    ));

    // §4 Languages — most recent year first
    const languages = [...(m.languages || [])].sort((a, c) => (c.year_accomplished || 0) - (a.year_accomplished || 0));

    const dues = (b.transactions || []).filter((t) => t.purpose === "dues" || t.type === "renewal").slice(0, 5);
    const donations = (b.transactions || []).filter((t) => t.type === "donation").slice(0, 5);
    const hoursCY = (b.hours || []).filter((h) => (h.date || "").slice(0, 4) === String(currentYear));

    // §8 Awards — Iter 36: one row per distinct award with total count + ordinal.
    // If backend supplied awards_grouped, use it directly; otherwise group locally.
    let awardsGrouped = b.awards_grouped;
    if (!awardsGrouped || awardsGrouped.length === 0) {
        const localCounts = {};
        const localLast = {};
        for (const g of [...(b.awards || [])].sort((a, c) => (a.granted_at || "").localeCompare(c.granted_at || ""))) {
            const nm = g.award_name || g.name || "—";
            localCounts[nm] = (localCounts[nm] || 0) + 1;
            localLast[nm] = g.granted_at || localLast[nm] || "";
        }
        awardsGrouped = Object.keys(localCounts).map((nm) => ({
            award_name: nm,
            count: localCounts[nm],
            last_granted_at: localLast[nm],
        }));
    }
    const awardsRows = [...awardsGrouped]
        .sort((a, c) => (c.last_granted_at || "").localeCompare(a.last_granted_at || ""))
        .map((row) => {
            const n = row.count || 1;
            const ord = n === 1 ? "1st Award" : n === 2 ? "2nd Award" : n === 3 ? "3rd Award" : `${n}th Award`;
            return [
                row.award_name || "—",
                n > 1 ? `${ord} (× ${n})` : ord,
                (row.last_granted_at || "").slice(0, 10),
            ];
        });

    // §9 Events — current-year check-ins only, dedup by event_id
    const checkinsCY = (b.checkins || []).filter((c) => (c.checked_in_at || "").slice(0, 4) === String(currentYear));
    const eventLookup = Object.fromEntries((b.events || []).map((e) => [e.id, e]));
    const rsvpLookup = Object.fromEntries((b.rsvps || []).map((r) => [r.event_id, r]));
    const seenEv = new Set();
    const eventRows = [];
    for (const c of checkinsCY) {
        if (seenEv.has(c.event_id)) continue;
        seenEv.add(c.event_id);
        const ev = eventLookup[c.event_id] || {};
        const rs = rsvpLookup[c.event_id] || {};
        eventRows.push({
            title: ev.title || "—",
            guests: (rs.guests || []).length,
            ticket_type: (c.ticket_type || rs.ticket_type || "general").replace("_", " "),
            date: (c.checked_in_at || "").slice(0, 10),
        });
    }

    // §10 Assignment History — current-first, then by start_date desc
    const assignments = [...(m.assignment_history || [])].sort((a, c) => {
        if (a.is_current && !c.is_current) return -1;
        if (c.is_current && !a.is_current) return 1;
        return (c.start_date || "").localeCompare(a.start_date || "");
    });

    return (
        <div className="space-y-5 print:text-black" data-testid="brief-body">
            {/* Header — photo + title + name + line + email + phone */}
            <div className="flex items-start gap-4 border-b border-border pb-4">
                {m.avatar_url ? (
                    <img src={mediaUrl(m.avatar_url)} alt="" className="w-20 h-20 rounded-lg object-cover border border-border" />
                ) : (
                    <div className="w-20 h-20 rounded-lg bg-primary/15 text-primary grid place-items-center font-heading font-black text-3xl shrink-0">
                        {(m.name || m.email)[0]?.toUpperCase()}
                    </div>
                )}
                <div className="flex-1 min-w-0">
                    <div className="font-heading text-2xl font-black leading-tight">{m.title ? `${m.title} ` : ""}{m.name}</div>
                    {m.line_name && <div className="text-xs font-bold uppercase tracking-widest text-primary mt-0.5">"{m.line_name}"</div>}
                    <div className="text-sm text-muted-foreground mt-1">{m.email}</div>
                    {m.phone && <div className="text-sm text-muted-foreground">{m.phone}</div>}
                </div>
            </div>

            <BriefSection num="1" title="Personal Information">
                <KvpGrid items={[
                    ["Address", m.address],
                    ["City", m.city],
                    ["State", m.state],
                    ["Country", m.country],
                    ["Zip code", m.zip_code],
                    ["Marital status", m.marital_status],
                    ["Birthdate", (m.birthdate || "").slice(0, 10)],
                    ["Branch of Service", m.branch_of_service],
                ]} />
            </BriefSection>

            <BriefSection num="2" title="Organization Information">
                <KvpGrid items={[
                    ["Chapter", chapter.name],
                    ["Region", chapter.region],
                    ["Status", (m.status || "").toUpperCase()],
                    ["Tier", tier.name],
                    ["Role", (m.role || "member")],
                    ["Joined", (m.join_date || m.created_at || "").slice(0, 10)],
                    ["Renewal", (m.membership_expires_at || "").slice(0, 10)],
                ]} />
            </BriefSection>

            <BriefSection num="3" title="Civilian Education">
                {degrees.length === 0 ? <Empty /> : <TableLike headers={["Level", "Type", "Field", "Institution", "Graduated"]} rows={degrees.map((d) => [
                    d.degree_level || "—",
                    d.degree_type || "—",
                    d.field_of_study || "—",
                    d.institution || "—",
                    `${["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.graduation_month || 0]} ${d.graduation_year || ""}`.trim() || "—",
                ])} />}
            </BriefSection>

            <BriefSection num="4" title="Languages">
                {languages.length === 0 ? <Empty /> : <TableLike headers={["Language", "Speaking", "Reading", "Writing", "Year"]} rows={languages.map((l) => [
                    l.language || "—", l.speaking || "—", l.reading || "—", l.writing || "—", String(l.year_accomplished || "—"),
                ])} />}
            </BriefSection>

            <BriefSection num="5" title="Financial Obligations (Annual Dues)">
                {dues.length === 0 ? <Empty /> : <TableLike headers={["Date", "Amount", "Status", "Description"]} rows={dues.map((t) => [
                    (t.created_at || "").slice(0, 10),
                    `$${(t.amount || 0).toFixed(2)}`,
                    (t.status || "—").toUpperCase(),
                    t.description || "—",
                ])} />}
            </BriefSection>

            <BriefSection num="6" title="Donations">
                {donations.length === 0 ? <Empty /> : <TableLike headers={["Date", "Cause", "Amount"]} rows={donations.map((t) => [
                    (t.created_at || "").slice(0, 10),
                    t.description || "General fund",
                    `$${(t.amount || 0).toFixed(2)}`,
                ])} />}
            </BriefSection>

            <BriefSection num="7" title={`Community Service (${currentYear})`}>
                {hoursCY.length === 0 ? <Empty /> : <TableLike headers={["Agency", "Event Type", "Hours", "Status", "Date"]} rows={hoursCY.map((h) => [
                    h.agency_name || "—",
                    (h.event_type || "other").replace("_", " "),
                    String(h.hours || 0),
                    (h.status || "—").toUpperCase(),
                    (h.date || "").slice(0, 10),
                ])} />}
            </BriefSection>

            <BriefSection num="8" title="Awards">
                {awardsRows.length === 0 ? <Empty /> : <TableLike headers={["Award", "Order", "Latest Date"]} rows={awardsRows} />}
            </BriefSection>

            <BriefSection num="9" title={`Events Attended (${currentYear} check-ins)`}>
                {eventRows.length === 0 ? <Empty /> : <TableLike headers={["Event", "Guests", "Ticket Type", "Check-in Date"]} rows={eventRows.map((e) => [
                    e.title, String(e.guests), e.ticket_type, e.date,
                ])} />}
            </BriefSection>

            <BriefSection num="10" title="Assignment History">
                {assignments.length === 0 ? <Empty /> : <TableLike headers={["Start", "End", "Chapter", "State", "Location", "Duty Title", "Rank"]} rows={assignments.map((a) => [
                    (a.start_date || "—").slice(0, 10) || "—",
                    a.is_current ? "Current" : ((a.end_date || "").slice(0, 10) || "—"),
                    a.chapter_name || "—",
                    a.state || "—",
                    a.location || "—",
                    a.duty_title || "—",
                    a.rank || "—",
                ])} />}
            </BriefSection>

            <div className="text-xs text-muted-foreground text-right mt-6 print:mt-12">
                Brief generated {b.generated_at?.slice(0, 16).replace("T", " ")} · Alpha Omega Phi
            </div>
        </div>
    );
}

function BriefSection({ num, title, children }) {
    return (
        <div data-testid={`brief-section-${num}`}>
            <h3 className="font-heading text-sm uppercase tracking-widest text-white bg-[hsl(220_45%_12%)] px-3 py-1.5 rounded mb-2">
                <span className="opacity-60 mr-2">§{num}</span>{title}
            </h3>
            <div className="space-y-1">{children}</div>
        </div>
    );
}

function KvpGrid({ items }) {
    const visible = items.filter(([_, v]) => v);
    if (visible.length === 0) return <Empty />;
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
            {visible.map(([k, v]) => (
                <div key={k} className="flex items-start gap-3 py-1.5 border-b border-border/50 text-sm">
                    <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground w-32 shrink-0 pt-0.5">{k}</div>
                    <div className="flex-1 break-words">{v}</div>
                </div>
            ))}
        </div>
    );
}

function TableLike({ headers, rows }) {
    return (
        <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-xs">
                <thead className="bg-muted/40">
                    <tr>{headers.map((h) => <th key={h} className="text-left font-bold uppercase tracking-wider text-[10px] px-2.5 py-1.5">{h}</th>)}</tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className="border-t border-border/50">
                            {r.map((cell, j) => <td key={j} className="px-2.5 py-1.5 align-top">{cell}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function Empty() {
    return <div className="text-xs text-muted-foreground italic px-1">— None on record —</div>;
}

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
            const { data } = await api.get("/transactions", { params: { provider: "zeffy" } });
            // Show pending awaiting approval + recent auto-approved (last 30 days) for audit
            const cutoff = Date.now() - 30 * 24 * 3600 * 1000;
            const filtered = (data || []).filter((t) => t.provider === "zeffy" && t.purpose === "dues" && (
                t.status === "pending" ||
                (t.zeffy_auto_approved && t.created_at && new Date(t.created_at).getTime() >= cutoff)
            ));
            // pending first, then auto-approved by created desc
            filtered.sort((a, b) => {
                if (a.status === "pending" && b.status !== "pending") return -1;
                if (b.status === "pending" && a.status !== "pending") return 1;
                return new Date(b.created_at) - new Date(a.created_at);
            });
            setRows(filtered);
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
            // Optimistically remove from local list; load() reconfirms with server
            setRows((cur) => cur.filter((r) => r.id !== tx.id));
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
            setRows((cur) => cur.filter((r) => r.id !== tx.id));
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
                    {rows.map((t) => {
                        const isPending = t.status === "pending";
                        return (
                            <div
                                key={t.id}
                                className={`bg-card border-2 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${isPending ? "border-amber-300 bg-amber-50/40" : "border-emerald-200 bg-emerald-50/30"}`}
                                data-testid={`zeffy-approval-row-${t.id}`}
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-heading font-bold text-lg">{t.user_name}</span>
                                        {!isPending && t.zeffy_auto_approved && (
                                            <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-300" data-testid={`zeffy-auto-badge-${t.id}`}>
                                                ⚡ Auto-approved
                                            </span>
                                        )}
                                        {isPending && (
                                            <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-300">
                                                Pending review
                                            </span>
                                        )}
                                        {t.zeffy_receipt_format ? (
                                            <span
                                                className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200"
                                                title={`Receipt format detected: ${t.zeffy_receipt_format}`}
                                                data-testid={`zeffy-format-badge-${t.id}`}
                                            >
                                                ✓ {t.zeffy_receipt_format === "rct" ? "RCT-####" : t.zeffy_receipt_format === "zf" ? "ZF-#" : t.zeffy_receipt_format === "email" ? "email" : "alnum id"}
                                            </span>
                                        ) : t.zeffy_confirmation ? (
                                            <span
                                                className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200"
                                                title="Receipt did not match a known Zeffy format — verify carefully"
                                                data-testid={`zeffy-format-badge-${t.id}`}
                                            >
                                                ⚠ unrecognised
                                            </span>
                                        ) : null}
                                    </div>
                                    <div className="text-sm text-muted-foreground">${t.amount} · {t.description}</div>
                                    <div className="text-xs text-muted-foreground mt-0.5">
                                        Submitted {t.created_at && format(parseISO(t.created_at), "MMM d, yyyy 'at' h:mm a")}
                                        {!isPending && t.approved_at && <> · Approved {format(parseISO(t.approved_at), "MMM d 'at' h:mm a")}</>}
                                    </div>
                                </div>
                                {isPending && (
                                    <div className="flex items-center gap-2">
                                        <Button variant="outline" size="sm" onClick={() => reject(t)} className="rounded-full" data-testid={`zeffy-reject-${t.id}`}>Reject</Button>
                                        <Button onClick={() => approve(t)} className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`zeffy-approve-${t.id}`}>Approve & extend membership</Button>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}




function EventTicketApprovals() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);

    async function load() {
        setLoading(true);
        try {
            const { data } = await api.get("/transactions");
            const cutoff = Date.now() - 30 * 24 * 3600 * 1000;
            const filtered = (data || []).filter((t) => t.purpose === "event_ticket" && (
                t.status === "pending" ||
                (t.zeffy_auto_approved && t.created_at && new Date(t.created_at).getTime() >= cutoff)
            ));
            filtered.sort((a, b) => {
                if (a.status === "pending" && b.status !== "pending") return -1;
                if (b.status === "pending" && a.status !== "pending") return 1;
                return new Date(b.created_at) - new Date(a.created_at);
            });
            setRows(filtered);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not load event-ticket transactions");
        }
        setLoading(false);
    }
    useEffect(() => { load(); }, []);

    async function approve(tx) {
        if (!window.confirm(`Approve ${tx.user_name}'s ticket for "${tx.event_title}" ($${tx.amount})? An RSVP will be created and the ticket emailed.`)) return;
        try {
            await api.put(`/transactions/${tx.id}/approve-event-ticket`);
            setRows((cur) => cur.filter((r) => r.id !== tx.id));
            toast.success("Approved — ticket emailed");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Approval failed");
        }
    }

    async function reject(tx) {
        if (!window.confirm(`Reject ${tx.user_name}'s payment? The pending transaction will be deleted.`)) return;
        try {
            await api.delete(`/transactions/${tx.id}`);
            setRows((cur) => cur.filter((r) => r.id !== tx.id));
            toast.success("Pending transaction deleted");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Delete failed");
        }
    }

    if (loading) return <div className="text-muted-foreground text-center py-10">Loading…</div>;

    return (
        <div data-testid="event-ticket-approvals-panel">
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="text-sm font-semibold mb-1">Pending event-ticket payments</div>
                <p className="text-xs text-muted-foreground">Members who paid via Zeffy for a paid event. Approving creates the RSVP and emails the QR ticket.</p>
            </div>
            {rows.length === 0 ? (
                <div className="bg-card rounded-2xl border border-dashed border-border p-10 text-center" data-testid="event-ticket-approvals-empty">
                    <div className="font-heading text-lg">All caught up</div>
                    <div className="text-sm text-muted-foreground mt-1">No pending event-ticket payments to verify.</div>
                </div>
            ) : (
                <div className="space-y-3">
                    {rows.map((t) => {
                        const isPending = t.status === "pending";
                        return (
                            <div
                                key={t.id}
                                className={`bg-card border-2 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${isPending ? "border-amber-300 bg-amber-50/40" : "border-emerald-200 bg-emerald-50/30"}`}
                                data-testid={`event-ticket-approval-row-${t.id}`}
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-heading font-bold text-lg">{t.user_name}</span>
                                        <span className="text-xs text-muted-foreground">→</span>
                                        <span className="font-semibold text-sm">{t.event_title}</span>
                                        {!isPending && t.zeffy_auto_approved && (
                                            <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-300">
                                                ⚡ Auto-approved
                                            </span>
                                        )}
                                        {isPending && (
                                            <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-300">
                                                Pending review
                                            </span>
                                        )}
                                        {t.zeffy_receipt_format ? (
                                            <span
                                                className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200"
                                                title={`Receipt format: ${t.zeffy_receipt_format}`}
                                            >
                                                ✓ {t.zeffy_receipt_format === "rct" ? "RCT-####" : t.zeffy_receipt_format === "zf" ? "ZF-#" : t.zeffy_receipt_format === "email" ? "email" : "alnum id"}
                                            </span>
                                        ) : t.zeffy_confirmation ? (
                                            <span className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                                                ⚠ unrecognised
                                            </span>
                                        ) : null}
                                    </div>
                                    <div className="text-sm text-muted-foreground">${t.amount} · {t.description}</div>
                                    <div className="text-xs text-muted-foreground mt-0.5">
                                        Submitted {t.created_at && format(parseISO(t.created_at), "MMM d, yyyy 'at' h:mm a")}
                                        {!isPending && t.approved_at && <> · Approved {format(parseISO(t.approved_at), "MMM d 'at' h:mm a")}</>}
                                    </div>
                                </div>
                                {isPending && (
                                    <div className="flex items-center gap-2">
                                        <Button variant="outline" size="sm" onClick={() => reject(t)} className="rounded-full" data-testid={`event-ticket-reject-${t.id}`}>Reject</Button>
                                        <Button onClick={() => approve(t)} className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`event-ticket-approve-${t.id}`}>Approve &amp; email ticket</Button>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}


const DUES_STAGE_LABELS = {
    before_30: "30 days before",
    before_15: "15 days before",
    before_5:  "5 days before",
    grace_1:   "Grace (+1 day)",
};

function DuesRemindersReport() {
    const [rows, setRows] = useState([]);
    const [summary, setSummary] = useState({ all_time: {}, last_30_days: {} });
    const [filters, setFilters] = useState({ stage: "", start: "", end: "" });
    const [loading, setLoading] = useState(false);

    async function run() {
        setLoading(true);
        try {
            const params = Object.fromEntries(Object.entries(filters).filter(([_, v]) => v));
            const [{ data: list }, { data: sum }] = await Promise.all([
                api.get("/reports/dues-reminders", { params }),
                api.get("/reports/dues-reminders/summary"),
            ]);
            setRows(list);
            setSummary(sum);
        } catch (e) {
            setRows([]);
        }
        setLoading(false);
    }
    useEffect(() => { run(); }, []); // eslint-disable-line

    function exportCSV() {
        downloadCSV(`dues-reminders-${new Date().toISOString().slice(0, 10)}.csv`, csvify(rows, [
            { label: "Sent at", get: (r) => r.sent_at || "" },
            { label: "Stage", get: (r) => DUES_STAGE_LABELS[r.stage] || r.stage },
            { label: "Member", get: (r) => r.user_name },
            { label: "Email", get: (r) => r.user_email },
            { label: "Reminder cycle expiration", get: (r) => (r.expires_at || "").slice(0, 10) },
            { label: "Current expiration", get: (r) => (r.current_expires_at || "").slice(0, 10) },
            { label: "Paid since reminder", get: (r) => (r.paid_since ? "Yes" : "No") },
            { label: "Current status", get: (r) => r.current_status || "" },
        ]));
    }

    const stageTotal = (s) => (summary.all_time?.[s] || 0);
    const stageRecent = (s) => (summary.last_30_days?.[s] || 0);

    return (
        <div data-testid="dues-reminders-report">
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                    {["before_30", "before_15", "before_5", "grace_1"].map((s) => (
                        <div key={s} className="bg-muted/30 rounded-xl p-3" data-testid={`dues-stat-${s}`}>
                            <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">{DUES_STAGE_LABELS[s]}</div>
                            <div className="text-2xl font-heading font-bold mt-1">{stageTotal(s)}</div>
                            <div className="text-xs text-muted-foreground">{stageRecent(s)} in last 30d</div>
                        </div>
                    ))}
                </div>
                <div className="grid sm:grid-cols-4 gap-3 items-end">
                    <FilterSelect
                        label="Stage"
                        value={filters.stage}
                        onChange={(v) => setFilters({ ...filters, stage: v })}
                        options={[
                            { value: "", label: "All stages" },
                            { value: "before_30", label: DUES_STAGE_LABELS.before_30 },
                            { value: "before_15", label: DUES_STAGE_LABELS.before_15 },
                            { value: "before_5",  label: DUES_STAGE_LABELS.before_5 },
                            { value: "grace_1",   label: DUES_STAGE_LABELS.grace_1 },
                        ]}
                        testid="dues-reminders-stage"
                    />
                    <div>
                        <Label className="text-xs">Sent on or after</Label>
                        <Input type="date" value={filters.start} onChange={(e) => setFilters({ ...filters, start: e.target.value })} className="rounded-xl mt-1.5" data-testid="dues-reminders-start" />
                    </div>
                    <div>
                        <Label className="text-xs">Sent on or before</Label>
                        <Input type="date" value={filters.end} onChange={(e) => setFilters({ ...filters, end: e.target.value })} className="rounded-xl mt-1.5" data-testid="dues-reminders-end" />
                    </div>
                    <div className="flex items-end gap-2">
                        <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="dues-reminders-run">{loading ? "Loading…" : "Run"}</Button>
                        <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="dues-reminders-csv"><Download className="h-4 w-4 mr-1.5" />CSV</Button>
                    </div>
                </div>
            </div>
            <div className="text-sm text-muted-foreground mb-2" data-testid="dues-reminders-count">{rows.length} reminder email{rows.length === 1 ? "" : "s"} matched</div>
            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                        <tr>
                            <th className="text-left px-4 py-2.5">Sent</th>
                            <th className="text-left px-4 py-2.5">Stage</th>
                            <th className="text-left px-4 py-2.5">Member</th>
                            <th className="text-left px-4 py-2.5">Email</th>
                            <th className="text-left px-4 py-2.5">Cycle exp.</th>
                            <th className="text-left px-4 py-2.5">Paid since</th>
                            <th className="text-left px-4 py-2.5">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={r.id} className="border-t border-border" data-testid={`dues-row-${r.id}`}>
                                <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">
                                    {r.sent_at && format(parseISO(r.sent_at), "MMM d, yyyy · h:mm a")}
                                </td>
                                <td className="px-4 py-2.5">
                                    <span className={`text-[10px] uppercase tracking-widest font-bold rounded-full px-2 py-0.5 ${r.stage === "grace_1" ? "bg-red-100 text-red-700" : "bg-primary/15 text-primary"}`}>
                                        {DUES_STAGE_LABELS[r.stage] || r.stage}
                                    </span>
                                </td>
                                <td className="px-4 py-2.5 font-medium">{r.user_name || "—"}</td>
                                <td className="px-4 py-2.5 text-muted-foreground">{r.user_email}</td>
                                <td className="px-4 py-2.5 text-muted-foreground">{(r.expires_at || "").slice(0, 10)}</td>
                                <td className="px-4 py-2.5">
                                    {r.paid_since ? (
                                        <span className="text-[10px] uppercase tracking-widest font-bold bg-green-100 text-green-700 rounded-full px-2 py-0.5">Yes</span>
                                    ) : <span className="text-xs text-muted-foreground">—</span>}
                                </td>
                                <td className="px-4 py-2.5 text-xs uppercase tracking-wider text-muted-foreground">{r.current_status || "—"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {rows.length === 0 && !loading && (
                    <div className="p-6 text-center text-sm text-muted-foreground">No reminders sent yet for these filters.</div>
                )}
            </div>
        </div>
    );
}

/**
 * Admin → Reports → Awards
 *
 * Two side-by-side audit panels:
 *   1. Award grants  — every ribbon/medal granted to a member (from award_grants)
 *   2. Of-The-Year   — yearly winners (Top Chapter, Member, Fundraiser, etc.)
 *
 * Both are searchable + filter by year, and export to CSV so leadership can
 * archive recognition records each year.
 */
function AwardsReport() {
    return (
        <div className="space-y-8" data-testid="awards-report">
            <AwardGrantsTable />
            <OfTheYearTable />
        </div>
    );
}

function AwardGrantsTable() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [year, setYear] = useState("");

    useEffect(() => {
        setLoading(true);
        const params = new URLSearchParams();
        if (year) params.set("year", year);
        api.get(`/reports/award-grants${params.toString() ? `?${params}` : ""}`)
            .then(({ data }) => setRows(data || []))
            .catch(() => setRows([]))
            .finally(() => setLoading(false));
    }, [year]);

    const filtered = search.trim()
        ? rows.filter((r) => {
            const q = search.trim().toLowerCase();
            return (
                (r.current_user_name || "").toLowerCase().includes(q)
                || (r.user_email || "").toLowerCase().includes(q)
                || (r.award_name || "").toLowerCase().includes(q)
                || (r.chapter_name || "").toLowerCase().includes(q)
                || (r.reason || "").toLowerCase().includes(q)
            );
        })
        : rows;

    function exportCSV() {
        const headers = [
            { label: "Granted at", get: (r) => r.granted_at || "" },
            { label: "Member", get: (r) => r.current_user_name || r.user_name || "" },
            { label: "Email", get: (r) => r.user_email || "" },
            { label: "Chapter", get: (r) => r.chapter_name || "" },
            { label: "Award", get: (r) => r.award_name || "" },
            { label: "Award #", get: (r) => r.ordinal || 1 },
            { label: "Granted by", get: (r) => r.granted_by_name || "" },
            { label: "Reason", get: (r) => r.reason || "" },
        ];
        downloadCSV(`award-grants-${new Date().toISOString().slice(0, 10)}.csv`, csvify(filtered, headers));
    }

    return (
        <div className="bg-card rounded-2xl border border-border shadow-warm overflow-hidden">
            <div className="flex flex-wrap items-end justify-between gap-3 p-4 border-b border-border">
                <div>
                    <h3 className="font-heading text-lg font-bold">Award grants</h3>
                    <p className="text-xs text-muted-foreground">Every ribbon, medal, and recognition awarded to a member — most recent first.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <Input
                        type="search"
                        placeholder="Search member, award, chapter…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="rounded-full text-sm h-9 w-64"
                        data-testid="awards-grants-search"
                    />
                    <Select value={year || "_all"} onValueChange={(v) => setYear(v === "_all" ? "" : v)}>
                        <SelectTrigger className="rounded-full h-9 w-32 text-sm" data-testid="awards-grants-year"><SelectValue placeholder="All years" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="_all">All years</SelectItem>
                            {Array.from({ length: new Date().getFullYear() - 2017 + 1 }).map((_, i) => {
                                const y = new Date().getFullYear() - i;
                                return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                            })}
                        </SelectContent>
                    </Select>
                    <Button variant="outline" className="rounded-full h-9 text-xs" onClick={exportCSV} data-testid="awards-grants-export"><Download className="h-3.5 w-3.5 mr-1" />CSV</Button>
                </div>
            </div>
            <div className="text-xs text-muted-foreground px-4 pt-3" data-testid="awards-grants-count">
                {loading ? "Loading…" : `${filtered.length} grant${filtered.length === 1 ? "" : "s"}`}
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                        <tr>
                            <th className="px-4 py-2.5 text-left font-semibold">Granted</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Member</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Chapter</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Award</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Granted by</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Reason</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {filtered.map((r) => (
                            <tr key={r.id} className="hover:bg-muted/30" data-testid={`award-grant-row-${r.id}`}>
                                <td className="px-4 py-2.5 text-xs whitespace-nowrap">{r.granted_at ? format(parseISO(r.granted_at), "MMM d, yyyy") : "—"}</td>
                                <td className="px-4 py-2.5">
                                    <div className="flex items-center gap-2">
                                        {r.user_avatar_url ? (
                                            <img src={mediaUrl(r.user_avatar_url)} alt="" className="w-7 h-7 rounded-full object-cover border border-border" />
                                        ) : (
                                            <div className="w-7 h-7 rounded-full bg-primary/15 text-primary grid place-items-center text-[10px] font-bold">{(r.current_user_name || "?").charAt(0).toUpperCase()}</div>
                                        )}
                                        <div>
                                            <div className="font-semibold">{r.current_user_name || r.user_name || "—"}</div>
                                            {r.user_email && <div className="text-[11px] text-muted-foreground">{r.user_email}</div>}
                                        </div>
                                    </div>
                                </td>
                                <td className="px-4 py-2.5 text-xs">{r.chapter_name || "—"}</td>
                                <td className="px-4 py-2.5">
                                    <div className="flex items-center gap-2">
                                        <span className="inline-block w-3 h-3 rounded-full border border-border" style={{ backgroundColor: r.award_color || "#F9D466" }} />
                                        <span className="font-semibold">{r.award_name}</span>
                                        {r.ordinal > 1 && <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary">{r.ordinal}×</span>}
                                    </div>
                                </td>
                                <td className="px-4 py-2.5 text-xs">{r.granted_by_name || "—"}</td>
                                <td className="px-4 py-2.5 text-xs text-foreground/80 max-w-[280px] truncate" title={r.reason}>{r.reason || "—"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {filtered.length === 0 && !loading && (
                    <div className="p-6 text-center text-sm text-muted-foreground">No award grants {search ? "match your search" : year ? "in this year" : "yet"}.</div>
                )}
            </div>
        </div>
    );
}

function OfTheYearTable() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [year, setYear] = useState(String(new Date().getFullYear()));

    useEffect(() => {
        setLoading(true);
        const params = new URLSearchParams();
        if (year && year !== "_all") params.set("year", year);
        api.get(`/reports/of-the-year${params.toString() ? `?${params}` : ""}`)
            .then(({ data }) => setRows(data || []))
            .catch(() => setRows([]))
            .finally(() => setLoading(false));
    }, [year]);

    function exportCSV() {
        const headers = [
            { label: "Year", get: (r) => r.year },
            { label: "Category", get: (r) => r.category_label || r.category },
            { label: "Winner", get: (r) => r.current_user_name || r.user_name || r.chapter_name || "" },
            { label: "Email", get: (r) => r.user_email || "" },
            { label: "Chapter", get: (r) => r.chapter_name || "" },
            { label: "Note", get: (r) => r.note || "" },
            { label: "Added by", get: (r) => r.created_by_name || "" },
        ];
        downloadCSV(`of-the-year-${year || "all"}.csv`, csvify(rows, headers));
    }

    return (
        <div className="bg-card rounded-2xl border border-border shadow-warm overflow-hidden">
            <div className="flex flex-wrap items-end justify-between gap-3 p-4 border-b border-border">
                <div>
                    <h3 className="font-heading text-lg font-bold">Of-The-Year winners</h3>
                    <p className="text-xs text-muted-foreground">Annual recognition (Top Chapter, Member, Fundraiser, Recruiter, etc.) Set them in Admin → Awards → Of-The-Year.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <Select value={year} onValueChange={setYear}>
                        <SelectTrigger className="rounded-full h-9 w-32 text-sm" data-testid="oty-year"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="_all">All years</SelectItem>
                            {Array.from({ length: new Date().getFullYear() - 2017 + 1 }).map((_, i) => {
                                const y = new Date().getFullYear() - i;
                                return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                            })}
                        </SelectContent>
                    </Select>
                    <Button variant="outline" className="rounded-full h-9 text-xs" onClick={exportCSV} data-testid="oty-export"><Download className="h-3.5 w-3.5 mr-1" />CSV</Button>
                </div>
            </div>
            <div className="text-xs text-muted-foreground px-4 pt-3" data-testid="oty-count">
                {loading ? "Loading…" : `${rows.length} winner${rows.length === 1 ? "" : "s"}`}
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                        <tr>
                            <th className="px-4 py-2.5 text-left font-semibold">Year</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Category</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Winner</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Note</th>
                            <th className="px-4 py-2.5 text-left font-semibold">Added by</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {rows.map((r) => (
                            <tr key={r.id} className="hover:bg-muted/30" data-testid={`oty-row-${r.id}`}>
                                <td className="px-4 py-2.5 text-xs font-mono">{r.year}</td>
                                <td className="px-4 py-2.5 font-semibold">{r.category_label || r.category}</td>
                                <td className="px-4 py-2.5">
                                    <div className="flex items-center gap-2">
                                        {r.user_avatar_url || r.chapter_logo_url ? (
                                            <img src={mediaUrl(r.user_avatar_url || r.chapter_logo_url)} alt="" className="w-7 h-7 rounded-full object-cover border border-border" />
                                        ) : (
                                            <div className="w-7 h-7 rounded-full bg-primary/15 text-primary grid place-items-center text-[10px] font-bold">{((r.current_user_name || r.chapter_name || "?").charAt(0) || "?").toUpperCase()}</div>
                                        )}
                                        <div>
                                            <div className="font-semibold">{r.current_user_name || r.user_name || r.chapter_name || "—"}</div>
                                            {r.user_email && <div className="text-[11px] text-muted-foreground">{r.user_email}</div>}
                                        </div>
                                    </div>
                                </td>
                                <td className="px-4 py-2.5 text-xs text-foreground/80 max-w-[280px]">{r.note || "—"}</td>
                                <td className="px-4 py-2.5 text-xs">{r.created_by_name || "—"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {rows.length === 0 && !loading && (
                    <div className="p-6 text-center text-sm text-muted-foreground">No "of-the-year" winners {year !== "_all" ? `for ${year}` : "recorded yet"}.</div>
                )}
            </div>
        </div>
    );
}
