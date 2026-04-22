import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Users, Calendar, DollarSign, TrendingUp, AlertCircle, Newspaper, FileText, Sparkles } from "lucide-react";
import { format, parseISO } from "date-fns";
import {
    ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip,
    PieChart, Pie, Cell, Legend
} from "recharts";

const PALETTE = ["#E86A58", "#F9D466", "#A5C4B4", "#D4A574", "#8B9DC3"];

export default function AdminDashboard() {
    const [stats, setStats] = useState(null);
    const [err, setErr] = useState("");

    useEffect(() => {
        api.get("/admin/stats").then(({ data }) => setStats(data)).catch((e) => setErr(e.message));
    }, []);

    if (err) return <div className="text-destructive" data-testid="dashboard-error">{err}</div>;
    if (!stats)
        return (
            <div className="grid md:grid-cols-4 gap-4" data-testid="dashboard-loading">
                {[1, 2, 3, 4].map((i) => <div key={i} className="h-32 rounded-2xl bg-muted animate-pulse" />)}
            </div>
        );

    const { members, events, content, dues } = stats;

    return (
        <div className="space-y-6" data-testid="admin-dashboard">
            {/* KPI cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <Kpi
                    icon={<Users className="h-5 w-5" />}
                    label="Total members"
                    value={members.total}
                    sub={`${members.new_this_month} new this month`}
                    tint="bg-primary/15 text-primary"
                    testid="kpi-members"
                />
                <Kpi
                    icon={<Calendar className="h-5 w-5" />}
                    label="Upcoming events"
                    value={events.upcoming}
                    sub={`${events.total_rsvps} total RSVPs`}
                    tint="bg-accent/40 text-[hsl(34_8%_16%)]"
                    testid="kpi-events"
                />
                <Kpi
                    icon={<DollarSign className="h-5 w-5" />}
                    label="Active revenue (est.)"
                    value={`$${dues.active_revenue_estimate.toLocaleString()}`}
                    sub={`$${dues.annual_fee}/member/year`}
                    tint="bg-secondary/60 text-[hsl(34_8%_16%)]"
                    testid="kpi-revenue"
                />
                <Kpi
                    icon={<AlertCircle className="h-5 w-5" />}
                    label="Expiring in 30d"
                    value={members.expiring_soon}
                    sub={`$${dues.potential_expiring_revenue.toLocaleString()} at risk`}
                    tint="bg-destructive/15 text-destructive"
                    testid="kpi-expiring"
                />
            </div>

            {/* Charts */}
            <div className="grid lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-card rounded-2xl border border-border p-6 shadow-warm" data-testid="growth-chart">
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <h3 className="font-heading font-semibold text-lg">Member growth</h3>
                            <p className="text-sm text-muted-foreground">New joins over the last 6 months</p>
                        </div>
                        <TrendingUp className="h-5 w-5 text-primary" />
                    </div>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={members.growth} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="hsl(40 20% 88%)" />
                                <XAxis dataKey="month" stroke="hsl(34 5% 45%)" style={{ fontSize: 12 }} />
                                <YAxis allowDecimals={false} stroke="hsl(34 5% 45%)" style={{ fontSize: 12 }} />
                                <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(40 20% 88%)" }} />
                                <Line
                                    type="monotone"
                                    dataKey="members"
                                    stroke="hsl(11 74% 63%)"
                                    strokeWidth={3}
                                    dot={{ r: 5, fill: "hsl(11 74% 63%)" }}
                                    activeDot={{ r: 7 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-card rounded-2xl border border-border p-6 shadow-warm" data-testid="tier-chart">
                    <h3 className="font-heading font-semibold text-lg">By membership tier</h3>
                    <p className="text-sm text-muted-foreground">Distribution across tiers</p>
                    <div className="h-64 mt-2">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={members.by_tier}
                                    dataKey="count"
                                    nameKey="tier"
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={50}
                                    outerRadius={80}
                                    paddingAngle={3}
                                >
                                    {members.by_tier.map((_, i) => (
                                        <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ borderRadius: 12 }} />
                                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Second row: top events + expiring */}
            <div className="grid lg:grid-cols-2 gap-6">
                <div className="bg-card rounded-2xl border border-border p-6 shadow-warm" data-testid="top-events">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-heading font-semibold text-lg">Top events by RSVPs</h3>
                        <Link to="/events" className="text-xs text-primary hover:underline">View all</Link>
                    </div>
                    <div className="space-y-3">
                        {events.top_by_rsvp.length === 0 && <div className="text-sm text-muted-foreground">No events yet.</div>}
                        {events.top_by_rsvp.map((e, idx) => (
                            <div key={e.id} className="flex items-center gap-3" data-testid={`top-event-${e.id}`}>
                                <div className="w-8 h-8 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold text-sm">
                                    {idx + 1}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-medium truncate">{e.title}</div>
                                    <div className="text-xs text-muted-foreground">
                                        {format(parseISO(e.start_at), "MMM d")} · {e.location || "TBA"}
                                    </div>
                                </div>
                                <div className="text-sm font-heading font-bold">{e.rsvp_count}</div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="bg-card rounded-2xl border border-border p-6 shadow-warm" data-testid="expiring-memberships">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-heading font-semibold text-lg">Memberships expiring soon</h3>
                        <span className="text-xs bg-destructive/10 text-destructive rounded-full px-2.5 py-0.5 font-semibold">
                            Next 30 days
                        </span>
                    </div>
                    {members.expiring_list.length === 0 ? (
                        <div className="text-sm text-muted-foreground py-6 text-center">
                            🌱 Nobody's expiring soon. You're all caught up.
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {members.expiring_list.map((m) => (
                                <div key={m.id} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0" data-testid={`expiring-${m.id}`}>
                                    <div>
                                        <div className="font-medium text-sm">{m.name}</div>
                                        <div className="text-xs text-muted-foreground">{m.email}</div>
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {m.expires_at && format(parseISO(m.expires_at), "MMM d")}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Third row: upcoming + content summary */}
            <div className="grid lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-card rounded-2xl border border-border p-6 shadow-warm" data-testid="next-events">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-heading font-semibold text-lg">Next up on the calendar</h3>
                    </div>
                    {events.next_up.length === 0 ? (
                        <div className="text-sm text-muted-foreground">No upcoming events.</div>
                    ) : (
                        <div className="space-y-3">
                            {events.next_up.map((e) => (
                                <Link
                                    key={e.id}
                                    to={`/events/${e.id}`}
                                    className="flex items-center gap-4 p-3 rounded-xl hover:bg-muted/50 transition-colors"
                                >
                                    <div className="w-14 h-14 rounded-xl bg-secondary/30 grid place-items-center text-center shrink-0">
                                        <div>
                                            <div className="text-[10px] font-semibold uppercase text-primary">
                                                {format(parseISO(e.start_at), "MMM")}
                                            </div>
                                            <div className="font-heading text-lg font-black leading-none">
                                                {format(parseISO(e.start_at), "d")}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium truncate">{e.title}</div>
                                        <div className="text-xs text-muted-foreground">
                                            {format(parseISO(e.start_at), "h:mm a")} · {e.location || "TBA"}
                                        </div>
                                    </div>
                                    <div className="text-xs text-muted-foreground">{e.rsvp_count} going</div>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>

                <div className="space-y-4">
                    <MiniCard icon={<Newspaper className="h-5 w-5" />} label="News articles" value={content.news} />
                    <MiniCard icon={<FileText className="h-5 w-5" />} label="CMS pages" value={content.pages} />
                    <div className="bg-gradient-to-br from-primary/10 via-secondary/20 to-accent/15 rounded-2xl p-5 border border-border">
                        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider">
                            <Sparkles className="h-4 w-4 text-primary" /> Tip
                        </div>
                        <div className="mt-2 text-sm leading-relaxed">
                            {members.expiring_soon > 0
                                ? `Send a renewal reminder — ${members.expiring_soon} member${members.expiring_soon > 1 ? "s" : ""} expiring soon. Use the AI email draft in the News tab.`
                                : "No urgent reminders. Draft a welcome-back email with the AI tool to keep momentum."}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function Kpi({ icon, label, value, sub, tint, testid }) {
    return (
        <div className="bg-card rounded-2xl border border-border p-5 shadow-warm" data-testid={testid}>
            <div className={`w-10 h-10 rounded-full grid place-items-center ${tint}`}>{icon}</div>
            <div className="mt-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">{label}</div>
            <div className="font-heading text-3xl font-black mt-1 tracking-tight">{value}</div>
            <div className="text-xs text-muted-foreground mt-1">{sub}</div>
        </div>
    );
}

function MiniCard({ icon, label, value }) {
    return (
        <div className="bg-card rounded-2xl border border-border p-5 flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-muted grid place-items-center text-muted-foreground">{icon}</div>
            <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">{label}</div>
                <div className="font-heading text-2xl font-black">{value}</div>
            </div>
        </div>
    );
}
