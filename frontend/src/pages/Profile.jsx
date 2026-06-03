import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Switch } from "../components/ui/switch";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { format, parseISO, differenceInDays } from "date-fns";
import { toast } from "sonner";
import {
    Calendar, MapPin, Trophy, Clock, Medal, Star, Heart, GraduationCap, Sparkles,
    Award as AwardIcon, Building2, Lock, DollarSign, Activity, Phone, AtSign,
    Facebook, Instagram, Linkedin, Twitter, Youtube, Globe,
} from "lucide-react";
import PayPalCheckout from "../components/PayPalCheckout";
import ZeffyCheckout from "../components/ZeffyCheckout";
import AvatarUploader from "../components/AvatarUploader";

const ICON_MAP = { medal: Medal, star: Star, heart: Heart, "graduation-cap": GraduationCap, sparkles: Sparkles, trophy: Trophy, award: AwardIcon };

export default function Profile() {
    const { user, setUser } = useAuth();
    const [params] = useSearchParams();
    const [tab, setTab] = useState(params.get("tab") || "profile");
    const [form, setForm] = useState({
        first_name: "", middle_name: "", last_name: "", line_name: "",
        intake_line: "", intake_completed_at: "",
        username: "", phone: "", bio: "", city: "", address: "", state: "", zip_code: "", country: "",
        birthdate: "", interests: "", avatar_url: "", chapter_id: "",
    });
    const [pwd, setPwd] = useState({ current: "", next: "", confirm: "" });
    const [chapters, setChapters] = useState([]);
    const [events, setEvents] = useState([]);
    const [awards, setAwards] = useState([]);
    const [hoursEntries, setHoursEntries] = useState([]);
    const [transactions, setTransactions] = useState([]);
    const [activity, setActivity] = useState([]);
    const [saving, setSaving] = useState(false);
    const [changingPwd, setChangingPwd] = useState(false);

    useEffect(() => {
        if (user) {
            setForm({
                first_name: user.first_name || "",
                middle_name: user.middle_name || "",
                last_name: user.last_name || "",
                line_name: user.line_name || "",
                intake_line: user.intake_line || "",
                intake_completed_at: user.intake_completed_at || "",
                username: user.username || "",
                phone: user.phone || "",
                bio: user.bio || "",
                city: user.city || "",
                address: user.address || "",
                state: user.state || "",
                zip_code: user.zip_code || "",
                country: user.country || "",
                birthdate: user.birthdate ? user.birthdate.slice(0, 10) : "",
                interests: (user.interests || []).join(", "),
                avatar_url: user.avatar_url || "",
                chapter_id: user.chapter_id || "",
                facebook_url: user.facebook_url || "",
                instagram_url: user.instagram_url || "",
                linkedin_url: user.linkedin_url || "",
                tiktok_url: user.tiktok_url || "",
                twitter_url: user.twitter_url || "",
                pinterest_url: user.pinterest_url || "",
                youtube_url: user.youtube_url || "",
                website_url: user.website_url || "",
            });
        }
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
        api.get("/me/events").then(({ data }) => setEvents(data)).catch(() => {});
        api.get("/me/awards").then(({ data }) => setAwards(data)).catch(() => {});
        api.get("/me/hours").then(({ data }) => setHoursEntries(data)).catch(() => {});
        api.get("/me/transactions").then(({ data }) => setTransactions(data)).catch(() => {});
        api.get("/me/activity").then(({ data }) => setActivity(data)).catch(() => {});
    }, [user]);

    async function save(e) {
        e.preventDefault();
        setSaving(true);
        try {
            const payload = {
                first_name: form.first_name, middle_name: form.middle_name, last_name: form.last_name,
                line_name: form.line_name, intake_line: form.intake_line, intake_completed_at: form.intake_completed_at,
                username: form.username, phone: form.phone,
                bio: form.bio, city: form.city, address: form.address,
                state: form.state, zip_code: form.zip_code, country: form.country,
                birthdate: form.birthdate,
                interests: form.interests.split(",").map((s) => s.trim()).filter(Boolean),
                avatar_url: form.avatar_url,
                facebook_url: form.facebook_url, instagram_url: form.instagram_url,
                linkedin_url: form.linkedin_url, tiktok_url: form.tiktok_url,
                twitter_url: form.twitter_url, pinterest_url: form.pinterest_url,
                youtube_url: form.youtube_url, website_url: form.website_url,
            };
            const { data } = await api.put("/members/me", payload);
            // Chapter is a separate endpoint
            if (form.chapter_id && form.chapter_id !== user.chapter_id) {
                const { data: data2 } = await api.put(`/members/${user.id}/chapter`, { chapter_id: form.chapter_id });
                setUser(data2);
            } else {
                setUser(data);
            }
            // Notify the user if the intake change is waiting on admin approval
            if (form.intake_completed_at && form.intake_completed_at !== (user.intake_completed_at || "") && data.pending_intake_completed_at) {
                toast.success("Profile saved. Your intake completion date change is pending admin approval.", { duration: 6500 });
            } else {
                toast.success("Profile updated");
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to save");
        }
        setSaving(false);
    }

    async function changePassword(e) {
        e.preventDefault();
        if (pwd.next !== pwd.confirm) { toast.error("New passwords don't match"); return; }
        if (pwd.next.length < 6) { toast.error("Password must be 6+ chars"); return; }
        setChangingPwd(true);
        try {
            await api.post("/auth/change-password", { current_password: pwd.current, new_password: pwd.next });
            toast.success("Password updated");
            setPwd({ current: "", next: "", confirm: "" });
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed");
        }
        setChangingPwd(false);
    }

    if (!user) return null;
    const daysLeft = user.membership_expires_at ? differenceInDays(parseISO(user.membership_expires_at), new Date()) : 0;
    const approvedHours = hoursEntries.filter((h) => h.status === "approved").reduce((s, h) => s + h.hours, 0);
    const totalPaid = transactions.filter((t) => t.status === "completed" && ["renewal", "donation", "fee"].includes(t.type)).reduce((s, t) => s + (t.amount || 0), 0);

    return (
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-10">
            <div className="flex items-center gap-5 mb-8">
                <AvatarUploader
                    user={user}
                    onUpdated={async (newUrl) => {
                        setForm((f) => ({ ...f, avatar_url: newUrl }));
                        const { data } = await api.get("/auth/me").catch(() => ({ data: null }));
                        if (data) setUser(data);
                    }}
                />
                <div>
                    <h1 className="font-heading text-3xl sm:text-4xl font-bold tracking-tight">{user.name}</h1>
                    {user.line_name && <div className="text-sm font-bold uppercase tracking-widest text-primary mt-0.5">"{user.line_name}"</div>}
                    <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 mt-1">
                        <span>{user.email}</span>
                        {user.membership_tier && <span className="text-xs bg-accent/40 rounded-full px-2.5 py-0.5 font-semibold uppercase tracking-wider">{user.membership_tier}</span>}
                    </div>
                </div>
            </div>

            <div className="rounded-2xl bg-gradient-to-br from-primary/15 via-secondary/25 to-accent/40 p-6 border border-border mb-8" data-testid="membership-card">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <div className="text-xs uppercase tracking-wider font-semibold">{user.membership_tier} membership</div>
                        {user.is_lifetime_member ? (
                            <>
                                <div className="font-heading text-2xl font-bold mt-1 text-primary" data-testid="membership-lifetime-label">Lifetime member</div>
                                <div className="text-sm text-muted-foreground mt-1">No renewal required — your membership never expires.</div>
                            </>
                        ) : (
                            <>
                                <div className="font-heading text-2xl font-bold mt-1">
                                    {user.within_grace ? <span className="text-destructive">In grace period — renew soon</span> : daysLeft > 0 ? `${daysLeft} days remaining` : "Expired"}
                                </div>
                                <div className="text-sm text-muted-foreground mt-1">
                                    Expires {user.membership_expires_at && format(parseISO(user.membership_expires_at), "MMM d, yyyy")}
                                    {user.within_grace && " · 30-day grace active"}
                                </div>
                            </>
                        )}
                    </div>
                    {!user.is_lifetime_member && (
                        <div className="text-xs text-muted-foreground italic">Pay annual dues below to renew.</div>
                    )}
                </div>
                {!user.is_lifetime_member && (
                    <div className="mt-4 pt-4 border-t border-border/40 grid sm:grid-cols-2 gap-4" data-testid="dues-checkout-row">
                        <div>
                            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2">Pay dues with PayPal</div>
                            <PayPalCheckout
                                purpose="dues"
                                amount={105}
                                note="Annual dues"
                                onComplete={async () => {
                                    const { data } = await api.get("/auth/me").catch(() => ({ data: null }));
                                    if (data) setUser(data);
                                }}
                            />
                        </div>
                        <div>
                            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2">Pay dues with Zeffy</div>
                            <ZeffyCheckout
                                onComplete={async () => {
                                    const { data } = await api.get("/auth/me").catch(() => ({ data: null }));
                                    if (data) setUser(data);
                                }}
                            />
                        </div>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
                <StatCard icon={<Trophy className="h-4 w-4" />} label="Awards" value={awards.length} testid="stat-awards" />
                <StatCard icon={<Clock className="h-4 w-4" />} label="Approved hrs" value={approvedHours.toFixed(1)} testid="stat-hours" />
                <StatCard icon={<Calendar className="h-4 w-4" />} label="Events" value={events.length} testid="stat-events" />
                <StatCard icon={<DollarSign className="h-4 w-4" />} label="Paid" value={`$${totalPaid.toFixed(0)}`} testid="stat-paid" />
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1 flex-wrap h-auto">
                    <TabsTrigger value="profile" className="rounded-full data-[state=active]:bg-background" data-testid="tab-profile">Profile</TabsTrigger>
                    <TabsTrigger value="security" className="rounded-full data-[state=active]:bg-background" data-testid="tab-security">Security</TabsTrigger>
                    <TabsTrigger value="notifications" className="rounded-full data-[state=active]:bg-background" data-testid="tab-notifications">Notifications</TabsTrigger>
                    <TabsTrigger value="activity" className="rounded-full data-[state=active]:bg-background" data-testid="tab-activity">Activity ({activity.length})</TabsTrigger>
                    <TabsTrigger value="transactions" className="rounded-full data-[state=active]:bg-background" data-testid="tab-transactions">Transactions ({transactions.length})</TabsTrigger>
                    <TabsTrigger value="awards" className="rounded-full data-[state=active]:bg-background" data-testid="tab-awards">Awards ({awards.length})</TabsTrigger>
                    <TabsTrigger value="hours" className="rounded-full data-[state=active]:bg-background" data-testid="tab-hours">Hours ({hoursEntries.length})</TabsTrigger>
                    <TabsTrigger value="events" className="rounded-full data-[state=active]:bg-background" data-testid="tab-events">Events ({events.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="profile" className="mt-6">
                    <form onSubmit={save} className="bg-card rounded-2xl p-6 border border-border shadow-warm space-y-5" data-testid="profile-form">
                        <div className="grid sm:grid-cols-3 gap-4">
                            <div><Label>First name</Label><Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-first" /></div>
                            <div><Label>Middle name</Label><Input value={form.middle_name} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-middle" /></div>
                            <div><Label>Last name</Label><Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-last" /></div>
                        </div>
                        <div className="grid sm:grid-cols-2 gap-4">
                            <div><Label>Line name <span className="text-xs text-muted-foreground font-normal">(fraternity nickname)</span></Label>
                                <Input value={form.line_name} onChange={(e) => setForm({ ...form, line_name: e.target.value })} className="rounded-xl mt-1.5" placeholder="e.g. Patriot" data-testid="profile-line-name" /></div>
                            <div><Label>Username</Label>
                                <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-username" /></div>
                        </div>
                        <div className="grid sm:grid-cols-2 gap-4">
                            <div><Label>Intake line</Label>
                                <Input value={form.intake_line} onChange={(e) => setForm({ ...form, intake_line: e.target.value })} className="rounded-xl mt-1.5" placeholder="e.g. Spring '24 — A1" data-testid="profile-intake-line" /></div>
                            <div>
                                <Label>Intake completion date <span className="text-xs text-muted-foreground font-normal">(Month/Year — requires admin approval)</span></Label>
                                <Input type="month" value={form.intake_completed_at} onChange={(e) => setForm({ ...form, intake_completed_at: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-intake-completed-at" />
                                {user.pending_intake_completed_at && (
                                    <p className="text-xs text-amber-700 mt-1.5 flex items-center gap-1" data-testid="profile-intake-pending">
                                        ⏳ Pending review — awaiting admin approval of <strong>{user.pending_intake_completed_at}</strong>
                                    </p>
                                )}
                            </div>
                        </div>
                        <div className="grid sm:grid-cols-2 gap-4">
                            <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-phone" /></div>
                            <div><Label>City</Label><Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-city" /></div>
                        </div>
                        <div className="grid sm:grid-cols-2 gap-4">
                            <div><Label>Street address</Label><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-address" placeholder="123 Main St, Apt 4B" /></div>
                            <div><Label>Birthdate</Label><Input type="date" value={form.birthdate} onChange={(e) => setForm({ ...form, birthdate: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-birthdate" /></div>
                        </div>
                        <div className="grid sm:grid-cols-3 gap-4">
                            <div><Label>State</Label><Input value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} className="rounded-xl mt-1.5" placeholder="TX" data-testid="profile-state" /></div>
                            <div><Label>Zip code</Label><Input value={form.zip_code} onChange={(e) => setForm({ ...form, zip_code: e.target.value })} className="rounded-xl mt-1.5" placeholder="77001" data-testid="profile-zip" /></div>
                            <div><Label>Country</Label><Input value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} className="rounded-xl mt-1.5" placeholder="USA" data-testid="profile-country" /></div>
                        </div>
                        <div>
                            <Label>Chapter</Label>
                            <Select value={form.chapter_id} onValueChange={(v) => setForm({ ...form, chapter_id: v })}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="profile-chapter"><SelectValue placeholder="Select your chapter" /></SelectTrigger>
                                <SelectContent>
                                    {chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}{c.region && ` — ${c.region}`}{c.state && ` (${c.state})`}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div><Label>Avatar URL</Label><Input value={form.avatar_url} onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-avatar" /></div>
                        <div><Label>Interests (comma separated)</Label><Input value={form.interests} onChange={(e) => setForm({ ...form, interests: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-interests" /></div>
                        <div className="border-t border-border pt-5 mt-2">
                            <div className="flex items-center gap-2 mb-3">
                                <Globe className="h-4 w-4 text-primary" />
                                <h3 className="font-heading text-lg font-bold">Social profiles</h3>
                                <span className="text-xs text-muted-foreground">— shown on your member card in the directory</span>
                            </div>
                            <div className="grid sm:grid-cols-2 gap-4">
                                <div>
                                    <Label className="flex items-center gap-1.5"><Facebook className="h-3.5 w-3.5" /> Facebook</Label>
                                    <Input value={form.facebook_url} onChange={(e) => setForm({ ...form, facebook_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://facebook.com/yourhandle" data-testid="profile-facebook" />
                                </div>
                                <div>
                                    <Label className="flex items-center gap-1.5"><Instagram className="h-3.5 w-3.5" /> Instagram</Label>
                                    <Input value={form.instagram_url} onChange={(e) => setForm({ ...form, instagram_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://instagram.com/yourhandle" data-testid="profile-instagram" />
                                </div>
                                <div>
                                    <Label className="flex items-center gap-1.5"><Linkedin className="h-3.5 w-3.5" /> LinkedIn</Label>
                                    <Input value={form.linkedin_url} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://linkedin.com/in/yourhandle" data-testid="profile-linkedin" />
                                </div>
                                <div>
                                    <Label className="flex items-center gap-1.5"><Twitter className="h-3.5 w-3.5" /> X / Twitter</Label>
                                    <Input value={form.twitter_url} onChange={(e) => setForm({ ...form, twitter_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://x.com/yourhandle" data-testid="profile-twitter" />
                                </div>
                                <div>
                                    <Label>TikTok</Label>
                                    <Input value={form.tiktok_url} onChange={(e) => setForm({ ...form, tiktok_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://tiktok.com/@yourhandle" data-testid="profile-tiktok" />
                                </div>
                                <div>
                                    <Label>Pinterest</Label>
                                    <Input value={form.pinterest_url} onChange={(e) => setForm({ ...form, pinterest_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://pinterest.com/yourhandle" data-testid="profile-pinterest" />
                                </div>
                                <div>
                                    <Label className="flex items-center gap-1.5"><Youtube className="h-3.5 w-3.5" /> YouTube</Label>
                                    <Input value={form.youtube_url} onChange={(e) => setForm({ ...form, youtube_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://youtube.com/@yourhandle" data-testid="profile-youtube" />
                                </div>
                                <div>
                                    <Label className="flex items-center gap-1.5"><Globe className="h-3.5 w-3.5" /> Personal website</Label>
                                    <Input value={form.website_url} onChange={(e) => setForm({ ...form, website_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://yourwebsite.com" data-testid="profile-website" />
                                </div>
                            </div>
                        </div>
                        <div><Label>Bio</Label><Textarea rows={4} value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-bio" /></div>
                        <div className="flex justify-end">
                            <Button type="submit" disabled={saving} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="profile-save-btn">{saving ? "Saving…" : "Save changes"}</Button>
                        </div>
                    </form>
                </TabsContent>

                <TabsContent value="security" className="mt-6">
                    <form onSubmit={changePassword} className="bg-card rounded-2xl p-6 border border-border shadow-warm space-y-4 max-w-md" data-testid="security-form">
                        <div className="flex items-center gap-2 mb-2">
                            <Lock className="h-5 w-5 text-primary" />
                            <h2 className="font-heading text-xl font-bold">Change password</h2>
                        </div>
                        <div><Label>Current password</Label><Input type="password" value={pwd.current} onChange={(e) => setPwd({ ...pwd, current: e.target.value })} className="rounded-xl mt-1.5" required data-testid="pwd-current" /></div>
                        <div><Label>New password</Label><Input type="password" value={pwd.next} onChange={(e) => setPwd({ ...pwd, next: e.target.value })} className="rounded-xl mt-1.5" required minLength={6} data-testid="pwd-new" /></div>
                        <div><Label>Confirm new password</Label><Input type="password" value={pwd.confirm} onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} className="rounded-xl mt-1.5" required data-testid="pwd-confirm" /></div>
                        <Button type="submit" disabled={changingPwd} className="w-full rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="pwd-submit-btn">
                            {changingPwd ? "Updating…" : "Update password"}
                        </Button>
                    </form>
                </TabsContent>

                <TabsContent value="notifications" className="mt-6">
                    <NotificationPrefs user={user} onSaved={(updated) => setUser(updated)} />
                </TabsContent>

                <TabsContent value="activity" className="mt-6">
                    {activity.length === 0 ? (
                        <div className="text-muted-foreground">No activity yet. RSVP to an event, log volunteer hours, or renew your membership to see entries here.</div>
                    ) : (
                        <div className="relative border-l-2 border-primary/30 ml-4 pl-6 space-y-5" data-testid="activity-timeline">
                            {activity.map((a, i) => <ActivityItem key={i} a={a} />)}
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="transactions" className="mt-6">
                    <div className="flex items-center justify-between gap-3 mb-3">
                        <p className="text-sm text-muted-foreground">Recent dues, donations, and gear orders.</p>
                        <Link to="/transactions" className="text-sm text-primary font-semibold hover:underline" data-testid="profile-view-all-tx">View full transactions history →</Link>
                    </div>
                    {transactions.length === 0 ? (
                        <div className="text-muted-foreground">No transactions yet. Renewals, donations, and credits appear here.</div>
                    ) : (
                        <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-warm" data-testid="transactions-table">
                            <table className="w-full text-sm">
                                <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                                    <tr>
                                        <th className="text-left px-5 py-3">Date</th>
                                        <th className="text-left px-5 py-3">Type</th>
                                        <th className="text-left px-5 py-3">Description</th>
                                        <th className="text-right px-5 py-3">Amount</th>
                                        <th className="text-left px-5 py-3">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {transactions.map((t) => (
                                        <tr key={t.id} className="border-t border-border" data-testid={`tx-${t.id}`}>
                                            <td className="px-5 py-3 text-muted-foreground">{t.created_at && format(parseISO(t.created_at), "MMM d, yyyy")}</td>
                                            <td className="px-5 py-3">
                                                <span className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-secondary/20">{t.type}</span>
                                            </td>
                                            <td className="px-5 py-3">{t.description}</td>
                                            <td className="px-5 py-3 text-right font-bold">${t.amount.toFixed(2)}</td>
                                            <td className="px-5 py-3">
                                                <span className={`text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 ${t.status === "completed" ? "bg-accent/40" : t.status === "refunded" ? "bg-destructive/15 text-destructive" : "bg-muted"}`}>{t.status}</span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="awards" className="mt-6">
                    {awards.length === 0 ? <div className="text-muted-foreground">No awards yet.</div> : (
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
                    <div className="mb-4"><Link to="/hours" className="text-primary font-medium hover:underline">Go to volunteer hours →</Link></div>
                    {hoursEntries.length === 0 ? <div className="text-muted-foreground">No hours logged yet.</div> : (
                        <div className="space-y-3">
                            {hoursEntries.slice(0, 20).map((h) => (
                                <div key={h.id} className="bg-card rounded-2xl border border-border p-4 flex items-center gap-4">
                                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary grid place-items-center font-heading font-bold text-sm">{h.hours}</div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm">{h.description}</div>
                                        <div className="text-xs text-muted-foreground">{h.date && format(parseISO(h.date), "MMM d, yyyy")}</div>
                                    </div>
                                    <span className={`text-[10px] uppercase tracking-wider font-semibold rounded-full px-2.5 py-0.5 ${h.status === "approved" ? "bg-accent/40" : h.status === "rejected" ? "bg-destructive/15 text-destructive" : "bg-secondary/40"}`}>{h.status}</span>
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

function StatCard({ icon, label, value, testid }) {
    return (
        <div className="bg-card rounded-2xl border border-border p-4" data-testid={testid}>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-bold">{icon} {label}</div>
            <div className="font-heading text-2xl font-black mt-1">{value}</div>
        </div>
    );
}

function ActivityItem({ a }) {
    const tone = {
        transaction: "bg-secondary/30 text-secondary",
        event: "bg-primary/15 text-primary",
        hours: "bg-accent/40 text-accent-foreground",
        award: "bg-yellow-500/20 text-yellow-700",
    }[a.kind] || "bg-muted";

    const Icon = a.kind === "transaction" ? DollarSign
        : a.kind === "event" ? Calendar
        : a.kind === "hours" ? Clock
        : Trophy;

    return (
        <div className="relative" data-testid={`activity-${a.kind}`}>
            <div className={`absolute -left-[37px] top-0 w-7 h-7 rounded-full grid place-items-center ${tone}`}>
                <Icon className="h-3.5 w-3.5" />
            </div>
            <div className="bg-card rounded-2xl border border-border p-4">
                <div className="flex items-center justify-between gap-2">
                    <div className="text-xs uppercase tracking-widest font-bold text-muted-foreground">{a.kind}{a.subtype && a.subtype !== a.kind ? ` · ${a.subtype}` : ""}</div>
                    <div className="text-xs text-muted-foreground">{a.at && format(parseISO(a.at), "MMM d, yyyy")}</div>
                </div>
                <div className="font-medium mt-1.5">{a.title}</div>
                {a.kind === "transaction" && a.meta?.amount != null && (
                    <div className="text-sm text-muted-foreground mt-1">${a.meta.amount.toFixed(2)} {a.meta.currency} · {a.meta.status}</div>
                )}
            </div>
        </div>
    );
}

function NotificationPrefs({ user, onSaved }) {
    const [emailOn, setEmailOn] = useState(user?.chat_email_notifications !== false);
    const [smsOn, setSmsOn] = useState(user?.chat_sms_notifications !== false);
    const [busy, setBusy] = useState(false);

    async function save() {
        setBusy(true);
        try {
            const { data } = await api.put("/members/me", {
                chat_email_notifications: emailOn,
                chat_sms_notifications: smsOn,
            });
            onSaved?.(data);
            toast.success("Notification preferences saved");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not save");
        }
        setBusy(false);
    }

    const hasPhone = !!user?.phone;

    return (
        <div className="bg-card rounded-2xl p-6 border border-border shadow-warm max-w-2xl space-y-6" data-testid="notification-prefs">
            <div>
                <h2 className="font-heading text-xl font-bold">Chat message notifications</h2>
                <p className="text-sm text-muted-foreground mt-1">When someone messages you in the Alpha Omega Phi chat, we can ping you outside the portal. We bundle messages over 15 minutes so you don't get spammed for back-and-forth threads.</p>
            </div>

            <ToggleRow
                title="Email me about new chat messages"
                description="A consolidated email is sent ~15 minutes after a message arrives, only if you haven't opened the chat by then."
                checked={emailOn}
                onChange={setEmailOn}
                testid="notif-email-toggle"
            />

            <ToggleRow
                title="Text me about new chat messages"
                description={hasPhone
                    ? `We'll text ${user.phone}. We bundle messages and only send if you haven't opened the chat within 15 minutes.`
                    : "Add a phone number in the Profile tab first, then we can text you."
                }
                checked={smsOn}
                onChange={setSmsOn}
                disabled={!hasPhone}
                testid="notif-sms-toggle"
            />

            <div className="pt-3 border-t border-border/40 flex items-center justify-between">
                <p className="text-xs text-muted-foreground">If you turn both off, you'll only see new messages by opening the chat tab.</p>
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="notif-save-btn">
                    {busy ? "Saving…" : "Save"}
                </Button>
            </div>
        </div>
    );
}

function ToggleRow({ title, description, checked, onChange, disabled, testid }) {
    return (
        <div className={`flex items-start justify-between gap-4 ${disabled ? "opacity-50" : ""}`}>
            <div className="flex-1">
                <div className="font-medium">{title}</div>
                <div className="text-xs text-muted-foreground mt-1 leading-relaxed">{description}</div>
            </div>
            <Switch
                checked={checked}
                onCheckedChange={onChange}
                disabled={disabled}
                data-testid={testid}
            />
        </div>
    );
}
