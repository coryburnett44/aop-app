import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Switch } from "./ui/switch";
import { Plus, Pencil, Trash2, Play, Eye, Clock, Tag, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

const SECTION_LABELS = {
    events: "Upcoming events (next 7 days)",
    photos: "New photo albums this week",
    documents: "New AOP forms this week",
    new_members: "New members joined this week",
    my_rsvps: "Recipient's upcoming RSVPs",
    pending_hours: "Hours waiting on approval (admins only)",
    birthday_greeting: "Birthday greeting (if recipient's birthday is this week)",
};

const COMMON_SCHEDULES = [
    { value: "0 9 * * 1", label: "Weekly · Monday 9am UTC" },
    { value: "0 9 * * 5", label: "Weekly · Friday 9am UTC" },
    { value: "0 9 1 * *", label: "Monthly · 1st at 9am UTC" },
    { value: "0 9 * * *", label: "Daily · 9am UTC" },
];

export default function AutomatedEmailsAdmin() {
    const [items, setItems] = useState([]);
    const [editing, setEditing] = useState(null);
    const [busy, setBusy] = useState({});

    const load = async () => {
        try { const { data } = await api.get("/automated-emails"); setItems(data); } catch { setItems([]); }
    };
    useEffect(() => { load(); }, []);

    async function runNow(it) {
        if (!window.confirm(`Send "${it.name}" RIGHT NOW to the full audience?`)) return;
        setBusy((b) => ({ ...b, [it.id]: "run" }));
        try {
            const { data } = await api.post(`/automated-emails/${it.id}/run-now`);
            toast.success(`Sent to ${data.sent} recipient${data.sent === 1 ? "" : "s"}`);
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy((b) => ({ ...b, [it.id]: null }));
    }
    async function remove(it) {
        if (!window.confirm(`Delete "${it.name}"?`)) return;
        try { await api.delete(`/automated-emails/${it.id}`); toast.success("Deleted"); await load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }
    async function toggleActive(it) {
        try {
            await api.put(`/automated-emails/${it.id}`, { ...it, audience: it.audience, sections: it.sections, is_active: !it.is_active });
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    return (
        <div className="space-y-6" data-testid="automated-emails-admin">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h2 className="font-heading text-2xl font-bold">Automated emails</h2>
                    <p className="text-sm text-muted-foreground mt-1">Scheduled campaigns that auto-render with member data. Admins can edit, pause, or delete any campaign — including the built-ins.</p>
                </div>
                <Button onClick={() => setEditing({ _new: true })} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="new-automated-email-btn">
                    <Plus className="h-4 w-4 mr-1.5" /> New campaign
                </Button>
            </div>

            {items.length === 0 ? (
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-2xl p-10 text-center text-sm text-muted-foreground">
                    Nothing scheduled yet.
                </div>
            ) : (
                <div className="space-y-3">
                    {items.map((it) => (
                        <div key={it.id} className="bg-card border border-border rounded-2xl p-5 flex flex-wrap items-start gap-4" data-testid={`auto-email-${it.id}`}>
                            <div className="flex-1 min-w-[240px]">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="font-heading font-bold text-lg">{it.name}</h3>
                                    {it.is_builtin && <span className="text-[10px] uppercase tracking-wider font-bold bg-primary/15 text-primary rounded-full px-2 py-0.5">Built-in</span>}
                                    <span className={`text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 ${it.is_active ? "bg-green-100 text-green-700" : "bg-slate-200 text-slate-600"}`}>
                                        {it.is_active ? "Active" : "Paused"}
                                    </span>
                                </div>
                                <div className="text-xs text-muted-foreground mt-1">{it.subject}</div>
                                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                    <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> <code className="font-mono">{it.cron_expression}</code></span>
                                    {it.next_run_at && <span>Next: {format(parseISO(it.next_run_at), "EEE, MMM d · h:mm a")}</span>}
                                    {it.last_run_at && <span>Last: {format(parseISO(it.last_run_at), "MMM d, h:mm a")} ({it.last_sent_count} sent)</span>}
                                    <span className="inline-flex items-center gap-1"><Tag className="h-3 w-3" />Audience: {(it.audience?.type || "all") + (it.audience?.ids?.length ? ` (${it.audience.ids.length})` : "")}</span>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <Switch checked={it.is_active} onCheckedChange={() => toggleActive(it)} data-testid={`auto-toggle-${it.id}`} />
                                <Button size="sm" variant="outline" onClick={() => setEditing(it)} className="rounded-full" data-testid={`auto-edit-${it.id}`}>
                                    <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => runNow(it)} disabled={busy[it.id] === "run"} className="rounded-full" data-testid={`auto-run-${it.id}`}>
                                    <Play className="h-3.5 w-3.5 mr-1" /> Run now
                                </Button>
                                {!it.is_builtin && (
                                    <Button size="sm" variant="ghost" onClick={() => remove(it)} className="text-destructive hover:bg-destructive/10 rounded-full" data-testid={`auto-delete-${it.id}`}>
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                )}
                                {it.is_builtin && (
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => {
                                            if (window.confirm(`Permanently delete the built-in "${it.name}" campaign? The boot seeder will skip recreating it. (Undo: drop the tombstone in deleted_builtin_automated_emails.)`)) {
                                                remove(it);
                                            }
                                        }}
                                        className="text-destructive hover:bg-destructive/10 rounded-full"
                                        data-testid={`auto-delete-${it.id}`}
                                        title="Admin override — permanently delete this built-in campaign"
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <CampaignEditor editing={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await load(); }} />
        </div>
    );
}

function CampaignEditor({ editing, onClose, onSaved }) {
    const [form, setForm] = useState(null);
    const [chapters, setChapters] = useState([]);
    const [tiers, setTiers] = useState([]);
    const [tags, setTags] = useState([]);
    const [busy, setBusy] = useState(false);
    const [previewHtml, setPreviewHtml] = useState("");
    const [duesDefaults, setDuesDefaults] = useState(null); // {stages, defaults, placeholders}

    useEffect(() => {
        if (!editing) { setForm(null); return; }
        if (editing._new) {
            setForm({
                _new: true, name: "", subject: "", body_html: "<p>Hi {{member_name}},</p>\n<p>Your message here.</p>\n{{upcoming_events}}",
                cron_expression: "0 9 * * 1", is_active: true,
                audience: { type: "all", ids: [] },
                sections: { events: true, photos: true, documents: true, new_members: true, my_rsvps: true, pending_hours: true, birthday_greeting: true },
                stage_templates: {},
            });
        } else {
            setForm({ ...editing, stage_templates: editing.stage_templates || {} });
        }
        setPreviewHtml("");
        api.get("/chapters").then(({ data }) => setChapters(data)).catch(() => {});
        api.get("/tiers").then(({ data }) => setTiers(data)).catch(() => {});
        api.get("/automated-emails/merge-tags").then(({ data }) => setTags(data.tags || [])).catch(() => {});
        // Only fetch defaults for dues_reminders kind — saves a roundtrip otherwise.
        if (editing?.kind === "dues_reminders") {
            api.get("/automated-emails/dues-reminder-defaults")
                .then(({ data }) => setDuesDefaults(data))
                .catch(() => {});
        } else {
            setDuesDefaults(null);
        }
    }, [editing]);

    if (!form) return null;

    function set(k, v) { setForm((p) => ({ ...p, [k]: v })); }
    function setAudienceType(t) { setForm((p) => ({ ...p, audience: { type: t, ids: [] } })); }
    function toggleAudienceId(id) {
        setForm((p) => {
            const ids = p.audience.ids.includes(id) ? p.audience.ids.filter((x) => x !== id) : [...p.audience.ids, id];
            return { ...p, audience: { ...p.audience, ids } };
        });
    }
    function toggleSection(k) { setForm((p) => ({ ...p, sections: { ...(p.sections || {}), [k]: !(p.sections?.[k] ?? true) } })); }
    function insertTag(tag) { setForm((p) => ({ ...p, body_html: (p.body_html || "") + "\n" + tag })); }
    function setStage(stageId, field, value) {
        setForm((p) => ({
            ...p,
            stage_templates: {
                ...(p.stage_templates || {}),
                [stageId]: { ...((p.stage_templates || {})[stageId] || {}), [field]: value },
            },
        }));
    }
    function resetStage(stageId) {
        // Drop the override → the backend falls back to the baked default.
        setForm((p) => {
            const next = { ...(p.stage_templates || {}) };
            delete next[stageId];
            return { ...p, stage_templates: next };
        });
        toast.success("Reset to default");
    }

    async function save() {
        const isDues = form.kind === "dues_reminders";
        if (!isDues && (!form.name?.trim() || !form.subject?.trim())) { toast.error("Name and subject are required"); return; }
        setBusy(true);
        try {
            const payload = {
                name: form.name || "Annual Dues Reminders",
                subject: form.subject || "Annual dues reminder",
                body_html: form.body_html || "",
                cron_expression: form.cron_expression, is_active: !!form.is_active,
                audience: form.audience || { type: "all", ids: [] },
                sections: form.sections || {},
                stage_templates: form.stage_templates || {},
            };
            if (form._new) await api.post("/automated-emails", payload);
            else await api.put(`/automated-emails/${form.id}`, payload);
            toast.success("Saved");
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    async function preview() {
        if (form._new) { toast.error("Save the campaign first to preview"); return; }
        try {
            const { data } = await api.post(`/automated-emails/${form.id}/preview`);
            setPreviewHtml(data.body_html);
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    const audienceOptions = form.audience.type === "chapter" ? chapters
        : form.audience.type === "tier" ? tiers
        : form.audience.type === "status" ? [{ id: "active", name: "Active" }, { id: "inactive", name: "Inactive" }, { id: "pending", name: "Pending" }]
        : [];

    const isDuesReminders = form.kind === "dues_reminders";

    return (
        <Dialog open={!!editing} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="automated-email-editor">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">{form._new ? "New automated campaign" : `Edit "${form.name}"`}</DialogTitle>
                </DialogHeader>
                <div className="space-y-5 mt-2">
                    {isDuesReminders && (
                        <div className="rounded-2xl border-2 border-primary/30 bg-primary/5 px-4 py-3 text-sm leading-relaxed" data-testid="dues-reminder-info">
                            <div className="font-bold text-primary mb-1.5 flex items-center gap-2">
                                <Clock className="h-4 w-4" /> System-managed campaign
                            </div>
                            <p className="text-foreground/80">
                                This daily job emails every active member at four cadence points based on their <code className="font-mono text-xs bg-white/60 px-1.5 py-0.5 rounded">membership_expires_at</code>:
                            </p>
                            <ul className="list-disc ml-6 mt-1.5 space-y-0.5 text-foreground/80">
                                <li><strong>30 days</strong> before expiration — friendly heads-up</li>
                                <li><strong>15 days</strong> before — reminder</li>
                                <li><strong>5 days</strong> before — final notice</li>
                                <li><strong>1 day after</strong> — 15-day grace period + $75.00 reactivation-fee warning (members must contact the National office to reactivate)</li>
                            </ul>
                            <p className="text-foreground/80 mt-1.5">Once a member pays (extending their expiration), the cycle resets — reminders for the previous cycle stop automatically.</p>
                            <p className="text-foreground/80 mt-1.5 text-xs">Edit the subject + body for each stage below. Leave a field blank or click <strong>Reset</strong> to fall back to the default wording.</p>
                        </div>
                    )}
                    {isDuesReminders && duesDefaults && (
                        <div className="space-y-4" data-testid="dues-stage-editors">
                            <div className="flex flex-wrap gap-1.5">
                                <span className="text-xs text-muted-foreground mr-1">Available placeholders:</span>
                                {(duesDefaults.placeholders || []).map((p) => (
                                    <code key={p.tag} title={p.desc} className="text-[10px] bg-accent/40 text-accent-foreground rounded-full px-2 py-0.5 font-mono">{p.tag}</code>
                                ))}
                            </div>
                            {(duesDefaults.stages || []).map((sd) => {
                                const stageId = sd.stage;
                                const override = (form.stage_templates || {})[stageId] || {};
                                const def = (duesDefaults.defaults || {})[stageId] || { subject: "", body_html: "" };
                                const isCustom = !!(override.subject || override.body_html);
                                return (
                                    <div key={stageId} className="bg-muted/30 border border-border rounded-2xl p-4" data-testid={`dues-stage-${stageId}`}>
                                        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-[10px] uppercase tracking-widest font-bold bg-primary/15 text-primary rounded-full px-2 py-0.5">{sd.label}</span>
                                                {isCustom && <span className="text-[10px] uppercase tracking-widest font-bold bg-amber-100 text-amber-700 rounded-full px-2 py-0.5">Customized</span>}
                                                <span className="text-xs text-muted-foreground font-mono">{stageId}</span>
                                            </div>
                                            {isCustom && (
                                                <Button type="button" variant="ghost" size="sm" onClick={() => resetStage(stageId)} className="text-xs rounded-full" data-testid={`dues-stage-reset-${stageId}`}>
                                                    Reset to default
                                                </Button>
                                            )}
                                        </div>
                                        <div className="mb-2">
                                            <Label className="text-xs">Subject</Label>
                                            <Input
                                                value={override.subject ?? def.subject}
                                                onChange={(e) => setStage(stageId, "subject", e.target.value)}
                                                className="rounded-xl mt-1 text-sm"
                                                data-testid={`dues-stage-subject-${stageId}`}
                                            />
                                        </div>
                                        <div>
                                            <Label className="text-xs">Body HTML</Label>
                                            <Textarea
                                                rows={5}
                                                value={override.body_html ?? def.body_html}
                                                onChange={(e) => setStage(stageId, "body_html", e.target.value)}
                                                className="rounded-xl mt-1 font-mono text-xs"
                                                data-testid={`dues-stage-body-${stageId}`}
                                            />
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div>
                            <Label>Campaign name</Label>
                            <Input value={form.name || ""} onChange={(e) => set("name", e.target.value)} className="rounded-xl mt-1.5" data-testid="auto-name-input" />
                            {form.is_builtin && <p className="text-xs text-muted-foreground mt-1">This is a built-in campaign — admins can rename it freely.</p>}
                        </div>
                        <div>
                            <Label>Schedule (cron)</Label>
                            <div className="flex gap-2 mt-1.5">
                                <Input value={form.cron_expression || ""} onChange={(e) => set("cron_expression", e.target.value)} className="rounded-xl flex-1 font-mono text-sm" placeholder="0 9 * * 1" data-testid="auto-cron-input" />
                                <Select value="_custom" onValueChange={(v) => v !== "_custom" && set("cron_expression", v)}>
                                    <SelectTrigger className="w-auto rounded-xl text-xs" data-testid="cron-preset"><SelectValue placeholder="Presets" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="_custom">Presets…</SelectItem>
                                        {COMMON_SCHEDULES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <p className="text-xs text-muted-foreground mt-1.5">Format: <code className="font-mono">min hour day mo dow</code>. All times UTC.</p>
                        </div>
                    </div>
                    <div>
                        <Label>Subject line</Label>
                        <Input value={form.subject || ""} onChange={(e) => set("subject", e.target.value)} className="rounded-xl mt-1.5" placeholder="Your AOP weekly digest — {{member_name}}" data-testid="auto-subject-input" disabled={isDuesReminders} />
                        {isDuesReminders && <p className="text-xs text-muted-foreground mt-1">Each stage has its own subject line — see Preview.</p>}
                    </div>
                    {!isDuesReminders && (
                    <div>
                        <div className="flex items-center justify-between mb-1.5">
                            <Label>Body (HTML)</Label>
                            <div className="text-xs text-muted-foreground">Insert merge tag:</div>
                        </div>
                        <div className="flex flex-wrap gap-1.5 mb-2" data-testid="auto-merge-tags">
                            {tags.map((t) => (
                                <button key={t.tag} type="button" onClick={() => insertTag(t.tag)} className="text-[11px] bg-accent/40 hover:bg-accent text-accent-foreground rounded-full px-2.5 py-1 font-mono" title={t.desc} data-testid={`merge-tag-${t.tag}`}>
                                    {t.tag}
                                </button>
                            ))}
                        </div>
                        <Textarea
                            value={form.body_html || ""}
                            onChange={(e) => set("body_html", e.target.value)}
                            rows={12}
                            className="rounded-xl font-mono text-xs"
                            data-testid="auto-body-textarea"
                        />
                    </div>
                    )}

                    {!isDuesReminders && (
                    <div>
                        <Label>Recipient audience</Label>
                        <div className="grid sm:grid-cols-2 gap-3 mt-1.5">
                            <Select value={form.audience.type} onValueChange={setAudienceType}>
                                <SelectTrigger className="rounded-xl" data-testid="auto-audience-type"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All active members</SelectItem>
                                    <SelectItem value="chapter">By chapter</SelectItem>
                                    <SelectItem value="tier">By tier</SelectItem>
                                    <SelectItem value="status">By status</SelectItem>
                                </SelectContent>
                            </Select>
                            {form.audience.type !== "all" && audienceOptions.length > 0 && (
                                <div className="border border-border rounded-xl p-2 max-h-32 overflow-y-auto space-y-1" data-testid="auto-audience-ids">
                                    {audienceOptions.map((o) => (
                                        <label key={o.id} className="flex items-center gap-2 text-sm hover:bg-muted/40 rounded-lg px-2 py-1 cursor-pointer">
                                            <input type="checkbox" checked={form.audience.ids.includes(o.id)} onChange={() => toggleAudienceId(o.id)} />
                                            {o.name}
                                        </label>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                    )}

                    {!isDuesReminders && (
                    <div>
                        <Label>Sections to include</Label>
                        <p className="text-xs text-muted-foreground">Each tag only renders if its section is enabled.</p>
                        <div className="grid sm:grid-cols-2 gap-2 mt-2">
                            {Object.entries(SECTION_LABELS).map(([k, label]) => (
                                <label key={k} className="flex items-center gap-2 bg-muted/30 hover:bg-muted/50 rounded-xl px-3 py-2 cursor-pointer text-sm" data-testid={`auto-section-${k}`}>
                                    <input type="checkbox" checked={form.sections?.[k] !== false} onChange={() => toggleSection(k)} />
                                    {label}
                                </label>
                            ))}
                        </div>
                    </div>
                    )}

                    <div className="flex items-center gap-3">
                        <Switch checked={!!form.is_active} onCheckedChange={(v) => set("is_active", v)} id="auto-active-switch" />
                        <Label htmlFor="auto-active-switch">Active — schedule will fire automatically</Label>
                    </div>

                    {!form._new && (
                        <div>
                            <Button type="button" variant="outline" onClick={preview} className="rounded-full" data-testid="auto-preview-btn">
                                <Eye className="h-4 w-4 mr-1.5" /> Preview as me
                            </Button>
                            {previewHtml && (
                                <div className="mt-3 border border-border rounded-2xl overflow-hidden bg-muted/30" data-testid="auto-preview-frame">
                                    <iframe srcDoc={previewHtml} title="Preview" className="w-full h-96 bg-white" />
                                </div>
                            )}
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} className="rounded-full" type="button">Cancel</Button>
                    <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="auto-save-btn">
                        {busy ? "Saving…" : "Save campaign"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
