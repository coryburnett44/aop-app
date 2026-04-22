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
import { Calendar, MapPin } from "lucide-react";

export default function Profile() {
    const { user, setUser } = useAuth();
    const [params] = useSearchParams();
    const [tab, setTab] = useState(params.get("tab") || "profile");
    const [form, setForm] = useState({ name: "", bio: "", city: "", interests: "", avatar_url: "" });
    const [events, setEvents] = useState([]);
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
        }
        api.get("/me/events").then(({ data }) => setEvents(data)).catch(() => {});
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
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to save");
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
                    <div className="text-muted-foreground">{user.email}</div>
                </div>
            </div>

            {/* Membership card */}
            <div className="rounded-2xl bg-gradient-to-br from-primary/15 via-secondary/25 to-accent/20 p-6 border border-border mb-8" data-testid="membership-card">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <div className="text-xs uppercase tracking-wider font-semibold">{user.membership_tier} membership</div>
                        <div className="font-heading text-2xl font-bold mt-1">
                            {daysLeft > 0 ? `${daysLeft} days remaining` : "Expired"}
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                            Expires {user.membership_expires_at && format(parseISO(user.membership_expires_at), "MMM d, yyyy")}
                        </div>
                    </div>
                    <Button onClick={renew} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="renew-btn">
                        Renew for 1 year
                    </Button>
                </div>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="rounded-full bg-muted p-1">
                    <TabsTrigger value="profile" className="rounded-full data-[state=active]:bg-background data-[state=active]:shadow" data-testid="tab-profile">Profile</TabsTrigger>
                    <TabsTrigger value="events" className="rounded-full data-[state=active]:bg-background data-[state=active]:shadow" data-testid="tab-events">My events ({events.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="profile" className="mt-6">
                    <form onSubmit={save} className="bg-card rounded-2xl p-6 border border-border shadow-warm grid sm:grid-cols-2 gap-5" data-testid="profile-form">
                        <div className="sm:col-span-2">
                            <Label>Name</Label>
                            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-name" />
                        </div>
                        <div>
                            <Label>City</Label>
                            <Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-city" />
                        </div>
                        <div>
                            <Label>Avatar URL</Label>
                            <Input value={form.avatar_url} onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-avatar" />
                        </div>
                        <div className="sm:col-span-2">
                            <Label>Interests (comma separated)</Label>
                            <Input value={form.interests} onChange={(e) => setForm({ ...form, interests: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-interests" />
                        </div>
                        <div className="sm:col-span-2">
                            <Label>Bio</Label>
                            <Textarea rows={4} value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="rounded-xl mt-1.5" data-testid="profile-bio" />
                        </div>
                        <div className="sm:col-span-2 flex justify-end">
                            <Button type="submit" disabled={saving} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="profile-save-btn">
                                {saving ? "Saving…" : "Save changes"}
                            </Button>
                        </div>
                    </form>
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
