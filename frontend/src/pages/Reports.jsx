import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Download, FileText, Filter, Printer, Pencil, Trash2 } from "lucide-react";
import { format, parseISO } from "date-fns";
import { formatCalendarDay } from "../lib/dateUtil";
import { FullEditHoursDialog } from "./Hours";
import { toast } from "sonner";

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
                <TabsTrigger value="recruitment" className="rounded-full" data-testid="reports-tab-recruitment">Recruitment</TabsTrigger>
                <TabsTrigger value="dues" className="rounded-full" data-testid="reports-tab-dues">Dues approvals</TabsTrigger>
                <TabsTrigger value="dues-reminders" className="rounded-full" data-testid="reports-tab-dues-reminders">Dues reminders</TabsTrigger>
                <TabsTrigger value="event-tickets" className="rounded-full" data-testid="reports-tab-event-tickets">Event tickets</TabsTrigger>
                <TabsTrigger value="awards" className="rounded-full" data-testid="reports-tab-awards">Awards</TabsTrigger>
                <TabsTrigger value="brief" className="rounded-full" data-testid="reports-tab-brief">Personnel Data Brief</TabsTrigger>
            </TabsList>
            <TabsContent value="members" className="mt-6"><MembersReport /></TabsContent>
            <TabsContent value="rsvps" className="mt-6"><RsvpsReport /></TabsContent>
            <TabsContent value="hours" className="mt-6"><HoursReport /></TabsContent>
            <TabsContent value="donations" className="mt-6"><DonationsReport /></TabsContent>
            <TabsContent value="recruitment" className="mt-6"><RecruitmentReport /></TabsContent>
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
                                <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">{(m.join_date || m.created_at) && formatCalendarDay(m.join_date || m.created_at, "MMM d, yyyy")}</td>
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
    const now = new Date();
    const [view, setView] = useState("entries"); // entries | by_member | by_chapter | by_period
    const [events, setEvents] = useState([]);
    // year is "all" or a 4-digit year string. Period is "all" | q1..q4 | m1..m12.
    const [year, setYear] = useState(String(now.getFullYear()));
    const [period, setPeriod] = useState("all");
    const [parentId, setParentId] = useState("");
    const [eventId, setEventId] = useState("");
    const [ticketType, setTicketType] = useState("");
    const [memberQuery, setMemberQuery] = useState("");
    // iter87 toggle — filter the period dropdown by either when the member
    // RSVP'd (rsvped_at) or by when the event itself is scheduled (event_start_at).
    const [dateField, setDateField] = useState("rsvped_at");
    const [rows, setRows] = useState([]);
    const [summary, setSummary] = useState(null);

    useEffect(() => {
        // Pull every event (incl. sub-events) so we can populate the
        // parent-event + sub-event selects in one shot.
        api.get("/events?include_sub_events=true").then(({ data }) => setEvents(data)).catch(() => {});
    }, []);

    function buildParams() {
        const p = { date_field: dateField };
        if (year !== "all") {
            p.year = year;
            if (period.startsWith("q")) p.quarter = period.slice(1);
            else if (period.startsWith("m")) p.month = period.slice(1);
        }
        // Specific sub-event wins over parent filter (matches HoursReport
        // pattern of "more specific overrides broader").
        if (eventId) p.event_id = eventId;
        else if (parentId) p.parent_event_id = parentId;
        if (ticketType) p.ticket_type = ticketType;
        return p;
    }

    async function run() {
        const params = buildParams();
        if (view === "entries") {
            const { data } = await api.get("/reports/rsvps", { params });
            setRows(data); setSummary(null);
        } else {
            const groupBy = view === "by_member" ? "member" : view === "by_chapter" ? "chapter" : "period";
            const { data } = await api.get("/reports/rsvps/summary", { params: { ...params, group_by: groupBy } });
            setRows(data.rows || []); setSummary(data);
        }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { setRows([]); run(); }, [view, year, period, parentId, eventId, ticketType, dateField]);

    function exportCSV() {
        const fnameBase = `rsvps-${view}-${year === "all" ? "all-years" : year}${year !== "all" && period !== "all" ? "-" + period : ""}`;
        let headers;
        if (view === "entries") {
            headers = [
                { label: "Event", get: (r) => r.event_title },
                { label: "Event date", get: (r) => r.event_start_at?.slice(0, 10) || "" },
                { label: "Member", get: (r) => r.user_name },
                { label: "Chapter", get: (r) => r.chapter_name || "" },
                { label: "RSVPed at", get: (r) => r.rsvped_at?.slice(0, 16).replace("T", " ") || "" },
                { label: "Ticket type", get: (r) => r.ticket_type || "" },
                { label: "Checked in at", get: (r) => r.checked_in_at?.slice(0, 16).replace("T", " ") || "" },
                { label: "Guest count", get: (r) => r.guest_count },
                { label: "Guests", get: (r) => (r.guests || []).map((g) => `${g.name}${g.email ? ` <${g.email}>` : ""}`).join("; ") },
            ];
        } else if (view === "by_member") {
            headers = [
                { label: "Member", get: (r) => r.user_name },
                { label: "Chapter", get: (r) => r.chapter_name || "Unassigned" },
                { label: "RSVPs", get: (r) => r.rsvp_count },
                { label: "Guests", get: (r) => r.guest_count },
                { label: "Checked in", get: (r) => r.checked_in_count },
            ];
        } else if (view === "by_chapter") {
            headers = [
                { label: "Chapter", get: (r) => r.chapter_name },
                { label: "RSVPs", get: (r) => r.rsvp_count },
                { label: "Guests", get: (r) => r.guest_count },
                { label: "Checked in", get: (r) => r.checked_in_count },
                { label: "Members", get: (r) => r.member_count },
            ];
        } else {
            headers = [
                { label: "Period", get: (r) => r.period_label },
                { label: "RSVPs", get: (r) => r.rsvp_count },
                { label: "Guests", get: (r) => r.guest_count },
                { label: "Checked in", get: (r) => r.checked_in_count },
            ];
        }
        downloadCSV(`${fnameBase}.csv`, csvify(rows, headers));
    }

    const years = (() => {
        const cy = now.getFullYear();
        const list = [];
        for (let y = cy; y >= 2017; y--) list.push(y);
        return list;
    })();
    const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    const parentEvents = events.filter((e) => !e.parent_event_id);
    const subEvents = parentId
        ? events.filter((e) => e.parent_event_id === parentId)
        : events.filter((e) => e.parent_event_id);

    // Apply client-side member-name search on the entries view only.
    const visibleRows = (view === "entries" && memberQuery.trim())
        ? rows.filter((r) => (r.user_name || "").toLowerCase().includes(memberQuery.trim().toLowerCase()))
        : rows;

    return (
        <div data-testid="rsvps-report">
            <div className="bg-card rounded-2xl border border-border p-5 mb-4">
                <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
                    <div className="flex items-center gap-2 text-sm font-semibold"><Filter className="h-4 w-4" /> Filters</div>
                    {/* iter87 — date-context toggle */}
                    <div className="inline-flex items-center gap-0 rounded-full bg-muted p-0.5 text-xs" role="group" data-testid="rsvps-date-field-toggle">
                        <span className="px-2 text-muted-foreground hidden sm:inline">📅 Filter by:</span>
                        <button
                            type="button"
                            onClick={() => setDateField("rsvped_at")}
                            className={`rounded-full px-3 py-1 font-semibold transition-colors ${dateField === "rsvped_at" ? "bg-primary text-white shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="rsvps-date-field-rsvped"
                        >
                            RSVP date
                        </button>
                        <button
                            type="button"
                            onClick={() => setDateField("event_start_at")}
                            className={`rounded-full px-3 py-1 font-semibold transition-colors ${dateField === "event_start_at" ? "bg-primary text-white shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="rsvps-date-field-event"
                        >
                            Event date
                        </button>
                    </div>
                </div>
                <div className="grid sm:grid-cols-3 lg:grid-cols-5 gap-3">
                    <FilterSelect label="Year" value={year} onChange={setYear} options={[{ value: "all", label: "All years" }, ...years.map((y) => ({ value: String(y), label: String(y) }))]} testid="rsvps-filter-year" />
                    <div>
                        <Label className="text-xs">Period</Label>
                        <Select value={period} onValueChange={setPeriod} disabled={year === "all"}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="rsvps-filter-period"><SelectValue placeholder={year === "all" ? "—" : ""} /></SelectTrigger>
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
                    <FilterSelect
                        label="Parent event"
                        value={parentId}
                        onChange={(v) => { setParentId(v); setEventId(""); }}
                        options={[{ value: "", label: "All events" }, ...parentEvents.map((e) => ({ value: e.id, label: e.title }))]}
                        testid="rsvps-filter-parent"
                    />
                    <FilterSelect
                        label="Sub-event"
                        value={eventId}
                        onChange={setEventId}
                        options={[{ value: "", label: parentId ? "All sub-events of selected" : "Any" }, ...subEvents.map((e) => ({ value: e.id, label: e.title }))]}
                        testid="rsvps-filter-subevent"
                    />
                    <FilterSelect
                        label="Ticket type"
                        value={ticketType}
                        onChange={setTicketType}
                        options={[
                            { value: "", label: "Any" },
                            { value: "vip", label: "VIP" },
                            { value: "all_access", label: "All Access" },
                            { value: "general", label: "General Admission" },
                            { value: "guest", label: "Guest" },
                            { value: "speaker", label: "Speaker" },
                            { value: "volunteer", label: "Volunteer" },
                        ]}
                        testid="rsvps-filter-ticket-type"
                    />
                </div>
                {view === "entries" && (
                    <div className="mt-3">
                        <Label className="text-xs">Search member</Label>
                        <Input
                            value={memberQuery}
                            onChange={(e) => setMemberQuery(e.target.value)}
                            placeholder="Filter by member name…"
                            className="rounded-xl mt-1.5"
                            data-testid="rsvps-filter-member-search"
                        />
                    </div>
                )}
                <div className="flex flex-wrap justify-end gap-2 mt-4">
                    <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="rsvps-report-run-btn">Run report</Button>
                    <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="rsvps-report-csv-btn"><Download className="h-4 w-4 mr-1.5" />Export CSV</Button>
                </div>
            </div>

            {/* View pills */}
            <Tabs value={view} onValueChange={setView}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="entries" className="rounded-full" data-testid="rsvps-view-entries">Individual entries</TabsTrigger>
                    <TabsTrigger value="by_member" className="rounded-full" data-testid="rsvps-view-by-member">By member</TabsTrigger>
                    <TabsTrigger value="by_chapter" className="rounded-full" data-testid="rsvps-view-by-chapter">By chapter</TabsTrigger>
                    <TabsTrigger value="by_period" className="rounded-full" data-testid="rsvps-view-by-period">By period</TabsTrigger>
                </TabsList>
            </Tabs>

            {summary && (
                <div className="grid sm:grid-cols-4 gap-3 mt-4" data-testid="rsvps-summary-totals">
                    <Stat label="RSVPs" value={summary.totals?.rsvp_count} />
                    <Stat label="Walk-ins" value={summary.totals?.walk_in_count} />
                    <Stat label="Guests" value={summary.totals?.guest_count} />
                    <Stat label="Checked in" value={summary.totals?.checked_in_count} />
                </div>
            )}

            <div className="bg-card rounded-2xl border overflow-x-auto mt-4">
                {view === "entries" && (
                    <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-4 py-2.5">Event</th>
                                <th className="text-left px-4 py-2.5">Member</th>
                                <th className="text-left px-4 py-2.5">RSVPed</th>
                                <th className="text-left px-4 py-2.5">Ticket</th>
                                <th className="text-left px-4 py-2.5">Checked in</th>
                                <th className="text-left px-4 py-2.5">Guests</th>
                            </tr>
                        </thead>
                        <tbody>
                            {visibleRows.map((r) => (
                                <tr key={r.rsvp_id} className="border-t border-border align-top" data-testid={`rsvps-report-row-${r.rsvp_id}`}>
                                    <td className="px-4 py-2.5">
                                        <div className="font-medium">{r.event_title}</div>
                                        {r.event_start_at && <div className="text-xs text-muted-foreground">{format(parseISO(r.event_start_at), "MMM d, yyyy")}</div>}
                                    </td>
                                    <td className="px-4 py-2.5">
                                        <div>{r.user_name}</div>
                                        {r.chapter_name && <div className="text-[11px] text-muted-foreground">{r.chapter_name}</div>}
                                    </td>
                                    <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap text-xs">
                                        {r.rsvped_at
                                            ? format(parseISO(r.rsvped_at), "MMM d, yyyy h:mm a")
                                            : (r.is_walk_in
                                                ? <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-amber-100 text-amber-800" data-testid={`rsvps-walkin-${r.user_id}-${r.event_id}`}>Walk-in</span>
                                                : "—")}
                                    </td>
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
                )}
                {view === "by_member" && (
                    <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-4 py-2.5">Member</th>
                                <th className="text-left px-4 py-2.5">Chapter</th>
                                <th className="text-right px-4 py-2.5">RSVPs</th>
                                <th className="text-right px-4 py-2.5">Guests</th>
                                <th className="text-right px-4 py-2.5">Checked in</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r) => (
                                <tr key={r.user_id} className="border-t border-border" data-testid={`rsvps-summary-member-${r.user_id}`}>
                                    <td className="px-4 py-2.5">{r.user_name}</td>
                                    <td className="px-4 py-2.5 text-muted-foreground">{r.chapter_name || "Unassigned"}</td>
                                    <td className="px-4 py-2.5 text-right font-semibold">{r.rsvp_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.guest_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.checked_in_count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {view === "by_chapter" && (
                    <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-4 py-2.5">Chapter</th>
                                <th className="text-right px-4 py-2.5">RSVPs</th>
                                <th className="text-right px-4 py-2.5">Guests</th>
                                <th className="text-right px-4 py-2.5">Checked in</th>
                                <th className="text-right px-4 py-2.5">Members</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, i) => (
                                <tr key={r.chapter_id || `unassigned-${i}`} className="border-t border-border" data-testid={`rsvps-summary-chapter-${r.chapter_id || "unassigned"}`}>
                                    <td className="px-4 py-2.5">{r.chapter_name}</td>
                                    <td className="px-4 py-2.5 text-right font-semibold">{r.rsvp_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.guest_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.checked_in_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.member_count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {view === "by_period" && (
                    <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-4 py-2.5">Period</th>
                                <th className="text-right px-4 py-2.5">RSVPs</th>
                                <th className="text-right px-4 py-2.5">Guests</th>
                                <th className="text-right px-4 py-2.5">Checked in</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r) => (
                                <tr key={r.period_key} className="border-t border-border" data-testid={`rsvps-summary-period-${r.period_key}`}>
                                    <td className="px-4 py-2.5">{r.period_label}</td>
                                    <td className="px-4 py-2.5 text-right font-semibold">{r.rsvp_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.guest_count}</td>
                                    <td className="px-4 py-2.5 text-right">{r.checked_in_count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
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

/* -------- Recruitment Report -------- */
// Bar-chart for the "by month" view — matches the visual weight of the
// donations/hours monthly trend cards. Renders defensively (skips rows
// missing `period_label`) because state can briefly hold stale data from
// a prior view between the tab click and the useEffect refetch.
function RecruitmentMonthlyTrendChart({ data }) {
    const safe = (data || []).filter((r) => r && typeof r.period_label === "string");
    if (safe.length === 0) return null;
    const max = Math.max(1, ...safe.map((r) => r.count || 0));
    return (
        <div className="bg-card rounded-2xl border p-5" data-testid="recruitment-trend">
            <div className="text-sm font-semibold mb-4">Monthly trend</div>
            <div className="flex items-end gap-2 h-40">
                {safe.map((r) => {
                    const pct = Math.round(((r.count || 0) / max) * 100);
                    return (
                        <div key={r.period_label} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                            <div className="text-[10px] text-muted-foreground font-bold">{r.count}</div>
                            <div className="w-full rounded-t-md" style={{ height: `${Math.max(pct, 3)}%`, backgroundColor: "#C8102E", minHeight: "3px" }} />
                            <div className="text-[10px] text-muted-foreground truncate">{r.period_label.slice(5)}</div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function RecruitmentReport() {
    const now = new Date();
    const [view, setView] = useState("entries"); // entries | by_recruiter | by_chapter | by_month
    const [chapters, setChapters] = useState([]);
    const [year, setYear] = useState(String(now.getFullYear()));
    const [period, setPeriod] = useState("all");
    const [chapterId, setChapterId] = useState("");
    const [rows, setRows] = useState([]);
    const [summary, setSummary] = useState(null);

    useEffect(() => {
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
    }, []);

    function buildParams() {
        const p = {};
        if (year !== "all") {
            p.year = year;
            if (period !== "all") p.period = period;
        }
        if (chapterId) p.chapter_id = chapterId;
        return p;
    }

    async function run() {
        const params = buildParams();
        if (view === "entries") {
            const { data } = await api.get("/reports/recruitment", { params });
            setRows(data);
            setSummary({ totals: { total_recruits: data.length, distinct_recruiters: new Set(data.map((r) => r.recruiter_id)).size } });
        } else {
            const groupBy = view === "by_recruiter" ? "recruiter" : view === "by_chapter" ? "chapter" : "month";
            const { data } = await api.get("/reports/recruitment/summary", { params: { ...params, group_by: groupBy } });
            setRows(data.rows || []);
            setSummary(data);
        }
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        setRows([]);
        run();
    }, [view, year, period, chapterId]);

    function exportCSV() {
        let headers;
        const fname = `recruitment-${view}-${year === "all" ? "all-years" : year}${year !== "all" && period !== "all" ? "-" + period : ""}.csv`;
        if (view === "entries") {
            headers = [
                { label: "Date", get: (r) => (r.date_recruited || "").slice(0, 10) },
                { label: "Recruiter", get: (r) => r.recruiter_name || "" },
                { label: "Recruiter email", get: (r) => r.recruiter_email || "" },
                { label: "Recruit", get: (r) => r.recruit_name || "" },
                { label: "Recruit email", get: (r) => r.recruit_email || "" },
                { label: "Chapter", get: (r) => r.chapter_name || "" },
                { label: "Notes", get: (r) => r.notes || "" },
            ];
        } else if (view === "by_recruiter") {
            headers = [
                { label: "Recruiter", get: (r) => r.user_name },
                { label: "Email", get: (r) => r.user_email },
                { label: "Chapter", get: (r) => r.chapter_name || "Unassigned" },
                { label: "Total recruits", get: (r) => r.count },
            ];
        } else if (view === "by_chapter") {
            headers = [
                { label: "Chapter", get: (r) => r.chapter_name },
                { label: "Total recruits", get: (r) => r.count },
                { label: "Distinct recruiters", get: (r) => r.recruiter_count },
            ];
        } else {
            headers = [
                { label: "Month", get: (r) => r.period_label },
                { label: "Recruits", get: (r) => r.count },
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
        <div data-testid="recruitment-report">
            <div className="bg-card rounded-2xl border p-5 mb-4">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><Filter className="h-4 w-4" /> Filters</div>
                <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
                    <FilterSelect label="Year" value={year} onChange={setYear} options={[{ value: "all", label: "All years" }, ...years.map((y) => ({ value: String(y), label: String(y) }))]} testid="recruitment-filter-year" />
                    <div>
                        <Label className="text-xs">Period</Label>
                        <Select value={period} onValueChange={setPeriod} disabled={year === "all"}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="recruitment-filter-period"><SelectValue placeholder={year === "all" ? "—" : ""} /></SelectTrigger>
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
                    <FilterSelect label="Chapter" value={chapterId} onChange={setChapterId} options={[{ value: "", label: "All chapters" }, ...chapters.map((c) => ({ value: c.id, label: c.name }))]} testid="recruitment-filter-chapter" />
                </div>
                <div className="flex flex-wrap justify-end gap-2 mt-4">
                    <Button onClick={run} className="rounded-full bg-primary hover:bg-primary/90" data-testid="recruitment-report-run">Run report</Button>
                    <Button onClick={exportCSV} variant="outline" className="rounded-full" data-testid="recruitment-report-csv"><Download className="h-4 w-4 mr-1.5" />Export CSV</Button>
                </div>
            </div>

            <Tabs value={view} onValueChange={setView}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="entries" className="rounded-full" data-testid="recruitment-view-entries">Individual entries</TabsTrigger>
                    <TabsTrigger value="by_recruiter" className="rounded-full" data-testid="recruitment-view-by-recruiter">By recruiter</TabsTrigger>
                    <TabsTrigger value="by_chapter" className="rounded-full" data-testid="recruitment-view-by-chapter">By chapter</TabsTrigger>
                    <TabsTrigger value="by_month" className="rounded-full" data-testid="recruitment-view-by-month">Monthly trend</TabsTrigger>
                </TabsList>
            </Tabs>

            {summary?.totals && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4" data-testid="recruitment-totals">
                    <Stat label="Total recruits" value={summary.totals.total_recruits} />
                    <Stat label="Distinct recruiters" value={summary.totals.distinct_recruiters} />
                </div>
            )}

            <div className="text-sm text-muted-foreground mt-4 mb-2">{rows.length} row{rows.length !== 1 ? "s" : ""}</div>

            {view === "by_month" && rows.length > 0 && (
                <div className="mb-4"><RecruitmentMonthlyTrendChart data={rows} /></div>
            )}

            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    {view === "entries" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr>
                                    <th className="text-left px-4 py-3">Date</th>
                                    <th className="text-left px-4 py-3">Recruiter</th>
                                    <th className="text-left px-4 py-3">Recruit</th>
                                    <th className="text-left px-4 py-3">Chapter</th>
                                    <th className="text-left px-4 py-3">Notes</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.id} className="border-t" data-testid={`recruitment-row-${r.id}`}>
                                        <td className="px-4 py-3 whitespace-nowrap font-medium">{(r.date_recruited || "").slice(0, 10)}</td>
                                        <td className="px-4 py-3">
                                            <div className="font-semibold">{r.recruiter_name || "—"}</div>
                                            <div className="text-xs text-muted-foreground">{r.recruiter_email}</div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="font-semibold">{r.recruit_name || "—"}</div>
                                            <div className="text-xs text-muted-foreground">{r.recruit_email}</div>
                                        </td>
                                        <td className="px-4 py-3">{r.chapter_name || "—"}</td>
                                        <td className="px-4 py-3 max-w-[300px] truncate" title={r.notes}>{r.notes}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_recruiter" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr>
                                    <th className="text-left px-4 py-3">Recruiter</th>
                                    <th className="text-left px-4 py-3">Chapter</th>
                                    <th className="text-right px-4 py-3">Total recruits</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.user_id} className="border-t" data-testid={`recruitment-recruiter-${r.user_id}`}>
                                        <td className="px-4 py-3">
                                            <div className="font-semibold">{r.user_name}</div>
                                            <div className="text-xs text-muted-foreground">{r.user_email}</div>
                                        </td>
                                        <td className="px-4 py-3">{r.chapter_name}</td>
                                        <td className="px-4 py-3 text-right font-bold">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_chapter" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr>
                                    <th className="text-left px-4 py-3">Chapter</th>
                                    <th className="text-right px-4 py-3">Total recruits</th>
                                    <th className="text-right px-4 py-3">Distinct recruiters</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.chapter_id || "unassigned"} className="border-t" data-testid={`recruitment-chapter-${r.chapter_id || "unassigned"}`}>
                                        <td className="px-4 py-3 font-semibold">{r.chapter_name}</td>
                                        <td className="px-4 py-3 text-right font-bold">{r.count}</td>
                                        <td className="px-4 py-3 text-right">{r.recruiter_count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                    {view === "by_month" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr>
                                    <th className="text-left px-4 py-3">Month</th>
                                    <th className="text-right px-4 py-3">Recruits</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.filter((r) => typeof r.period_label === "string").map((r) => (
                                    <tr key={r.period_label} className="border-t" data-testid={`recruitment-month-${r.period_label}`}>
                                        <td className="px-4 py-3 font-medium">{r.period_label}</td>
                                        <td className="px-4 py-3 text-right font-bold">{r.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </>
                    )}
                </table>
            </div>
        </div>
    );
}


function HoursReport() {
    const now = new Date();
    const [view, setView] = useState("entries"); // entries | by_member | by_chapter | by_period
    const [chapters, setChapters] = useState([]);
    // year is "all" or a stringified 4-digit year so the Select binds cleanly
    // and the "All years" option drops the year/period params from the query.
    const [year, setYear] = useState(String(now.getFullYear()));
    const [period, setPeriod] = useState("all"); // all | q1..q4 | m1..m12
    const [chapterId, setChapterId] = useState("");
    const [eventType, setEventType] = useState("");
    const [status, setStatus] = useState("");
    // Client-side text filter against user_name. Lives outside `buildParams`
    // because the backend has no member-name search — we filter the rendered
    // rows so the filter stays responsive as the admin types.
    const [memberQuery, setMemberQuery] = useState("");
    const [rows, setRows] = useState([]);
    const [summary, setSummary] = useState(null);

    useEffect(() => { api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {}); }, []);

    function buildParams() {
        const p = {};
        // "All years" omits the year/period filters entirely so the backend
        // returns lifetime totals.
        if (year !== "all") {
            p.year = year;
            if (period.startsWith("q")) p.quarter = period.slice(1);
            else if (period.startsWith("m")) p.month = period.slice(1);
        }
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
        let fname = `hours-${view}-${year === "all" ? "all-years" : year}${year !== "all" && period !== "all" ? "-" + period : ""}.csv`;
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
                    <FilterSelect label="Year" value={year} onChange={setYear} options={[{ value: "all", label: "All years" }, ...years.map((y) => ({ value: String(y), label: String(y) }))]} testid="hours-filter-year" />
                    <div>
                        <Label className="text-xs">Period</Label>
                        <Select value={period} onValueChange={setPeriod} disabled={year === "all"}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="hours-filter-period"><SelectValue placeholder={year === "all" ? "—" : ""} /></SelectTrigger>
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
                {view === "entries" && (
                    <div className="mt-3">
                        <Label className="text-xs">Search member</Label>
                        <Input
                            value={memberQuery}
                            onChange={(e) => setMemberQuery(e.target.value)}
                            placeholder="Filter by member name…"
                            className="rounded-xl mt-1.5"
                            data-testid="hours-filter-member-search"
                        />
                    </div>
                )}
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

            <div className="text-sm text-muted-foreground mt-4 mb-2">
                {(() => {
                    const shown = view === "entries" && memberQuery.trim()
                        ? rows.filter((h) => (h.user_name || "").toLowerCase().includes(memberQuery.toLowerCase().trim())).length
                        : rows.length;
                    if (view === "entries" && memberQuery.trim()) {
                        return `${shown} of ${rows.length} row${rows.length !== 1 ? "s" : ""} match "${memberQuery.trim()}"`;
                    }
                    return `${rows.length} row${rows.length !== 1 ? "s" : ""}`;
                })()}
            </div>

            <div className="bg-card rounded-2xl border overflow-x-auto">
                <table className="w-full text-sm">
                    {view === "entries" && (
                        <>
                            <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                <tr><th className="text-left px-4 py-2.5">Member</th><th className="text-left px-4 py-2.5">Hrs</th><th className="text-left px-4 py-2.5">Type</th><th className="text-left px-4 py-2.5">Activity</th><th className="text-left px-4 py-2.5">Date</th><th className="text-left px-4 py-2.5">Status</th><th className="text-right px-4 py-2.5">Actions</th></tr>
                            </thead>
                            <tbody>
                                {(memberQuery.trim()
                                    ? rows.filter((h) => (h.user_name || "").toLowerCase().includes(memberQuery.toLowerCase().trim()))
                                    : rows
                                ).map((h) => (
                                    <tr key={h.id} className="border-t border-border" data-testid={`hours-report-row-${h.id}`}>
                                        <td className="px-4 py-2.5">{h.user_name}</td>
                                        <td className="px-4 py-2.5 font-bold">{h.hours}</td>
                                        <td className="px-4 py-2.5 text-xs">{h.event_type}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground max-w-sm truncate">{h.activity || h.description}</td>
                                        <td className="px-4 py-2.5 text-muted-foreground">{h.date && formatCalendarDay(h.date, "MMM d, yyyy")}</td>
                                        <td className="px-4 py-2.5 text-xs uppercase tracking-wider font-semibold">{h.status}</td>
                                        <td className="px-4 py-2.5 text-right whitespace-nowrap">
                                            <FullEditHoursDialog
                                                h={h}
                                                onSaved={run}
                                                trigger={
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                                                        data-testid={`hours-report-edit-${h.id}`}
                                                        title="Edit this entry"
                                                    >
                                                        <Pencil className="h-3.5 w-3.5" />
                                                    </Button>
                                                }
                                            />
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                                                data-testid={`hours-report-delete-${h.id}`}
                                                title="Delete this entry"
                                                onClick={async () => {
                                                    if (!confirm(`Delete ${h.user_name}'s ${h.hours}h entry on ${h.date ? formatCalendarDay(h.date, "MMM d, yyyy") : "unknown date"}?\n\nThis cannot be undone.`)) return;
                                                    try {
                                                        await api.delete(`/hours/${h.id}`);
                                                        toast.success("Hours entry deleted");
                                                        run();
                                                    } catch (e) {
                                                        toast.error(e.response?.data?.detail || "Could not delete");
                                                    }
                                                }}
                                            >
                                                <Trash2 className="h-3.5 w-3.5" />
                                            </Button>
                                        </td>
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
    const [year, setYear] = useState(String(now.getFullYear()));
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
        const p = {};
        if (year !== "all") {
            p.year = year;
            if (period.startsWith("q")) p.quarter = period.slice(1);
            else if (period.startsWith("m")) p.month = period.slice(1);
        }
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
        const fname = `donations-${view}-${year === "all" ? "all-years" : year}${year !== "all" && period !== "all" ? "-" + period : ""}.csv`;
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
                    <FilterSelect label="Year" value={year} onChange={setYear} options={[{ value: "all", label: "All years" }, ...years.map((y) => ({ value: String(y), label: String(y) }))]} testid="donations-filter-year" />
                    <div>
                        <Label className="text-xs">Period</Label>
                        <Select value={period} onValueChange={setPeriod} disabled={year === "all"}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="donations-filter-period"><SelectValue placeholder={year === "all" ? "—" : ""} /></SelectTrigger>
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

    async function downloadPdf(userId, { detailed = false } = {}) {
        if (!userId) return;
        try {
            const url = `/reports/personnel-brief/${userId}/pdf${detailed ? "?detailed=true" : ""}`;
            const res = await api.get(url, { responseType: "blob" });
            const blob = new Blob([res.data], { type: "application/pdf" });
            const objUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = objUrl;
            const m = members.find((x) => x.id === userId);
            const safe = (m?.name || "member").replace(/\s+/g, "_");
            a.download = `personnel-data-brief${detailed ? "-detailed" : ""}-${safe}.pdf`;
            a.click();
            URL.revokeObjectURL(objUrl);
        } catch {
            // server error already toasts via interceptor
        }
    }

    return (
        <div>
            <div className="bg-card rounded-2xl border p-5 max-w-2xl">
                <div className="flex items-center gap-2 text-sm font-semibold mb-3"><FileText className="h-4 w-4" /> Generate brief</div>
                <Label className="text-xs">Member</Label>
                <Select value={chosen} onValueChange={setChosen}>
                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="brief-member-select"><SelectValue placeholder="Pick a member…" /></SelectTrigger>
                    <SelectContent className="max-h-80">
                        {members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} — {m.email}</SelectItem>)}
                    </SelectContent>
                </Select>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4">
                    <Button
                        onClick={() => downloadPdf(chosen, { detailed: false })}
                        disabled={!chosen}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid="brief-pdf-one-pager-btn"
                    >
                        <Download className="h-4 w-4 mr-1.5" />Personnel Data Brief
                    </Button>
                    <Button
                        onClick={() => downloadPdf(chosen, { detailed: true })}
                        disabled={!chosen}
                        variant="outline"
                        className="rounded-full border-2 border-primary text-primary hover:bg-primary/10"
                        data-testid="brief-pdf-detailed-btn"
                    >
                        <Download className="h-4 w-4 mr-1.5" />Detailed Data Brief
                    </Button>
                </div>
                <p className="text-[11px] text-muted-foreground mt-2 leading-snug">
                    <span className="font-semibold">Personnel Data Brief</span> is a one-page ORB-style landscape summary.<br />
                    <span className="font-semibold">Detailed Data Brief</span> includes the one-pager + multi-page attachments listing every degree, language, award, donation, hour, and assignment in full.
                </p>
                <Button onClick={load} disabled={!chosen} variant="ghost" size="sm" className="mt-2 text-xs text-muted-foreground hover:text-foreground" data-testid="brief-generate-btn">
                    Preview on screen instead →
                </Button>
            </div>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-6xl max-h-[92vh] overflow-y-auto" data-testid="brief-dialog">
                    <DialogHeader className="print:pb-2 print:border-b print:border-black">
                        <DialogTitle className="font-heading text-2xl flex items-center justify-between gap-3">
                            Personnel Data Brief
                            <div className="flex gap-2 print:hidden">
                                <Button size="sm" onClick={() => downloadPdf(chosen, { detailed: false })} variant="outline" className="rounded-full" data-testid="brief-dialog-pdf-one-btn">
                                    <Download className="h-4 w-4 mr-1.5" />One-pager
                                </Button>
                                <Button size="sm" onClick={() => downloadPdf(chosen, { detailed: true })} variant="outline" className="rounded-full" data-testid="brief-dialog-pdf-detailed-btn">
                                    <Download className="h-4 w-4 mr-1.5" />Detailed
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
        <div className="space-y-4 print:text-black" data-testid="brief-body">
            {/* ORB-style header strip — wide identity bar with right-aligned meta */}
            <div className="flex items-start gap-4 border-b-2 border-primary pb-4">
                {m.avatar_url ? (
                    <img src={mediaUrl(m.avatar_url)} alt="" className="w-20 h-20 rounded-md object-contain border border-border shrink-0" />
                ) : (
                    <div className="w-20 h-20 rounded-md bg-primary/15 text-primary grid place-items-center font-heading font-black text-3xl shrink-0">
                        {(m.name || m.email)[0]?.toUpperCase()}
                    </div>
                )}
                <div className="flex-1 min-w-0">
                    <div className="font-heading text-2xl font-black leading-tight uppercase tracking-wide">{m.title ? `${m.title} ` : ""}{m.name}</div>
                    {m.line_name && <div className="text-xs font-bold uppercase tracking-widest text-primary mt-0.5">&ldquo;{m.line_name}&rdquo;</div>}
                    <div className="text-xs text-muted-foreground mt-1">
                        {[m.email, m.phone].filter(Boolean).join(" · ")}
                    </div>
                </div>
                <div className="text-[10px] tabular-nums shrink-0 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 min-w-[180px]" data-testid="brief-orb-meta">
                    <span className="font-bold text-muted-foreground uppercase">Member ID</span><span className="font-semibold">{(m.id || "").slice(0, 8).toUpperCase()}</span>
                    <span className="font-bold text-muted-foreground uppercase">Status</span><span className="font-semibold">{(m.status || "—").toUpperCase()}</span>
                    <span className="font-bold text-muted-foreground uppercase">Chapter</span><span className="font-semibold">{(chapter.name || "—").toUpperCase()}</span>
                    <span className="font-bold text-muted-foreground uppercase">Tier</span><span className="font-semibold">{(tier.name || "—").toUpperCase()}</span>
                    <span className="font-bold text-muted-foreground uppercase">Joined</span><span className="font-semibold">{(m.join_date || m.created_at || "—").slice(0, 10)}</span>
                    <span className="font-bold text-muted-foreground uppercase">Renewal</span><span className="font-semibold">{(m.membership_expires_at || "—").slice(0, 10)}</span>
                </div>
            </div>

            {/* ORB-style 3-column summary tiles */}
            <OrbSummary b={b} awardsGrouped={[...awardsGrouped].sort((a, c) => (c.last_granted_at || "").localeCompare(a.last_granted_at || ""))} currentYear={currentYear} />

            <div className="text-[11px] uppercase tracking-widest font-bold text-muted-foreground border-b border-border pb-1">
                ▼ Detailed Record (Attachments)
            </div>

            <BriefSection num="I" title="Personal Data">
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

            <BriefSection num="II" title="Organization">
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

            <BriefSection num="III" title="Civilian Education">
                {degrees.length === 0 ? <Empty /> : <TableLike headers={["Level", "Type", "Field", "Institution", "Graduated"]} rows={degrees.map((d) => [
                    d.degree_level || "—",
                    d.degree_type || "—",
                    d.field_of_study || "—",
                    d.institution || "—",
                    `${["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.graduation_month || 0]} ${d.graduation_year || ""}`.trim() || "—",
                ])} />}
            </BriefSection>

            <BriefSection num="IV" title="Language Proficiency">
                {languages.length === 0 ? <Empty /> : <TableLike headers={["Language", "Speaking", "Reading", "Writing", "Year"]} rows={languages.map((l) => [
                    l.language || "—", l.speaking || "—", l.reading || "—", l.writing || "—", String(l.year_accomplished || "—"),
                ])} />}
            </BriefSection>

            <BriefSection num="V" title="Financial Obligations (Annual Dues)">
                {dues.length === 0 ? <Empty /> : <TableLike headers={["Date", "Amount", "Status", "Description"]} rows={dues.map((t) => [
                    (t.created_at || "").slice(0, 10),
                    `$${(t.amount || 0).toFixed(2)}`,
                    (t.status || "—").toUpperCase(),
                    t.description || "—",
                ])} />}
            </BriefSection>

            <BriefSection num="VI" title="Donations">
                {donations.length === 0 ? <Empty /> : <TableLike headers={["Date", "Cause", "Amount"]} rows={donations.map((t) => [
                    (t.created_at || "").slice(0, 10),
                    t.description || "General fund",
                    `$${(t.amount || 0).toFixed(2)}`,
                ])} />}
            </BriefSection>

            <BriefSection num="VII" title={`Community Service (${currentYear})`}>
                {hoursCY.length === 0 ? <Empty /> : <TableLike headers={["Agency", "Event Type", "Hours", "Status", "Date"]} rows={hoursCY.map((h) => [
                    h.agency_name || "—",
                    (h.event_type || "other").replace("_", " "),
                    String(h.hours || 0),
                    (h.status || "—").toUpperCase(),
                    (h.date || "").slice(0, 10),
                ])} />}
            </BriefSection>

            <BriefSection num="VIII" title="Awards &amp; Decorations">
                {awardsRows.length === 0 ? <Empty /> : <TableLike headers={["Award", "Order", "Latest Date"]} rows={awardsRows} />}
            </BriefSection>

            {(() => {
                const otyAll = b.of_the_year || [];
                const otyRecent = otyAll;  // full list in detail section
                const totalCount = b.of_the_year_count ?? otyAll.length;
                const title = `Of The Year Honors${totalCount > 0 ? ` — ${totalCount} total` : ""}`;
                return (
                    <BriefSection num="IX" title={title}>
                        {otyRecent.length === 0 ? <Empty /> : <TableLike
                            headers={["Year", "Category", "Chapter", "Note"]}
                            rows={otyRecent.map((o) => [
                                String(o.year || "—"),
                                o.category_label || o.category || "—",
                                o.chapter_name || "—",
                                o.note || "",
                            ])}
                        />}
                    </BriefSection>
                );
            })()}

            <BriefSection num="X" title={`Events Attended (${currentYear} check-ins)`}>
                {eventRows.length === 0 ? <Empty /> : <TableLike headers={["Event", "Guests", "Ticket Type", "Check-in Date"]} rows={eventRows.map((e) => [
                    e.title, String(e.guests), e.ticket_type, e.date,
                ])} />}
            </BriefSection>

            <BriefSection num="XI" title="Assignment History">
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
            {/* Inline style so the navy-on-white title always renders — the
                previous arbitrary Tailwind class `bg-[hsl(220_45%_12%)]` was
                colliding with the parent's `print:text-black` and producing
                "black bars with no visible title" per the user's report. */}
            <h3
                className="font-heading text-sm uppercase tracking-widest px-3 py-1.5 rounded mb-2 print:!text-white"
                style={{ backgroundColor: "#0C1B33", color: "#FFFFFF" }}
            >
                <span style={{ opacity: 0.7, marginRight: "0.5rem" }}>SECTION {num} —</span>{title}
            </h3>
            <div className="space-y-1">{children}</div>
        </div>
    );
}

/**
 * ORB-style 3-column summary tiles on page 1 of the brief preview. Mirrors
 * the layout of the landscape PDF. Each column is a stack of small tiles
 * with ALL CAPS section labels and dense data rows.
 */
const OrbKv = ({ k, v }) => (
    <div className="grid grid-cols-[88px_1fr] gap-2 text-[11px] leading-tight border-b border-border/40 py-0.5">
        <span className="text-muted-foreground font-bold uppercase">{k}</span>
        <span className="font-semibold text-foreground/90 truncate">{v || "—"}</span>
    </div>
);
const OrbTile = ({ title, tileTitle, children, "data-testid": testId }) => {
    // Accept BOTH `title` and `tileTitle` props — legacy callers in this file
    // pass `tileTitle` (from when the outer variable was renamed to avoid the
    // ORB component collision). Prior to iter97 the destructure only matched
    // `title`, so every caller sending `tileTitle` produced a navy bar with no
    // visible text (the "black lines" the user reported).
    const label = title ?? tileTitle;
    return (
        <div data-testid={testId}>
            <div
                className="text-[10px] uppercase tracking-[0.15em] font-black px-2 py-1 rounded-sm print:!text-white"
                style={{ backgroundColor: "#0C1B33", color: "#FFFFFF" }}
            >
                {label}
            </div>
            <div className="px-1 pt-1">{children}</div>
        </div>
    );
};
const OrbRow = ({ children }) => (
    <div className="text-[11px] leading-tight border-b border-border/40 py-1">{children}</div>
);

function OrbSummary({ b, awardsGrouped, currentYear }) {
    const m = b.member || {};
    const oty = b.of_the_year_recent || [];
    const otyCount = b.of_the_year_count || 0;
    const assignments = (m.assignment_history || [])
        .slice()
        .sort((a, c) => {
            if (a.is_current && !c.is_current) return -1;
            if (c.is_current && !a.is_current) return 1;
            return (c.start_date || "").localeCompare(a.start_date || "");
        });
    const asnTop = assignments.slice(0, 4);
    const degreesTop = (m.civilian_degrees || []).slice().sort((a, c) => (c.graduation_year || 0) - (a.graduation_year || 0)).slice(0, 3);
    const langsTop = (m.languages || []).slice().sort((a, c) => (c.year_accomplished || 0) - (a.year_accomplished || 0)).slice(0, 3);
    const awardsTop = awardsGrouped.slice(0, 10);
    const checkins = b.checkins || [];
    const eventsCY = checkins.filter((c) => (c.checked_in_at || "").slice(0, 4) === String(currentYear));
    const cyHours = (b.hours || []).filter((h) => (h.date || "").slice(0, 4) === String(currentYear) && h.status === "approved").reduce((s, h) => s + (h.hours || 0), 0);
    const eventLookup = Object.fromEntries((b.events || []).map((e) => [e.id, e]));
    const seen = new Set();
    const recentEvents = [];
    for (const c of [...eventsCY].sort((a, c) => (c.checked_in_at || "").localeCompare(a.checked_in_at || ""))) {
        if (seen.has(c.event_id)) continue;
        seen.add(c.event_id);
        recentEvents.push({ ...c, title: (eventLookup[c.event_id] || {}).title || "—" });
        if (recentEvents.length >= 4) break;
    }
    const Kv = OrbKv;
    const Tile = OrbTile;
    const Row = OrbRow;

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="brief-orb-summary">
            {/* COL 1 */}
            <div className="space-y-3">
                <Tile tileTitle="Section I — Personal Data">
                    <Kv k="Address" v={m.address} />
                    <Kv k="City" v={m.city} />
                    <Kv k="State / Zip" v={[m.state, m.zip_code].filter(Boolean).join(" / ")} />
                    <Kv k="Country" v={m.country} />
                    <Kv k="Birthdate" v={(m.birthdate || "").slice(0, 10)} />
                    <Kv k="Branch" v={m.branch_of_service} />
                </Tile>
                <Tile tileTitle={`Section II — Education (${(m.civilian_degrees || []).length} total)`}>
                    {degreesTop.length === 0 ? <div className="text-[11px] italic text-muted-foreground">None on record.</div>
                        : degreesTop.map((d, i) => (
                            <Row key={i}>
                                <span className="font-bold uppercase">{d.degree_level || "—"}</span> · {d.field_of_study || "—"}
                                <div className="text-muted-foreground">{[d.institution, d.graduation_year].filter(Boolean).join(" · ")}</div>
                            </Row>
                        ))}
                </Tile>
                <Tile tileTitle={`Section III — Languages (${(m.languages || []).length} total)`}>
                    {langsTop.length === 0 ? <div className="text-[11px] italic text-muted-foreground">None on record.</div>
                        : langsTop.map((lg, i) => (
                            <Row key={i}>
                                <span className="font-bold uppercase">{lg.language}</span> · S:{lg.speaking || "—"} R:{lg.reading || "—"} W:{lg.writing || "—"}
                            </Row>
                        ))}
                </Tile>
            </div>
            {/* COL 2 */}
            <div className="space-y-3">
                <Tile tileTitle={`Section IV — Awards & Decorations${awardsGrouped.length > 10 ? ` (Top 10 of ${awardsGrouped.length})` : ""}`}>
                    {awardsTop.length === 0 ? <div className="text-[11px] italic text-muted-foreground">None on record.</div>
                        : awardsTop.map((a, i) => (
                            <Row key={i}>
                                <span className="font-bold">{a.award_name || "—"}</span>
                                {a.count > 1 && <span> × {a.count}</span>}
                                <span className="text-muted-foreground"> · {(a.last_granted_at || "").slice(0, 10)}</span>
                            </Row>
                        ))}
                </Tile>
                <Tile tileTitle={`Section V — Of The Year Honors${otyCount > 7 ? ` (Last 7 of ${otyCount})` : ""}`} data-testid="orb-oty-tile">
                    {oty.length === 0 ? <div className="text-[11px] italic text-muted-foreground">None on record.</div>
                        : oty.map((o) => (
                            <Row key={o.id}>
                                <span className="font-bold text-primary">{o.year}</span> · <span className="uppercase">{o.category_label || o.category}</span>
                                <div className="text-muted-foreground">{[o.chapter_name, o.note].filter(Boolean).join(" · ")}</div>
                            </Row>
                        ))}
                </Tile>
            </div>
            {/* COL 3 */}
            <div className="space-y-3">
                <Tile tileTitle={`Section VI — Assignment History${assignments.length > 4 ? ` (Recent 4 of ${assignments.length})` : ""}`}>
                    {asnTop.length === 0 ? <div className="text-[11px] italic text-muted-foreground">None on record.</div>
                        : asnTop.map((a, i) => (
                            <Row key={i}>
                                <span className="font-bold">{(a.start_date || "").slice(0, 7) || "—"} — {a.is_current ? "PRESENT" : ((a.end_date || "").slice(0, 7) || "—")}</span>
                                <div className="text-muted-foreground">{[a.chapter_name, a.duty_title, a.rank].filter(Boolean).join(" · ")}</div>
                            </Row>
                        ))}
                </Tile>
                <Tile tileTitle="Section VII — Service Statistics">
                    <Kv k={`CY ${currentYear} Hours`} v={cyHours.toFixed(1)} />
                    <Kv k="Lifetime Hours" v={(b.approved_hours || 0).toFixed(1)} />
                    <Kv k="Pending Hours" v={(b.pending_hours || 0).toFixed(1)} />
                    <Kv k="Total Paid" v={`$${(b.total_paid || 0).toFixed(2)}`} />
                    <Kv k={`Events CY ${currentYear}`} v={String(eventsCY.length)} />
                    <Kv k="Awards Held" v={`${awardsGrouped.length} (distinct)`} />
                    <Kv k="OTY Honors" v={String(otyCount)} />
                </Tile>
                <Tile tileTitle={`Section VIII — Recent Events (${currentYear})`}>
                    {recentEvents.length === 0 ? <div className="text-[11px] italic text-muted-foreground">No check-ins this year.</div>
                        : recentEvents.map((e) => (
                            <Row key={e.id || e.event_id}>
                                <span className="font-bold">{e.title}</span>
                                <span className="text-muted-foreground"> · {(e.checked_in_at || "").slice(0, 10)}</span>
                                <div className="text-muted-foreground uppercase">{(e.ticket_type || "general").replace("_", " ")}</div>
                            </Row>
                        ))}
                </Tile>
            </div>
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
                                <td className="px-4 py-2.5 text-xs whitespace-nowrap">{r.granted_at ? formatCalendarDay(r.granted_at, "MMM d, yyyy") : "—"}</td>
                                <td className="px-4 py-2.5">
                                    <div className="flex items-center gap-2">
                                        {r.user_avatar_url ? (
                                            <img src={mediaUrl(r.user_avatar_url)} alt="" className="w-7 h-7 rounded-full object-contain border border-border" />
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
                                            <img src={mediaUrl(r.user_avatar_url || r.chapter_logo_url)} alt="" className="w-7 h-7 rounded-full object-contain border border-border" />
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
