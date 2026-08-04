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
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { format, parseISO, differenceInDays } from "date-fns";
import { formatCalendarDay } from "../lib/dateUtil";
import { fmtET } from "../lib/eventTime";
import { toast } from "sonner";
import {
    Calendar, MapPin, Trophy, Clock, Medal, Star, Heart, GraduationCap, Sparkles,
    Award as AwardIcon, Building2, Lock, DollarSign, Activity, Phone, AtSign,
    Facebook, Instagram, Linkedin, Twitter, Youtube, Globe, Download, Bell, BellOff,
} from "lucide-react";
import ZeffyCheckout from "../components/ZeffyCheckout";
import MyOutstandingBalance from "../components/MyOutstandingBalance";
import AvatarUploader from "../components/AvatarUploader";
import { MaritalStatusField, LanguagesEditor, CivilianDegreesEditor } from "../components/ProfileExtrasEditor";
import { requestPushPermission, optOutOfPush, optInToPush, readPushState } from "../lib/onesignal";
import { MILITARY_BRANCHES } from "../lib/militaryBranches";

const ICON_MAP = { medal: Medal, star: Star, heart: Heart, "graduation-cap": GraduationCap, sparkles: Sparkles, trophy: Trophy, award: AwardIcon };

export default function Profile() {
    const { user, setUser } = useAuth();
    const [params] = useSearchParams();
    const [tab, setTab] = useState(params.get("tab") || "profile");
    const [form, setForm] = useState({
        title: "",
        first_name: "", middle_name: "", last_name: "", line_name: "",
        intake_line: "", intake_completed_at: "",
        username: "", phone: "", bio: "", city: "", address: "", state: "", zip_code: "", country: "",
        birthdate: "", interests: "", avatar_url: "", chapter_id: "",
        branch_of_service: "",
        marital_status: "",
        languages: [],
        civilian_degrees: [],
        custom_fields: {},
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
    const [siteSettings, setSiteSettings] = useState({ profile_layout: [], profile_custom_fields: [] });

    useEffect(() => {
        // Fetch the admin-configured profile layout so we know which sections
        // are hidden and which custom fields to render.
        api.get("/site-settings").then(({ data }) => setSiteSettings({
            profile_layout: data.profile_layout || [],
            profile_custom_fields: data.profile_custom_fields || [],
        })).catch(() => {});
    }, []);

    useEffect(() => {
        if (user) {
            setForm({
                title: user.title || "",
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
                branch_of_service: user.branch_of_service || "",
                facebook_url: user.facebook_url || "",
                instagram_url: user.instagram_url || "",
                linkedin_url: user.linkedin_url || "",
                tiktok_url: user.tiktok_url || "",
                twitter_url: user.twitter_url || "",
                pinterest_url: user.pinterest_url || "",
                youtube_url: user.youtube_url || "",
                website_url: user.website_url || "",
                marital_status: user.marital_status || "",
                languages: user.languages || [],
                civilian_degrees: user.civilian_degrees || [],
                custom_fields: user.custom_fields || {},
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
                title: form.title,
                first_name: form.first_name, middle_name: form.middle_name, last_name: form.last_name,
                line_name: form.line_name, intake_line: form.intake_line, intake_completed_at: form.intake_completed_at,
                username: form.username, phone: form.phone,
                bio: form.bio, city: form.city, address: form.address,
                state: form.state, zip_code: form.zip_code, country: form.country,
                birthdate: form.birthdate,
                interests: form.interests.split(",").map((s) => s.trim()).filter(Boolean),
                avatar_url: form.avatar_url,
                branch_of_service: form.branch_of_service,
                facebook_url: form.facebook_url, instagram_url: form.instagram_url,
                linkedin_url: form.linkedin_url, tiktok_url: form.tiktok_url,
                twitter_url: form.twitter_url, pinterest_url: form.pinterest_url,
                youtube_url: form.youtube_url, website_url: form.website_url,
                marital_status: form.marital_status,
                languages: form.languages,
                civilian_degrees: form.civilian_degrees,
                custom_fields: form.custom_fields,
                // Send chapter_id in the main payload — prior to iter99 this
                // went to a separate admin-only endpoint that silently 403'd
                // for members, which is why picking a chapter appeared to
                // "save" and then vanish on the next page load.
                chapter_id: form.chapter_id || "",
            };
            const { data } = await api.put("/members/me", payload);
            setUser(data);
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
                <div className="flex-1">
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
                                    Expires {user.membership_expires_at && formatCalendarDay(user.membership_expires_at, "MMM d, yyyy")}
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
                    <div className="mt-4 pt-4 border-t border-border/40" data-testid="dues-checkout-row">
                        <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2">Pay annual dues</div>
                        <ZeffyCheckout
                            onComplete={async () => {
                                const { data } = await api.get("/auth/me").catch(() => ({ data: null }));
                                if (data) setUser(data);
                            }}
                        />
                    </div>
                )}
            </div>

            <MyOutstandingBalance />

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
                <StatCard icon={<Trophy className="h-4 w-4" />} label="Awards" value={new Set(awards.map((g) => g.award_id || g.award_name)).size} testid="stat-awards" />
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
                    <TabsTrigger value="awards" className="rounded-full data-[state=active]:bg-background" data-testid="tab-awards">Awards ({new Set(awards.map((g) => g.award_id || g.award_name)).size})</TabsTrigger>
                    <TabsTrigger value="hours" className="rounded-full data-[state=active]:bg-background" data-testid="tab-hours">Hours ({hoursEntries.length})</TabsTrigger>
                    <TabsTrigger value="events" className="rounded-full data-[state=active]:bg-background" data-testid="tab-events">Events ({events.length})</TabsTrigger>
                </TabsList>

                {/* Iter 38: Download buttons live UNDER the tabs row so the profile header
                    stays compact on mobile. */}
                <div className="flex flex-wrap items-center gap-2 mt-4 mb-2" data-testid="profile-download-row">
                    <DownloadMyBriefButton />
                    <DownloadTaxLetterButton />
                </div>

                <TabsContent value="profile" className="mt-6">
                    <form onSubmit={save} className="bg-card rounded-2xl p-6 border border-border shadow-warm space-y-5" data-testid="profile-form">
                        <div className="grid sm:grid-cols-[120px_1fr_1fr_1fr] gap-4">
                            <div>
                                <Label>Title <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                                <Select value={form.title || "__none__"} onValueChange={(v) => setForm({ ...form, title: v === "__none__" ? "" : v })}>
                                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="profile-title"><SelectValue placeholder="—" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__none__">— None —</SelectItem>
                                        {["Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Rev.", "Hon.", "Mx."].map((t) => (
                                            <SelectItem key={t} value={t}>{t}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
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
                        <div className="grid sm:grid-cols-3 gap-4">
                            <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-phone" /></div>
                            <MaritalStatusField value={form.marital_status} onChange={(v) => setForm({ ...form, marital_status: v })} />
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
                        <div className="grid sm:grid-cols-2 gap-4">
                            <div>
                                <Label>Branch of service</Label>
                                <Select
                                    value={form.branch_of_service || "__none__"}
                                    onValueChange={(v) => setForm({ ...form, branch_of_service: v === "__none__" ? "" : v })}
                                >
                                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="profile-branch-of-service">
                                        <SelectValue placeholder="Select your branch" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__none__">— Not specified —</SelectItem>
                                        {MILITARY_BRANCHES.map((b) => (
                                            <SelectItem key={b} value={b} data-testid={`branch-option-${b.replace(/\s+/g, "-").toLowerCase()}`}>{b}</SelectItem>
                                        ))}
                                        {/* Legacy: render any non-canonical value already on the user so editing doesn't silently wipe it. */}
                                        {form.branch_of_service && !MILITARY_BRANCHES.includes(form.branch_of_service) && (
                                            <SelectItem value={form.branch_of_service}>{form.branch_of_service} (legacy)</SelectItem>
                                        )}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Chapter</Label>
                                {/* Iter 100: Governor Managers are chapter-scoped admins whose
                                    authority is tied to their assigned chapter. They cannot
                                    self-reassign — a full-access admin must do it.
                                    Iter 150: Regular members can request a chapter change,
                                    but only a full-access admin can approve it. */}
                                {user?.role === "admin" && (user?.admin_role === "governor_manager") ? (
                                    <>
                                        <div
                                            className="rounded-xl mt-1.5 border border-input bg-muted/40 px-3 py-2 text-sm text-muted-foreground flex items-center justify-between"
                                            data-testid="profile-chapter-locked"
                                        >
                                            <span>{chapters.find((c) => c.id === form.chapter_id)?.name || "Not assigned"}</span>
                                            <span className="text-[10px] uppercase tracking-wider font-bold bg-primary/15 text-primary rounded-full px-2 py-0.5">Locked</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-1.5">
                                            Governor Managers can&apos;t change their own chapter. Please reach out to a full-access admin to be reassigned.
                                        </p>
                                    </>
                                ) : user?.role === "member" ? (
                                    <ChapterChangeRequest
                                        user={user}
                                        chapters={chapters}
                                        currentChapterName={chapters.find((c) => c.id === form.chapter_id)?.name || "Not assigned"}
                                    />
                                ) : (
                                    <Select value={form.chapter_id} onValueChange={(v) => setForm({ ...form, chapter_id: v })}>
                                        <SelectTrigger className="rounded-xl mt-1.5" data-testid="profile-chapter"><SelectValue placeholder="Select your chapter" /></SelectTrigger>
                                        <SelectContent>
                                            {chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}{c.region && ` — ${c.region}`}{c.state && ` (${c.state})`}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                )}
                            </div>
                        </div>
                        {/* Iter 38: Avatar URL field replaced with upload-only.
                            Calls /api/members/me/avatar which stores in object storage and
                            sets avatar_url on the user. */}
                        <div>
                            <Label>Profile photo</Label>
                            <div className="flex items-center gap-3 mt-1.5">
                                {form.avatar_url ? (
                                    <img src={form.avatar_url} alt="" className="h-16 w-16 rounded-full object-contain border border-border" />
                                ) : (
                                    <div className="h-16 w-16 rounded-full border-2 border-dashed border-border grid place-items-center text-[10px] text-muted-foreground">
                                        No photo
                                    </div>
                                )}
                                <label className="rounded-full border px-4 py-2 text-xs cursor-pointer hover:bg-slate-50 inline-flex items-center gap-1.5" data-testid="profile-avatar-upload">
                                    {form.avatar_url ? "Replace photo" : "Upload photo"}
                                    <input
                                        type="file"
                                        accept="image/*"
                                        className="hidden"
                                        onChange={async (e) => {
                                            const f = e.target.files?.[0];
                                            if (!f) return;
                                            const fd = new FormData();
                                            fd.append("file", f);
                                            try {
                                                const { data } = await api.post("/members/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } });
                                                setForm({ ...form, avatar_url: data.avatar_url });
                                                toast.success("Photo uploaded");
                                            } catch (err) {
                                                toast.error(err.response?.data?.detail || "Upload failed");
                                            }
                                            e.target.value = "";
                                        }}
                                    />
                                </label>
                                {form.avatar_url && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        type="button"
                                        onClick={() => setForm({ ...form, avatar_url: "" })}
                                        className="text-xs text-destructive"
                                        data-testid="profile-avatar-remove"
                                    >
                                        Remove
                                    </Button>
                                )}
                            </div>
                        </div>
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
                        <LanguagesEditor value={form.languages} onChange={(v) => setForm({ ...form, languages: v })} />
                        <CivilianDegreesEditor value={form.civilian_degrees} onChange={(v) => setForm({ ...form, civilian_degrees: v })} />
                        {(siteSettings.profile_custom_fields || []).length > 0 && (
                            <div className="rounded-2xl border-2 border-slate-200 bg-slate-50 p-4 space-y-3" data-testid="custom-fields-section">
                                <div>
                                    <Label className="text-base font-semibold">Additional information</Label>
                                    <p className="text-xs text-muted-foreground">Fields configured by your chapter admin.</p>
                                </div>
                                {siteSettings.profile_custom_fields.map((f) => (
                                    <CustomFieldInput
                                        key={f.key}
                                        field={f}
                                        value={(form.custom_fields || {})[f.key] ?? ""}
                                        onChange={(v) => setForm({ ...form, custom_fields: { ...(form.custom_fields || {}), [f.key]: v } })}
                                    />
                                ))}
                            </div>
                        )}
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

                <TabsContent value="notifications" className="mt-6 space-y-6">
                    <NotificationPrefs user={user} onSaved={(updated) => setUser(updated)} />
                    <PushPreferences />
                    <EmailPreferences user={user} onSaved={(updated) => setUser(updated)} />
                    <SmsPreferences user={user} onSaved={(updated) => setUser(updated)} />
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
                    {(() => {
                        // Iter 36: render ONE card per distinct award, with an ordinal
                        // label ("2nd Award", "3rd Award") + total count when the
                        // member has earned the same award more than once.
                        const ordinalLabel = (n) => n === 1 ? "1st Award" : n === 2 ? "2nd Award" : n === 3 ? "3rd Award" : `${n}th Award`;
                        const byAward = new Map();
                        for (const g of [...awards].sort((a, b) => (a.granted_at || "").localeCompare(b.granted_at || ""))) {
                            const aid = g.award_id || g.award_name;
                            const cur = byAward.get(aid) || { ...g, count: 0, grants: [], last_granted_at: g.granted_at, reasons: [] };
                            cur.count += 1;
                            cur.last_granted_at = g.granted_at || cur.last_granted_at;
                            cur.grants.push(g);
                            if (g.reason) cur.reasons.push(g.reason);
                            byAward.set(aid, cur);
                        }
                        const grouped = Array.from(byAward.values()).sort((a, b) => (b.last_granted_at || "").localeCompare(a.last_granted_at || ""));
                        if (grouped.length === 0) return <div className="text-muted-foreground">No awards yet.</div>;
                        return (
                            <div className="grid sm:grid-cols-2 gap-4" data-testid="awards-grid">
                                {grouped.map((row) => {
                                    const Icon = ICON_MAP[row.award_icon] || Trophy;
                                    const ord = ordinalLabel(row.count);
                                    return (
                                        <div key={row.award_id || row.award_name} className="bg-card rounded-2xl border border-border p-5 flex items-center gap-4" data-testid={`award-card-${row.award_id || row.award_name}`}>
                                            <div className="w-14 h-14 rounded-2xl grid place-items-center" style={{ backgroundColor: `${row.award_color}33`, color: row.award_color }}>
                                                <Icon className="h-7 w-7" />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <div className="font-heading font-semibold">{row.award_name}</div>
                                                    <span
                                                        className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary"
                                                        title={row.count > 1 ? `Earned ${row.count} times` : "Earned once"}
                                                        data-testid={`award-ordinal-${row.award_id || row.award_name}`}
                                                    >
                                                        {row.count > 1 ? `${ord} · × ${row.count}` : ord}
                                                    </span>
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {row.count > 1 ? "Latest " : ""}
                                                    {row.last_granted_at && formatCalendarDay(row.last_granted_at, "MMM d, yyyy")}
                                                </div>
                                                {row.reasons.length > 0 && (
                                                    <div className="text-xs italic mt-1 truncate" title={row.reasons.join(" • ")}>{row.reasons[row.reasons.length - 1]}</div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        );
                    })()}
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
                                        <div className="text-xs text-muted-foreground">{h.date && formatCalendarDay(h.date, "MMM d, yyyy")}</div>
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
                                <span className="inline-flex items-center gap-1.5"><Calendar className="h-4 w-4" /> {fmtET(e.start_at, "EEE, MMM d · h:mm a zzz")}</span>
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

function PushPreferences() {
    // OneSignal state — read on mount + whenever the user toggles.
    const [state, setState] = useState({ available: false });
    const [busy, setBusy] = useState(false);

    async function refresh() {
        const s = await readPushState();
        setState(s);
    }

    useEffect(() => { refresh(); }, []);

    async function turnOn() {
        setBusy(true);
        // If the site permission was already denied at the browser level,
        // requesting again won't re-prompt — surface an actionable hint.
        const before = await readPushState();
        if (before.permission === "denied") {
            toast.error("Notifications are blocked in your browser. Open site settings and set Notifications → Allow, then reload.");
            setBusy(false);
            return;
        }
        const res = await requestPushPermission();
        if (res.ok) {
            // Ensure the user is opted in (browsers can grant permission but
            // leave the subscription off if it was previously opted out).
            await optInToPush();
            toast.success("Push notifications enabled ✓");
            await refresh();
        } else if (res.reason === "onesignal_unavailable") {
            toast.error("Push notifications aren't configured on this environment.");
        } else {
            toast.error("Could not enable notifications — please allow them in your browser.");
        }
        setBusy(false);
    }

    async function turnOff() {
        setBusy(true);
        const res = await optOutOfPush();
        if (res.ok) {
            toast.success("Push notifications turned off.");
            await refresh();
        } else if (res.reason === "onesignal_unavailable") {
            toast.error("Push notifications aren't configured on this environment.");
        } else {
            toast.error("Could not update your preferences right now.");
        }
        setBusy(false);
    }

    if (!state.available) {
        return (
            <div className="rounded-2xl border border-dashed p-6 bg-muted/30" data-testid="push-prefs-unavailable">
                <div className="flex items-start gap-3">
                    <BellOff className="h-5 w-5 text-muted-foreground mt-0.5" />
                    <div>
                        <div className="font-semibold">Push notifications</div>
                        <p className="text-sm text-muted-foreground mt-1">
                            Push isn't available in this browser or environment. On mobile, open this site in Chrome (Android) or Safari (iOS 16.4+) and add it to your home screen to enable pushes.
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    const enabled = state.opted_in && state.permission === "granted";

    return (
        <div className="rounded-2xl border p-6 bg-card" data-testid="push-prefs-card">
            <div className="flex items-start gap-3">
                <Bell className={`h-5 w-5 mt-0.5 ${enabled ? "text-primary" : "text-muted-foreground"}`} />
                <div className="flex-1">
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <div className="font-semibold">Push notifications</div>
                            <p className="text-sm text-muted-foreground mt-0.5">
                                {enabled
                                    ? "You'll get a heads-up on your device when a new story, event, or announcement is published."
                                    : "Get instant alerts on this device for new stories, events, and announcements."}
                            </p>
                        </div>
                        {enabled ? (
                            <Button variant="outline" onClick={turnOff} disabled={busy} data-testid="push-turn-off">
                                Turn off
                            </Button>
                        ) : (
                            <Button onClick={turnOn} disabled={busy} data-testid="push-turn-on">
                                {busy ? "Enabling…" : "Enable"}
                            </Button>
                        )}
                    </div>
                    {state.permission === "denied" && !enabled && (
                        <div className="mt-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs px-3 py-2">
                            Notifications are currently blocked in your browser. To re-enable them, click the padlock/settings icon next to the URL, set Notifications → Allow, and reload the page.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function EmailPreferences({ user, onSaved }) {
    const [optOut, setOptOut] = useState(!!user?.email_opt_out);
    const [blasts, setBlasts] = useState(user?.email_prefs?.blasts !== false);
    const [duesReminders, setDuesReminders] = useState(user?.email_prefs?.dues_reminders !== false);
    const [loaded, setLoaded] = useState(false);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        // Refresh from server in case the public unsubscribe link was clicked
        // since the last user fetch (otherwise the master toggle looks stale).
        api.get("/me/email-preferences")
            .then(({ data }) => {
                setOptOut(!!data.email_opt_out);
                setBlasts(data.email_prefs?.blasts !== false);
                setDuesReminders(data.email_prefs?.dues_reminders !== false);
                setLoaded(true);
            })
            .catch(() => setLoaded(true));
    }, []);

    async function save() {
        setBusy(true);
        try {
            const payload = {
                blasts,
                dues_reminders: duesReminders,
                email_opt_out: optOut,
            };
            const { data } = await api.put("/me/email-preferences", payload);
            setOptOut(!!data.email_opt_out);
            setBlasts(data.email_prefs?.blasts !== false);
            setDuesReminders(data.email_prefs?.dues_reminders !== false);
            // Sync the user object so other tabs see the change immediately.
            onSaved?.({ ...user, email_opt_out: !!data.email_opt_out, email_prefs: data.email_prefs });
            toast.success("Email preferences saved");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not save");
        }
        setBusy(false);
    }

    return (
        <div className="bg-card rounded-2xl p-6 border border-border shadow-warm max-w-2xl space-y-6" data-testid="email-preferences">
            <div>
                <h2 className="font-heading text-xl font-bold">Email preferences</h2>
                <p className="text-sm text-muted-foreground mt-1">
                    Choose which Alpha Omega Phi emails you want to receive. Account-critical
                    emails — password resets, your own RSVP receipts, security alerts — always
                    come through regardless of these settings.
                </p>
            </div>

            {loaded && optOut && (
                <div className="rounded-2xl border-2 border-amber-300 bg-amber-50 p-3 text-sm" data-testid="email-prefs-master-banner">
                    <div className="font-bold text-amber-800 mb-0.5">⚠ You are currently unsubscribed from all marketing email.</div>
                    <div className="text-amber-900/80 text-xs leading-relaxed">
                        This happens when you click "Unsubscribe" at the bottom of an email. Toggle any category back on below — we'll automatically re-subscribe you to the master list.
                    </div>
                </div>
            )}

            <ToggleRow
                title="Newsletter & announcement blasts"
                description="Chapter news, event invites, fundraising drives, and the periodic admin email blast. Sent from the Admin → Email tab."
                checked={blasts && !optOut}
                onChange={(v) => { setBlasts(v); if (v) setOptOut(false); }}
                testid="email-prefs-blasts-toggle"
            />

            <ToggleRow
                title="Annual dues renewal reminders"
                description="Friendly heads-up emails 30, 15, and 5 days before your membership expires, plus a final note 1 day after. Highly recommended — missing renewal puts you in inactive status."
                checked={duesReminders && !optOut}
                onChange={(v) => { setDuesReminders(v); if (v) setOptOut(false); }}
                testid="email-prefs-dues-toggle"
            />

            <ToggleRow
                title="Unsubscribe from everything (master kill switch)"
                description="Equivalent to clicking the Unsubscribe link in the footer of any email blast. Turning this on overrides the individual toggles above."
                checked={optOut}
                onChange={setOptOut}
                testid="email-prefs-optout-toggle"
            />

            <div className="pt-3 border-t border-border/40 flex items-center justify-end">
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="email-prefs-save-btn">
                    {busy ? "Saving…" : "Save email preferences"}
                </Button>
            </div>
        </div>
    );
}

function SmsPreferences({ user, onSaved }) {
    const [phone, setPhone] = useState(user?.phone || "");
    const [optOut, setOptOut] = useState(!!user?.sms_opt_out);
    const [duesReminders, setDuesReminders] = useState(user?.sms_prefs?.dues_reminders !== false);
    const [loaded, setLoaded] = useState(false);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get("/me/sms-preferences")
            .then(({ data }) => {
                setPhone(data.phone || "");
                setOptOut(!!data.sms_opt_out);
                setDuesReminders(data.sms_prefs?.dues_reminders !== false);
                setLoaded(true);
            })
            .catch(() => setLoaded(true));
    }, []);

    async function save() {
        setBusy(true);
        try {
            const { data } = await api.put("/me/sms-preferences", {
                dues_reminders: duesReminders,
                sms_opt_out: optOut,
            });
            setOptOut(!!data.sms_opt_out);
            setDuesReminders(data.sms_prefs?.dues_reminders !== false);
            onSaved?.({ ...user, sms_opt_out: !!data.sms_opt_out, sms_prefs: data.sms_prefs });
            toast.success("Text message preferences saved");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not save");
        }
        setBusy(false);
    }

    const hasPhone = !!(phone && phone.trim());

    return (
        <div className="bg-card rounded-2xl p-6 border border-border shadow-warm max-w-2xl space-y-6" data-testid="sms-preferences">
            <div>
                <h2 className="font-heading text-xl font-bold">Text message preferences</h2>
                <p className="text-sm text-muted-foreground mt-1">
                    Alpha Omega Phi sends occasional SMS messages — dues renewal reminders and
                    a heads-up when a chapter video meeting starts. Standard message &amp; data
                    rates apply. Reply <span className="font-bold">STOP</span> to any message
                    to opt out immediately.
                </p>
            </div>

            {loaded && !hasPhone && (
                <div className="rounded-2xl border-2 border-slate-200 bg-slate-50 p-3 text-sm" data-testid="sms-prefs-no-phone-banner">
                    <div className="font-bold text-slate-800 mb-0.5">No phone number on file.</div>
                    <div className="text-slate-700/80 text-xs leading-relaxed">
                        Add a phone number to your profile above to start receiving text messages. Until then these preferences won't have any effect.
                    </div>
                </div>
            )}

            {loaded && optOut && hasPhone && (
                <div className="rounded-2xl border-2 border-amber-300 bg-amber-50 p-3 text-sm" data-testid="sms-prefs-master-banner">
                    <div className="font-bold text-amber-800 mb-0.5">⚠ You are currently unsubscribed from all Alpha Omega Phi text messages.</div>
                    <div className="text-amber-900/80 text-xs leading-relaxed">
                        Toggle any category back on below — we'll automatically clear the master opt-out.
                    </div>
                </div>
            )}

            <ToggleRow
                title="Annual dues renewal reminders"
                description="A short heads-up text 30, 15, and 5 days before your membership expires (plus a grace-period reminder). Sent as a companion to the email so you don't miss a renewal."
                checked={duesReminders && !optOut}
                onChange={(v) => { setDuesReminders(v); if (v) setOptOut(false); }}
                disabled={!hasPhone}
                testid="sms-prefs-dues-toggle"
            />

            <ToggleRow
                title="Unsubscribe from all Alpha Omega Phi text messages"
                description="Equivalent to replying STOP to any AOP text. Overrides the individual toggles above."
                checked={optOut}
                onChange={setOptOut}
                disabled={!hasPhone}
                testid="sms-prefs-optout-toggle"
            />

            <div className="pt-3 border-t border-border/40 flex items-center justify-end">
                <Button onClick={save} disabled={busy || !hasPhone} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="sms-prefs-save-btn">
                    {busy ? "Saving…" : "Save text message preferences"}
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

/**
 * Tiny self-contained button — fetches the current user's personnel-brief PDF
 * and triggers a download. Lives in the profile header so members always have
 * a one-click escape hatch to grab their record (great for reimbursements,
 * career packets, and PCS/transfer files).
 */
function DownloadMyBriefButton() {
    const [busy, setBusy] = useState(false);
    async function download() {
        setBusy(true);
        try {
            const res = await api.get("/me/personnel-brief/pdf", { responseType: "blob" });
            const url = URL.createObjectURL(res.data);
            const a = document.createElement("a");
            a.href = url;
            a.download = `my-personnel-brief-${new Date().toISOString().slice(0, 10)}.pdf`;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
            toast.success("Personnel brief downloaded");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not download brief");
        }
        setBusy(false);
    }
    return (
        <Button
            type="button"
            onClick={download}
            disabled={busy}
            variant="outline"
            className="rounded-full self-start"
            data-testid="download-my-brief-btn"
        >
            <Download className="h-4 w-4 mr-1.5" />
            {busy ? "Generating…" : "Download my brief"}
        </Button>
    );
}

/**
 * Per-year annual tax-donation letter download. Defaults to last completed
 * year (current_year - 1) which is what taxpayers usually need. A small
 * year-picker lets the member also grab the current year (mid-year preview)
 * or any past year — useful if they're back-filling tax records.
 */
function DownloadTaxLetterButton() {
    const [busy, setBusy] = useState(false);
    const [year, setYear] = useState(new Date().getFullYear() - 1);
    const years = [];
    const cur = new Date().getFullYear();
    for (let y = cur; y >= 2017; y--) years.push(y);
    async function download() {
        setBusy(true);
        try {
            const res = await api.get(`/me/tax-letter/pdf?year=${year}`, { responseType: "blob" });
            const url = URL.createObjectURL(res.data);
            const a = document.createElement("a");
            a.href = url;
            a.download = `aop-tax-letter-${year}.pdf`;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
            toast.success(`Tax letter for ${year} downloaded`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not generate tax letter");
        }
        setBusy(false);
    }
    return (
        <div className="flex items-center gap-1.5 self-start" data-testid="tax-letter-block">
            <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
                <SelectTrigger className="rounded-full h-9 w-[110px] text-xs font-semibold" data-testid="tax-letter-year-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                    {years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
                </SelectContent>
            </Select>
            <Button
                type="button"
                onClick={download}
                disabled={busy}
                className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white"
                data-testid="download-tax-letter-btn"
            >
                <Download className="h-4 w-4 mr-1.5" />
                {busy ? "Generating…" : "Tax letter"}
            </Button>
        </div>
    );
}


/**
 * Renders one admin-defined custom profile field. Supported types:
 *   text / textarea / date / number / select
 * The field's `key` becomes the persisted key on users.custom_fields.
 */
function CustomFieldInput({ field, value, onChange }) {
    const id = `cf-${field.key}`;
    if (field.type === "textarea") {
        return (
            <div>
                <Label htmlFor={id}>{field.label}{field.required && <span className="text-rose-500 ml-1">*</span>}</Label>
                <Textarea id={id} rows={3} value={value || ""} onChange={(e) => onChange(e.target.value)} className="rounded-xl mt-1.5" data-testid={`custom-field-input-${field.key}`} />
                {field.help_text && <p className="text-[11px] text-muted-foreground mt-1">{field.help_text}</p>}
            </div>
        );
    }
    if (field.type === "select") {
        return (
            <div>
                <Label htmlFor={id}>{field.label}{field.required && <span className="text-rose-500 ml-1">*</span>}</Label>
                <Select value={value || "__none__"} onValueChange={(v) => onChange(v === "__none__" ? "" : v)}>
                    <SelectTrigger className="rounded-xl mt-1.5" data-testid={`custom-field-input-${field.key}`}><SelectValue placeholder="—" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="__none__">— None —</SelectItem>
                        {(field.options || []).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                    </SelectContent>
                </Select>
                {field.help_text && <p className="text-[11px] text-muted-foreground mt-1">{field.help_text}</p>}
            </div>
        );
    }
    const inputType = field.type === "date" ? "date" : field.type === "number" ? "number" : "text";
    return (
        <div>
            <Label htmlFor={id}>{field.label}{field.required && <span className="text-rose-500 ml-1">*</span>}</Label>
            <Input id={id} type={inputType} value={value || ""} onChange={(e) => onChange(e.target.value)} className="rounded-xl mt-1.5" data-testid={`custom-field-input-${field.key}`} />
            {field.help_text && <p className="text-[11px] text-muted-foreground mt-1">{field.help_text}</p>}
        </div>
    );
}



/**
 * Iter 150 — Chapter-change request for regular members.
 */
function ChapterChangeRequest({ user, chapters, currentChapterName }) {
    const [pending, setPending] = useState(null);
    const [showDialog, setShowDialog] = useState(false);
    const [form, setForm] = useState({ target_chapter_id: "", reason: "" });
    const [saving, setSaving] = useState(false);

    async function load() {
        try {
            const { data } = await api.get("/me/chapter-change-request");
            setPending(data && data.status === "pending" ? data : null);
        } catch { setPending(null); }
    }
    useEffect(() => { load(); }, []);

    async function submit() {
        if (!form.target_chapter_id) return toast.error("Pick a target chapter");
        if (form.target_chapter_id === user?.chapter_id) return toast.error("You're already assigned to that chapter.");
        setSaving(true);
        try {
            await api.post("/me/chapter-change-request", form);
            toast.success("Chapter change request submitted");
            setShowDialog(false);
            setForm({ target_chapter_id: "", reason: "" });
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Submit failed");
        }
        setSaving(false);
    }

    async function cancel() {
        if (!window.confirm("Cancel your chapter change request?")) return;
        try {
            await api.delete("/me/chapter-change-request");
            toast.success("Request cancelled");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Cancel failed"); }
    }

    return (
        <>
            <div className="rounded-xl mt-1.5 border border-input bg-muted/40 px-3 py-2 text-sm flex items-center justify-between" data-testid="profile-chapter-readonly">
                <span>{currentChapterName}</span>
                {!pending ? (
                    <Button type="button" size="sm" variant="outline" onClick={() => setShowDialog(true)} data-testid="chapter-change-request-btn">
                        Request change
                    </Button>
                ) : (
                    <span className="text-[10px] uppercase tracking-wider font-bold bg-amber-100 text-amber-800 rounded-full px-2 py-0.5" data-testid="chapter-change-pending-badge">
                        Change pending approval
                    </span>
                )}
            </div>
            {pending && (
                <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs" data-testid="chapter-change-pending-detail">
                    <div>Requesting move to <strong>{pending.target_chapter_name}</strong> &mdash; awaiting full-access admin approval.</div>
                    {pending.reason && <div className="italic text-slate-700 mt-1">&ldquo;{pending.reason}&rdquo;</div>}
                    <button type="button" onClick={cancel} className="underline text-slate-600 mt-2" data-testid="chapter-change-cancel-btn">Cancel request</button>
                </div>
            )}
            <p className="text-xs text-muted-foreground mt-1.5">
                Chapter changes require full-access admin approval. Submit a request and you&rsquo;ll be notified by email when it&rsquo;s reviewed.
            </p>
            <Dialog open={showDialog} onOpenChange={setShowDialog}>
                <DialogContent data-testid="chapter-change-dialog">
                    <DialogHeader><DialogTitle>Request chapter change</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                        <div>
                            <Label htmlFor="ccr-target">New chapter</Label>
                            <Select value={form.target_chapter_id} onValueChange={(v) => setForm({ ...form, target_chapter_id: v })}>
                                <SelectTrigger id="ccr-target" data-testid="chapter-change-target-select"><SelectValue placeholder="Pick a chapter…" /></SelectTrigger>
                                <SelectContent>
                                    {chapters.filter((c) => c.id !== user?.chapter_id).map((c) => (
                                        <SelectItem key={c.id} value={c.id}>{c.name}{c.region && ` — ${c.region}`}{c.state && ` (${c.state})`}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label htmlFor="ccr-reason">Reason (optional)</Label>
                            <Textarea id="ccr-reason" rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Moved to a new state, joined a closer chapter, etc." data-testid="chapter-change-reason-input" />
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <Button variant="outline" onClick={() => setShowDialog(false)} disabled={saving}>Cancel</Button>
                            <Button onClick={submit} disabled={saving || !form.target_chapter_id} data-testid="chapter-change-submit-btn">
                                {saving ? "Submitting…" : "Submit request"}
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </>
    );
}

