import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { format, parseISO, differenceInDays } from "date-fns";
import { toast } from "sonner";
import { Calendar, MapPin, Trophy, Clock, Medal, Star, Heart, GraduationCap, Sparkles, Award as AwardIcon, Building2 } from "lucide-react";

const ICON_MAP = { medal: Medal, star: Star, heart: Heart, "graduation-cap": GraduationCap, sparkles: Sparkles, trophy: Trophy, award: AwardIcon };

export default function Profile() {
    const { user, setUser } = useAuth();
    const [params] = useSearchParams();
    const [tab, setTab] = useState(params.get("tab") || "profile");
    const [form, setForm] = useState({ name: "", bio: "", city: "", interests: "", avatar_url: "" });
    const [events, setEvents] = useState([]);
    const [awards, setAwards] = useState([]);
    const [hoursEntries, setHoursEntries] = useState([]);
    const [chapter, setChapter] = useState(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (user) {
            setForm({
                name: user.name || "",
                bio: user.bio || "",
                city: user.city || "",
                interests: (user.interests || []).join(", "),
                avatar_url: user.avatar_url || "",
            });
            if (user.chapter_id) {
                api.get("/chapters").then(({ data }) => {
                    setChapter(data.find((c) => c.id === user.chapter_id) || null);
                }).catch(() => {});
            }
        }
        api.get("/me/events").then(({ data }) => setEvents(data)).catch(() => {});
        api.get("/me/awards").then(({ data }) => setAwards(data)).catch(() => {});
        api.get("/me/hours").then(({ data }) => setHoursEntries(data)).catch(() => {});
    }, [user]);

    async function save(e) {
        e.preventDefault();
        setSaving(true);
        try {
            const { data } = await api.put("/members/me", {
                name: form.name,
                bio: form.bio,
                city: form.city,
                interests: form.interests.split(",").map((s) => s.trim()).filter(Boolean),
                avatar_url: form.avatar_url,
            });
            setUser(data);
            toast.success("Profile updated");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to save");
        }
        setSaving(false);
    }

    async function renew() {
        try {
            const { data } = await api.post("/members/me/renew");
            setUser(data);
            toast.success("Membership renewed for another year! 🎉");
        } catch {
            toast.error("Renewal failed");
        }
    }

    if (!user) return null;
    const daysLeft = user.membership_expires_at ? differenceInDays(parseISO(user.membership_expires_at), new Date()) : 0;
    const approvedHours = hoursEntries.filter((h) => h.status === "approved").reduce((s, h) => s + h.hours, 0);

    return (
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-10">
            <div className="flex items-center gap-5 mb-8">
                <Avatar className="h-20 w-20 border-2 border-white shadow-warm">
                    {user.avatar_url && <AvatarImage src={user.avatar_url} />}
                    <AvatarFallback className="bg-primary/15 text-primary text-2xl font-bold">
                        {user.name?.[0]?.toUpperCase()}
                    </AvatarFallback>
                </Avatar>
                <div>
                    <h1 className="font-heading text-3xl sm:text-4xl font-bold tracking-tight">{user.name}</h1>
                    <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 mt-1">
                        <span>{user.email}</span>
                        {chapter && <span className="inline-flex items-center gap-1"><Building2 className="h-4 w-4" /> {chapter.name}</span>}
                        {user.membership_tier && <span className="text-xs bg-accent/40 rounded-full px-2.5 py-0.5 font-semibold uppercase tracking-wider">{user.membership_tier}</span>}
                    </div>
                </div>
            </div>

            <div className="rounded-2xl bg-gradient-to-br from-primary/15 via-secondary/25 to-accent/20 p-6 border border-border mb-8" data-testid="membership-card">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <div className="text-xs uppercase tracking-wider font-semibold">{user.membership_tier} membership</div>
                        <div className="font-heading text-2xl font-bold mt-1">
                            {user.within_grace ? <span className="text-destructive">In grace period — renew soon</span> : daysLeft > 0 ? `${daysLeft} days remaining` : "Expired"}
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                            Expires {user.membership_expires_at && format(parseISO(user.membership_expires_at), "MMM d, yyyy")}
                            {user.within_grace && " · 30-day grace active"}
                        </div>
                    </div>
                    <Button onClick={renew} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="renew-btn">
                        Renew for 1 year
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-8">
                <div className="bg-card rounded-2xl border border-border p-5" data-testid="stat-awards">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground font-semibold"><Trophy className="h-4 w-4" /> Awards</div>
                    <div className="font-heading text-3xl font-black mt-1">{awards.length}</div>
                </div>
                <div className="bg-card rounded-2xl border border-border p-5" data-testid="stat-hours">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground font-semibold"><Clock className="h-4 w-4" /> Approved hours</div>
                    <div className="font-heading text-3xl font-black mt-1">{approvedHours.toFixed(1)}</div>
                </div>
                <div className="bg-card rounded-2xl border border-border p-5" data-testid="stat-events">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground font-semibold"><Calendar className="h-4 w-4" /> Events</div>
                    <div className="font-heading text-3xl font-black mt-1">{events.length}</div>
                </div>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="profile" className="rounded-full data-[state=active]:bg-background" data-testid="tab-profile">Profile</TabsTrigger>
                    <TabsTrigger value="awards" className="rounded-full data-[state=active]:bg-background" data-testid="tab-awards">Awards ({awards.length})</TabsTrigger>
                    <TabsTrigger value="hours" className="rounded-full data-[state=active]:bg-background" data-testid="tab-hours">Hours ({hoursEntries.length})</TabsTrigger>
                    <TabsTrigger value="events" className="rounded-full data-[state=active]:bg-background" data-testid="tab-events">Events ({events.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="profile" className="mt-6">
                    <form onSubmit={save} className="bg-card rounded-2xl p-6 border border-border shadow-warm grid sm:grid-cols-2 gap-5" data-testid="profile-form">
                        <div className="sm:col-span-2"><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-name" /></div>
                        <div><Label>City</Label><Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-city" /></div>
                        <div><Label>Avatar URL</Label><Input value={form.avatar_url} onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-avatar" /></div>
                        <div className="sm:col-span-2"><Label>Interests (comma separated)</Label><Input value={form.interests} onChange={(e) => setForm({ ...form, interests: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-interests" /></div>
                        <div className="sm:col-span-2"><Label>Bio</Label><Textarea rows={4} value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-bio" /></div>
                        <div className="sm:col-span-2 flex justify-end">
                            <Button type="submit" disabled={saving} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="profile-save-btn">{saving ? "Saving…" : "Save changes"}</Button>
                        </div>
                    </form>
                </TabsContent>

                <TabsContent value="awards" className="mt-6">
                    {awards.length === 0 ? (
                        <div className="text-muted-foreground">No awards yet. Keep showing up! 🌟</div>
                    ) : (
                        <div className="grid sm:grid-cols-2 gap-4">
                            {awards.map((g) => {
                                const Icon = ICON_MAP[g.award_icon] || Trophy;
                                return (
                                    <div key={g.id} className="bg-card rounded-2xl border border-border p-5 flex items-center gap-4">
                                        <div className="w-14 h-14 rounded-2xl grid place-items-center" style={{ backgroundColor: `${g.award_color}33`, color: g.award_color }}>
                                            <Icon className="h-7 w-7" />
                                        </div>
                                        <div>
                                            <div className="font-heading font-semibold">{g.award_name}</div>
                                            <div className="text-xs text-muted-foreground">{g.granted_at && format(parseISO(g.granted_at), "MMM d, yyyy")}</div>
                                            {g.reason && <div className="text-xs italic mt-1">{g.reason}</div>}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="hours" className="mt-6">
                    <div className="mb-4">
                        <Link to="/hours" className="text-primary font-medium hover:underline">Go to volunteer hours →</Link>
                    </div>
                    {hoursEntries.length === 0 ? (
                        <div className="text-muted-foreground">No hours logged yet.</div>
                    ) : (
                        <div className="space-y-3">
                            {hoursEntries.slice(0, 10).map((h) => (
                                <div key={h.id} className="bg-card rounded-2xl border border-border p-4 flex items-center gap-4">
                                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold text-sm">{h.hours}</div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm">{h.description}</div>
                                        <div className="text-xs text-muted-foreground">{h.date && format(parseISO(h.date), "MMM d, yyyy")}</div>
                                    </div>
                                    <span className={`text-[10px] uppercase tracking-wider font-semibold rounded-full px-2.5 py-0.5 ${h.status === "approved" ? "bg-accent/40" : h.status === "rejected" ? "bg-destructive/15 text-destructive" : "bg-secondary/40"}`}>
                                        {h.status}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="events" className="mt-6 space-y-4">
                    {events.length === 0 && <div className="text-muted-foreground">You haven't RSVPed to any events yet. <Link to="/events" className="text-primary">Browse events →</Link></div>}
                    {events.map((e) => (
                        <Link key={e.id} to={`/events/${e.id}`} className="block bg-card rounded-2xl p-5 border border-border hover:shadow-warm transition-all" data-testid={`my-event-${e.id}`}>
                            <div className="font-heading font-semibold text-lg">{e.title}</div>
                            <div className="mt-2 flex items-center gap-5 text-sm text-muted-foreground">
                                <span className="inline-flex items-center gap-1.5"><Calendar className="h-4 w-4" /> {format(parseISO(e.start_at), "EEE, MMM d · h:mm a")}</span>
                                <span className="inline-flex items-center gap-1.5"><MapPin className="h-4 w-4" /> {e.location}</span>
                            </div>
                        </Link>
                    ))}
                </TabsContent>
            </Tabs>
        </div>
    );
}
