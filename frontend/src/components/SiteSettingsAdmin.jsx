import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Plus, Trash2, Save, Home as HomeIcon, FileText, Layers, ToggleLeft } from "lucide-react";
import { toast } from "sonner";
import { useSiteSettings } from "../context/SiteSettingsContext";
import PageBuilder from "./cms/PageBuilder";

const HOME_SECTION_KEYS = [
    { key: "founders", label: "Founders photo strip" },
    { key: "hero_text", label: "Hero headline + CTAs" },
    { key: "countdown", label: "10-year countdown" },
    { key: "pillars", label: "Three pillars" },
    { key: "family_pulse", label: "New members + birthdays" },
    { key: "secondary_banner", label: "Secondary banner photo" },
    { key: "upcoming_events", label: "Upcoming events" },
    { key: "news", label: "News & stories" },
];

const PAGE_KEYS = [
    { slug: "home", label: "Home" },
    { slug: "events", label: "Events" },
    { slug: "directory", label: "Members" },
    { slug: "chapters", label: "Chapters" },
    { slug: "donations", label: "Donations" },
    { slug: "gear", label: "Gear store" },
    { slug: "photos", label: "Photos" },
    { slug: "documents", label: "AOP Forms" },
    { slug: "chat", label: "Chat" },
    { slug: "news", label: "News" },
    { slug: "calendar", label: "Calendar" },
    { slug: "awards", label: "Awards" },
    { slug: "hours", label: "Hours" },
    { slug: "omega", label: "Omega" },
    { slug: "schedule-meeting", label: "Schedule a meeting" },
];

