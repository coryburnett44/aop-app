import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Compass, MapPin, Plus, Trash2, Pencil, Star, ArrowRightLeft, Save, Users as UsersIcon } from "lucide-react";

/**
 * Iter 135 — Regions admin console.
 *
 * Full CRUD over the `app_regions` collection:
 *   • Create / edit / delete regions (name, description, color, emoji,
 *     display order, states list).
 *   • Assign a Governor per region — searchable member picker.
 *   • Move a member into a specific region regardless of their state
 *     (`region_override` on the user doc).
 */
export default function RegionsAdmin() {
    const [regions, setRegions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(null); // region being edited (or null)
    const [moving, setMoving] = useState(false);   // "move member" modal open

    async function reload() {
        try {
            setLoading(true);
            const { data } = await api.get("/regions");
            setRegions(data.regions || []);
        } finally {
            setLoading(false);
        }
    }
    useEffect(() => { reload(); }, []);

    async function del(r) {
        if (!window.confirm(`Delete "${r.name}"? Any member overrides pointing to this region will be cleared.`)) return;
        try {
            await api.delete(`/admin/regions/${r.id}`);
            toast.success(`Deleted ${r.name}`);
            reload();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Delete failed");
        }
    }

    function newRegion() {
        setEditing({
            id: "", name: "", description: "", emoji: "📍",
            color: "#0A2463", gradient_from: "#0A2463", gradient_to: "#3E5C99",
            order: (regions.at(-1)?.order || 100) + 1,
            governor_user_id: "",
            states: [],
        });
    }

    return (
        <div className="space-y-6" data-testid="regions-admin">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-heading font-bold">Regions</h2>
                    <p className="text-sm text-muted-foreground">Manage the geographic regions shown on <span className="font-mono">/regions</span>. Governors surface as a spotlight card on the public page.</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setMoving(true)} className="rounded-full" data-testid="admin-regions-move-member-btn">
                        <ArrowRightLeft className="h-4 w-4 mr-1.5" /> Move a member
                    </Button>
                    <Button onClick={newRegion} className="rounded-full" data-testid="admin-regions-new-btn">
                        <Plus className="h-4 w-4 mr-1.5" /> New region
                    </Button>
                </div>
            </div>

            {loading && <div className="text-sm text-muted-foreground">Loading…</div>}

            <div className="grid md:grid-cols-2 gap-4">
                {regions.map((r) => (
                    <div key={r.id} className="bg-card border border-border rounded-xl overflow-hidden shadow-warm" data-testid={`admin-region-card-${r.id}`}>
                        <div
                            className="text-white px-4 py-3 flex items-center justify-between"
                            style={{ background: `linear-gradient(135deg, ${r.gradient_from} 0%, ${r.gradient_to} 100%)` }}
                        >
                            <div className="flex items-center gap-2">
                                <span className="text-xl">{r.emoji}</span>
                                <div>
                                    <div className="font-semibold text-sm">{r.name}</div>
                                    <div className="text-[10px] opacity-85 font-mono">{r.id}</div>
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-lg font-black tabular-nums">{r.total}</div>
                                <div className="text-[9px] uppercase tracking-widest opacity-85">members</div>
                            </div>
                        </div>
                        <div className="p-4 space-y-3">
                            <div className="text-xs text-muted-foreground">{r.description || "—"}</div>
                            <div className="flex items-center gap-2 flex-wrap">
                                {r.governor ? (
                                    <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 font-medium" data-testid={`admin-region-governor-${r.id}`}>
                                        <Star className="h-3 w-3" /> Governor: {r.governor.name}
                                    </span>
                                ) : (
                                    <span className="text-[11px] text-muted-foreground italic">No governor assigned</span>
                                )}
                                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                    <Compass className="h-3 w-3" /> {r.states.length} states
                                </span>
                            </div>
                            <div className="text-xs">
                                <span className="font-medium">States: </span>
                                <span className="text-muted-foreground">{r.states.map((s) => `${s.code} (${s.count})`).join(" · ") || "—"}</span>
                            </div>
                            <div className="flex justify-end gap-2 pt-2 border-t border-border">
                                <Button variant="outline" size="sm" onClick={() => setEditing(r)} className="rounded-full text-xs" data-testid={`admin-region-edit-${r.id}`}>
                                    <Pencil className="h-3 w-3 mr-1" /> Edit
                                </Button>
                                <Button variant="outline" size="sm" onClick={() => del(r)} className="rounded-full text-xs text-red-600 hover:text-red-700" data-testid={`admin-region-delete-${r.id}`}>
                                    <Trash2 className="h-3 w-3 mr-1" /> Delete
                                </Button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {editing && <RegionEditor initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
            {moving && <MoveMemberDialog regions={regions} onClose={() => setMoving(false)} />}
        </div>
    );
}

/**
 * Region create/edit dialog. Handles governor lookup via the /members
 * search endpoint so admins don't have to remember user IDs.
 */
function RegionEditor({ initial, onClose, onSaved }) {
    const isNew = !initial.id;
    const [form, setForm] = useState(() => ({
        ...initial,
        states: initial.states.map((s) => ({ code: s.code, name: s.name })),
    }));
    const [busy, setBusy] = useState(false);
    const [governor, setGovernor] = useState(null); // resolved user object
    const [govQuery, setGovQuery] = useState("");
    const [govResults, setGovResults] = useState([]);

    // Preload the current governor's basic info.
    useEffect(() => {
        if (!form.governor_user_id) { setGovernor(null); return; }
        api.get(`/members/${form.governor_user_id}`)
            .then(({ data }) => setGovernor(data))
            .catch(() => setGovernor(null));
    }, [form.governor_user_id]);

    // Search members for the governor picker.
    useEffect(() => {
        if (!govQuery.trim()) { setGovResults([]); return; }
        const t = setTimeout(async () => {
            try {
                const { data } = await api.get("/members", { params: { q: govQuery } });
                setGovResults(data.slice(0, 8));
            } catch { setGovResults([]); }
        }, 250);
        return () => clearTimeout(t);
    }, [govQuery]);

    function setField(k, v) { setForm((f) => ({ ...f, [k]: v })); }

    function addState() {
        setForm((f) => ({ ...f, states: [...f.states, { code: "", name: "" }] }));
    }
    function updateState(idx, k, v) {
        setForm((f) => ({
            ...f,
            states: f.states.map((s, i) => i === idx ? { ...s, [k]: v } : s),
        }));
    }
    function removeState(idx) {
        setForm((f) => ({ ...f, states: f.states.filter((_, i) => i !== idx) }));
    }

    async function save() {
        // Basic client validation.
        if (!form.name.trim()) return toast.error("Name is required");
        const bad = form.states.find((s) => !s.code.trim() || !s.name.trim());
        if (bad) return toast.error("Every state needs a code and name");
        setBusy(true);
        try {
            const payload = {
                name: form.name.trim(),
                description: form.description || "",
                emoji: form.emoji || "📍",
                color: form.color || "#0A2463",
                gradient_from: form.gradient_from || form.color,
                gradient_to: form.gradient_to || form.color,
                order: Number(form.order) || 100,
                governor_user_id: form.governor_user_id || "",
                states: form.states.map((s) => ({
                    code: s.code.trim().toUpperCase(),
                    name: s.name.trim(),
                })),
            };
            if (isNew) {
                await api.post("/admin/regions", payload);
                toast.success("Region created");
            } else {
                await api.put(`/admin/regions/${form.id}`, payload);
                toast.success("Region updated");
            }
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Save failed");
        }
        setBusy(false);
    }

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="admin-region-editor">
                <DialogHeader>
                    <DialogTitle>{isNew ? "New region" : `Edit ${form.name}`}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="sm:col-span-2">
                            <label className="text-xs font-medium">Name</label>
                            <Input value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="e.g. Central-East Region" data-testid="admin-region-field-name" />
                        </div>
                        <div>
                            <label className="text-xs font-medium">Order</label>
                            <Input type="number" value={form.order} onChange={(e) => setField("order", e.target.value)} data-testid="admin-region-field-order" />
                        </div>
                    </div>
                    <div>
                        <label className="text-xs font-medium">Description</label>
                        <Textarea rows={2} value={form.description} onChange={(e) => setField("description", e.target.value)} placeholder="Comma-separated list of states shown under the region title" data-testid="admin-region-field-description" />
                    </div>
                    <div className="grid grid-cols-4 gap-3">
                        <div>
                            <label className="text-xs font-medium">Emoji</label>
                            <Input value={form.emoji} onChange={(e) => setField("emoji", e.target.value)} placeholder="📍" data-testid="admin-region-field-emoji" />
                        </div>
                        <div>
                            <label className="text-xs font-medium">Map color</label>
                            <Input type="color" value={form.color} onChange={(e) => setField("color", e.target.value)} data-testid="admin-region-field-color" />
                        </div>
                        <div>
                            <label className="text-xs font-medium">Gradient from</label>
                            <Input type="color" value={form.gradient_from} onChange={(e) => setField("gradient_from", e.target.value)} data-testid="admin-region-field-gradient-from" />
                        </div>
                        <div>
                            <label className="text-xs font-medium">Gradient to</label>
                            <Input type="color" value={form.gradient_to} onChange={(e) => setField("gradient_to", e.target.value)} data-testid="admin-region-field-gradient-to" />
                        </div>
                    </div>

                    <div className="rounded-xl border p-3 space-y-2">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="text-sm font-semibold">Governor</div>
                                <div className="text-[11px] text-muted-foreground">Featured in the spotlight card on the region page.</div>
                            </div>
                            {governor && <Button variant="outline" size="sm" onClick={() => { setField("governor_user_id", ""); setGovernor(null); }} className="rounded-full text-xs">Clear</Button>}
                        </div>
                        {governor ? (
                            <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-sm border border-amber-500/40">
                                <Star className="h-3.5 w-3.5 inline text-amber-500 fill-amber-400 mr-1" />
                                <span className="font-medium">{governor.name}</span>
                                <span className="text-xs text-muted-foreground ml-2">{governor.email}</span>
                            </div>
                        ) : (
                            <div>
                                <Input value={govQuery} onChange={(e) => setGovQuery(e.target.value)} placeholder="Search for a member by name or email…" data-testid="admin-region-field-governor-search" />
                                {govResults.length > 0 && (
                                    <div className="mt-1 rounded-lg border max-h-40 overflow-y-auto">
                                        {govResults.map((m) => (
                                            <button
                                                key={m.id}
                                                type="button"
                                                onClick={() => { setField("governor_user_id", m.id); setGovQuery(""); setGovResults([]); }}
                                                className="w-full text-left px-3 py-2 hover:bg-accent text-sm flex items-center gap-2"
                                                data-testid={`admin-region-governor-pick-${m.id}`}
                                            >
                                                <span className="font-medium">{m.name}</span>
                                                <span className="text-xs text-muted-foreground truncate">{m.email}</span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="rounded-xl border p-3">
                        <div className="flex items-center justify-between mb-2">
                            <div>
                                <div className="text-sm font-semibold">States</div>
                                <div className="text-[11px] text-muted-foreground">USPS 2-letter code (e.g. TX) + full name. Common variants are auto-generated so members show up regardless of how they typed their state.</div>
                            </div>
                            <Button variant="outline" size="sm" onClick={addState} className="rounded-full text-xs" data-testid="admin-region-add-state-btn">
                                <Plus className="h-3 w-3 mr-1" /> Add state
                            </Button>
                        </div>
                        <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                            {form.states.length === 0 && <div className="text-xs text-muted-foreground italic px-1">No states yet — add at least one.</div>}
                            {form.states.map((s, i) => (
                                <div key={i} className="flex items-center gap-2" data-testid={`admin-region-state-row-${i}`}>
                                    <Input value={s.code} onChange={(e) => updateState(i, "code", e.target.value)} placeholder="TX" className="w-24 uppercase" maxLength={4} />
                                    <Input value={s.name} onChange={(e) => updateState(i, "name", e.target.value)} placeholder="Texas" className="flex-1" />
                                    <Button variant="outline" size="sm" onClick={() => removeState(i)} className="text-red-600 rounded-full">
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
                <DialogFooter className="flex-row justify-end gap-2 pt-4 border-t">
                    <Button variant="outline" onClick={onClose} className="rounded-full">Cancel</Button>
                    <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="admin-region-save-btn">
                        <Save className="h-4 w-4 mr-1.5" /> {busy ? "Saving…" : (isNew ? "Create region" : "Save changes")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/**
 * "Move a member" dialog — searches members and lets the admin drop
 * them into any region (or clear the override so they fall back to their
 * state).
 */
function MoveMemberDialog({ regions, onClose }) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [selected, setSelected] = useState(null);
    const [targetRegion, setTargetRegion] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!query.trim()) { setResults([]); return; }
        const t = setTimeout(async () => {
            try {
                const { data } = await api.get("/members", { params: { q: query } });
                setResults(data.slice(0, 12));
            } catch { setResults([]); }
        }, 250);
        return () => clearTimeout(t);
    }, [query]);

    async function apply() {
        if (!selected) return;
        setBusy(true);
        try {
            // "__clear__" is our sentinel for the "clear override" option —
            // the backend expects an empty string to remove the override.
            const region_id = targetRegion === "__clear__" ? "" : targetRegion;
            await api.put(`/admin/members/${selected.id}/region`, { region_id });
            toast.success(region_id
                ? `Moved ${selected.name} into ${regions.find((r) => r.id === region_id)?.name || region_id}`
                : `Cleared region override for ${selected.name}`
            );
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Move failed");
        }
        setBusy(false);
    }

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-lg" data-testid="admin-region-move-dialog">
                <DialogHeader>
                    <DialogTitle>Move a member between regions</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">
                        Overrides count the member under the chosen region regardless of the state on their profile. Clear the override to revert to normal state-based bucketing.
                    </p>
                    {!selected ? (
                        <div>
                            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search members by name or email…" data-testid="admin-move-search" autoFocus />
                            <div className="mt-2 rounded-lg border max-h-[300px] overflow-y-auto">
                                {results.map((m) => (
                                    <button
                                        key={m.id}
                                        type="button"
                                        onClick={() => setSelected(m)}
                                        className="w-full text-left px-3 py-2 hover:bg-accent text-sm flex items-center gap-2 border-b border-border last:border-0"
                                        data-testid={`admin-move-pick-${m.id}`}
                                    >
                                        <UsersIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                        <span className="font-medium">{m.name}</span>
                                        <span className="text-xs text-muted-foreground truncate">{m.email}</span>
                                        {m.state && <span className="ml-auto text-[10px] font-mono text-muted-foreground">{m.state}</span>}
                                    </button>
                                ))}
                                {query && results.length === 0 && <div className="p-3 text-xs text-muted-foreground text-center">No results</div>}
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            <div className="p-3 rounded-lg border bg-muted/30 flex items-center justify-between">
                                <div>
                                    <div className="font-semibold text-sm">{selected.name}</div>
                                    <div className="text-xs text-muted-foreground">{selected.email} · state: {selected.state || "—"}</div>
                                </div>
                                <Button variant="outline" size="sm" onClick={() => setSelected(null)} className="rounded-full text-xs">Change</Button>
                            </div>
                            <div>
                                <label className="text-xs font-medium">Move to region</label>
                                <Select value={targetRegion} onValueChange={setTargetRegion}>
                                    <SelectTrigger data-testid="admin-move-target-region"><SelectValue placeholder="Pick a region…" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__clear__">— Clear override (use state) —</SelectItem>
                                        {regions.map((r) => (
                                            <SelectItem key={r.id} value={r.id}>{r.emoji} {r.name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    )}
                </div>
                <DialogFooter className="flex-row justify-end gap-2 pt-4 border-t">
                    <Button variant="outline" onClick={onClose} className="rounded-full">Close</Button>
                    <Button
                        onClick={() => apply()}
                        disabled={!selected || !targetRegion || busy}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid="admin-move-apply-btn"
                    >
                        <MapPin className="h-4 w-4 mr-1.5" /> {busy ? "Applying…" : "Apply"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