export default function SiteSettingsAdmin() {
    const { settings, refresh } = useSiteSettings();
    const [form, setForm] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => { if (settings) setForm(JSON.parse(JSON.stringify(settings))); }, [settings]);
    if (!form) return null;

    function set(k, v) { setForm((p) => ({ ...p, [k]: v })); }
    function setTitle(slug, v) { setForm((p) => ({ ...p, page_titles: { ...(p.page_titles || {}), [slug]: v } })); }
    function setNav(slug, v) { setForm((p) => ({ ...p, nav_labels: { ...(p.nav_labels || {}), [slug]: v } })); }
    function addFooterLink() { setForm((p) => ({ ...p, footer_links: [...(p.footer_links || []), { label: "", href: "" }] })); }
    function setFooterLink(i, k, v) { setForm((p) => ({ ...p, footer_links: p.footer_links.map((l, idx) => idx === i ? { ...l, [k]: v } : l) })); }
    function removeFooterLink(i) { setForm((p) => ({ ...p, footer_links: p.footer_links.filter((_, idx) => idx !== i) })); }

    async function save() {
        setBusy(true);
        try {
            const payload = {
                hero_eyebrow: form.hero_eyebrow, hero_headline: form.hero_headline, hero_subtext: form.hero_subtext,
                hero_cta_label: form.hero_cta_label, hero_cta_href: form.hero_cta_href,
                footer_text: form.footer_text, footer_links: form.footer_links,
                page_titles: form.page_titles, nav_labels: form.nav_labels,
                home_sections: form.home_sections,
                home_blocks_top: form.home_blocks_top || [],
                home_blocks_bottom: form.home_blocks_bottom || [],
            };
            await api.put("/site-settings", payload);
            toast.success("Site copy saved");
            await refresh();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    function toggleSection(key) {
        setForm((p) => ({ ...p, home_sections: { ...(p.home_sections || {}), [key]: !(p.home_sections?.[key] ?? true) } }));
    }

    return (
        <div className="bg-card border border-border rounded-2xl p-6 space-y-6" data-testid="site-settings-admin">
            <div className="flex items-end justify-between">
                <div>
                    <h3 className="font-heading text-xl font-bold flex items-center gap-2"><HomeIcon className="h-5 w-5" />Site copy</h3>
                    <p className="text-xs text-muted-foreground">Edit hero text, footer, and every page's H1 / navbar label without touching code. Changes go live immediately for all visitors.</p>
                </div>
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="save-site-settings-btn">
                    <Save className="h-4 w-4 mr-1.5" /> {busy ? "Saving…" : "Save changes"}
                </Button>
            </div>

            {/* Home hero */}
            <div>
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground mb-2">Home page hero</h4>
                <div className="grid sm:grid-cols-2 gap-3">
                    <div><Label>Eyebrow tag</Label><Input value={form.hero_eyebrow || ""} onChange={(e) => set("hero_eyebrow", e.target.value)} className="rounded-xl mt-1.5" data-testid="hero-eyebrow-input" /></div>
                    <div><Label>CTA label (logged out)</Label><Input value={form.hero_cta_label || ""} onChange={(e) => set("hero_cta_label", e.target.value)} className="rounded-xl mt-1.5" /></div>
                    <div className="sm:col-span-2"><Label>Headline</Label><Input value={form.hero_headline || ""} onChange={(e) => set("hero_headline", e.target.value)} className="rounded-xl mt-1.5" data-testid="hero-headline-input" /></div>
                    <div className="sm:col-span-2"><Label>Subtext</Label><Textarea rows={2} value={form.hero_subtext || ""} onChange={(e) => set("hero_subtext", e.target.value)} className="rounded-xl mt-1.5" data-testid="hero-subtext-input" /></div>
                </div>
            </div>

            {/* Footer */}
            <div>
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground mb-2">Footer</h4>
                <div>
                    <Label>Footer text</Label>
                    <Textarea rows={2} value={form.footer_text || ""} onChange={(e) => set("footer_text", e.target.value)} className="rounded-xl mt-1.5" data-testid="footer-text-input" />
                </div>
                <div className="mt-3">
                    <Label>Footer links</Label>
                    <div className="space-y-2 mt-1.5">
                        {(form.footer_links || []).map((l, i) => (
                            <div key={i} className="flex gap-2 items-center" data-testid={`footer-link-${i}`}>
                                <Input value={l.label} onChange={(e) => setFooterLink(i, "label", e.target.value)} placeholder="Label" className="rounded-xl flex-1" />
                                <Input value={l.href} onChange={(e) => setFooterLink(i, "href", e.target.value)} placeholder="https://… or /route" className="rounded-xl flex-1" />
                                <Button variant="ghost" size="icon" onClick={() => removeFooterLink(i)} className="text-destructive"><Trash2 className="h-4 w-4" /></Button>
                            </div>
                        ))}
                    </div>
                    <Button onClick={addFooterLink} variant="outline" size="sm" className="rounded-full mt-2" data-testid="add-footer-link-btn">
                        <Plus className="h-3 w-3 mr-1" /> Add link
                    </Button>
                </div>
            </div>

            {/* Home page section toggles */}
            <div>
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground mb-2 flex items-center gap-2"><ToggleLeft className="h-4 w-4" />Home page sections</h4>
                <p className="text-xs text-muted-foreground mb-3">Toggle which sections appear on the homepage.</p>
                <div className="grid sm:grid-cols-2 gap-2">
                    {HOME_SECTION_KEYS.map((s) => {
                        const on = form.home_sections?.[s.key] ?? true;
                        return (
                            <label key={s.key} className={`flex items-center gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${on ? "bg-primary/5 border-primary/30" : "bg-slate-50 border-slate-200"}`} data-testid={`home-section-${s.key}`}>
                                <input type="checkbox" checked={on} onChange={() => toggleSection(s.key)} className="h-4 w-4 rounded" />
                                <span className="text-sm font-semibold flex-1">{s.label}</span>
                                <span className={`text-[10px] uppercase tracking-wider font-bold ${on ? "text-emerald-600" : "text-slate-400"}`}>{on ? "On" : "Off"}</span>
                            </label>
                        );
                    })}
                </div>
            </div>

            {/* Home blocks — top */}
            <div>
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground mb-2 flex items-center gap-2"><Layers className="h-4 w-4" />Custom blocks — top of home</h4>
                <p className="text-xs text-muted-foreground mb-3">Inserted between the hero and the countdown. Drag to reorder.</p>
                <PageBuilder blocks={form.home_blocks_top || []} onChange={(b) => set("home_blocks_top", b)} testIdPrefix="home-builder-top" />
            </div>

            {/* Home blocks — bottom */}
            <div>
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground mb-2 flex items-center gap-2"><Layers className="h-4 w-4" />Custom blocks — bottom of home</h4>
                <p className="text-xs text-muted-foreground mb-3">Inserted after the News section. Drag to reorder.</p>
                <PageBuilder blocks={form.home_blocks_bottom || []} onChange={(b) => set("home_blocks_bottom", b)} testIdPrefix="home-builder-bottom" />
            </div>

            {/* Per-page titles + nav labels */}
            <div>
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground mb-2 flex items-center gap-2"><FileText className="h-4 w-4" />Page titles & navbar labels</h4>
                <p className="text-xs text-muted-foreground mb-3">Leave blank to use the default. The H1 heading appears at the top of each page; the navbar label is shown in the main nav.</p>
                <div className="grid sm:grid-cols-3 gap-x-3 gap-y-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    <div>Page</div><div>H1 heading</div><div>Navbar label</div>
                </div>
                <div className="grid sm:grid-cols-3 gap-x-3 gap-y-2 mt-1">
                    {PAGE_KEYS.map((p) => (
                        <div key={p.slug} className="contents">
                            <div className="text-sm font-medium pt-2">{p.label}</div>
                            <Input
                                value={form.page_titles?.[p.slug] || ""}
                                onChange={(e) => setTitle(p.slug, e.target.value)}
                                placeholder={p.label}
                                className="rounded-xl"
                                data-testid={`page-title-${p.slug}`}
                            />
                            <Input
                                value={form.nav_labels?.[p.slug] || ""}
                                onChange={(e) => setNav(p.slug, e.target.value)}
                                placeholder={p.label}
                                className="rounded-xl"
                                data-testid={`nav-label-${p.slug}`}
                            />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
