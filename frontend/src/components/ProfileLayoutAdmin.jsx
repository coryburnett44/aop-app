import { useEffect, useState } from "react";
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, arrayMove, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "./ui/select";
import { GripVertical, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

const FIELD_TYPES = [
    { value: "text", label: "Text" },
    { value: "textarea", label: "Long text" },
    { value: "date", label: "Date" },
    { value: "number", label: "Number" },
    { value: "select", label: "Dropdown" },
];

/**
 * Admin-side layout manager for the member Profile page.
 *
 * Two concerns, side by side:
 *   1. Section order — built-in section keys (identity / contact / fraternity /
 *      languages / education / social) plus any custom section keys. Drag the
 *      grip handle to reorder; eye toggle hides a section without deleting it.
 *      Order applies GLOBALLY to every member's profile.
 *   2. Custom fields — admin-defined extra inputs that render on the member
 *      profile under a "Custom Fields" section. Members fill them in; values
 *      live in users.custom_fields keyed by the field's `key` slug.
 *
 * Persisted to GET/PUT /api/site-settings as `profile_layout` + `profile_custom_fields`.
 */
export default function ProfileLayoutAdmin() {
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [sections, setSections] = useState([]);
    const [fields, setFields] = useState([]);

    useEffect(() => { load(); }, []);
    async function load() {
        setLoading(true);
        try {
            const { data } = await api.get("/site-settings");
            setSections(data.profile_layout || []);
            setFields(data.profile_custom_fields || []);
        } catch (e) {
            toast.error("Could not load profile layout");
        }
        setLoading(false);
    }

    const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

    function onDragEnd(ev) {
        const { active, over } = ev;
        if (!over || active.id === over.id) return;
        const oldIdx = sections.findIndex((s) => s.key === active.id);
        const newIdx = sections.findIndex((s) => s.key === over.id);
        if (oldIdx < 0 || newIdx < 0) return;
        setSections((arr) => arrayMove(arr, oldIdx, newIdx));
    }

    function updateSection(i, patch) { setSections((arr) => arr.map((s, idx) => idx === i ? { ...s, ...patch } : s)); }
    function addSection() {
        const key = window.prompt("New section key (lowercase, no spaces — e.g. 'tax_records'):");
        if (!key) return;
        const norm = key.toLowerCase().replace(/[^a-z0-9_]+/g, "_");
        if (sections.some((s) => s.key === norm)) { toast.error("Key already exists"); return; }
        setSections((arr) => [...arr, { key: norm, visible: true, label: key }]);
    }
    function removeSection(i) {
        if (!window.confirm("Remove this section from the layout?")) return;
        setSections((arr) => arr.filter((_, idx) => idx !== i));
    }

    function addField() {
        if (fields.length >= 12) { toast.error("Maximum of 12 custom fields"); return; }
        setFields((arr) => [...arr, { key: `field_${arr.length + 1}`, label: "New field", type: "text", options: [], required: false, help_text: "" }]);
    }
    function updateField(i, patch) { setFields((arr) => arr.map((f, idx) => idx === i ? { ...f, ...patch } : f)); }
    function removeField(i) { setFields((arr) => arr.filter((_, idx) => idx !== i)); }

    async function save() {
        setBusy(true);
        try {
            // Server-side validation: keys must be unique and snake_case.
            const keys = new Set();
            for (const f of fields) {
                if (!/^[a-z0-9_]+$/.test(f.key)) { toast.error(`Custom field key "${f.key}" must be lowercase letters/digits/underscores`); setBusy(false); return; }
                if (keys.has(f.key)) { toast.error(`Duplicate field key: ${f.key}`); setBusy(false); return; }
                keys.add(f.key);
            }
            const payload = {
                profile_layout: sections,
                profile_custom_fields: fields.map((f) => ({
                    ...f,
                    options: typeof f.options === "string" ? f.options.split(",").map((o) => o.trim()).filter(Boolean) : (f.options || []),
                })),
            };
            await api.put("/site-settings", payload);
            toast.success("Profile layout saved");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Save failed");
        }
        setBusy(false);
    }

    if (loading) return <div className="text-muted-foreground text-center py-10">Loading layout…</div>;

    return (
        <div className="space-y-6" data-testid="profile-layout-admin">
            <div className="rounded-2xl border bg-card p-5">
                <h3 className="font-heading text-lg font-bold mb-1">Profile section order</h3>
                <p className="text-xs text-muted-foreground mb-4">Drag to reorder. Toggle the eye to hide a section without losing data. This order applies to every member's profile page.</p>
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                    <SortableContext items={sections.map((s) => s.key)} strategy={verticalListSortingStrategy}>
                        <div className="space-y-2" data-testid="profile-layout-list">
                            {sections.map((s, i) => (
                                <SortableSectionRow
                                    key={s.key}
                                    section={s}
                                    onLabel={(v) => updateSection(i, { label: v })}
                                    onToggleVisible={() => updateSection(i, { visible: !s.visible })}
                                    onRemove={() => removeSection(i)}
                                />
                            ))}
                        </div>
                    </SortableContext>
                </DndContext>
                <Button type="button" variant="outline" size="sm" onClick={addSection} className="rounded-full mt-3" data-testid="add-profile-section-btn">
                    <Plus className="h-4 w-4 mr-1" /> Add section
                </Button>
            </div>

            <div className="rounded-2xl border bg-card p-5">
                <div className="flex items-center justify-between mb-1">
                    <div>
                        <h3 className="font-heading text-lg font-bold">Custom profile fields</h3>
                        <p className="text-xs text-muted-foreground">Up to 12 admin-defined fields that render on every member's profile.</p>
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={addField} disabled={fields.length >= 12} className="rounded-full" data-testid="add-custom-field-btn">
                        <Plus className="h-4 w-4 mr-1" /> Add field ({fields.length}/12)
                    </Button>
                </div>
                {fields.length === 0 && <div className="text-xs text-muted-foreground italic mt-3">No custom fields configured.</div>}
                <div className="space-y-3 mt-3">
                    {fields.map((f, i) => (
                        <div key={i} className="bg-muted/30 border rounded-xl p-3 space-y-2" data-testid={`custom-field-row-${i}`}>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                <div>
                                    <Label className="text-[10px] uppercase tracking-wider">Key (slug)</Label>
                                    <Input value={f.key} onChange={(e) => updateField(i, { key: e.target.value.toLowerCase().replace(/[^a-z0-9_]+/g, "_") })} className="rounded-xl text-sm h-9 font-mono" data-testid={`custom-field-key-${i}`} />
                                </div>
                                <div>
                                    <Label className="text-[10px] uppercase tracking-wider">Label</Label>
                                    <Input value={f.label} onChange={(e) => updateField(i, { label: e.target.value })} className="rounded-xl text-sm h-9" data-testid={`custom-field-label-${i}`} />
                                </div>
                                <div>
                                    <Label className="text-[10px] uppercase tracking-wider">Type</Label>
                                    <Select value={f.type} onValueChange={(v) => updateField(i, { type: v })}>
                                        <SelectTrigger className="rounded-xl text-sm h-9" data-testid={`custom-field-type-${i}`}><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {FIELD_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-end">
                                <Input value={f.help_text || ""} onChange={(e) => updateField(i, { help_text: e.target.value })} placeholder="Help text (shown under the input)" className="rounded-xl text-sm h-9" data-testid={`custom-field-help-${i}`} />
                                <Button type="button" size="sm" variant="ghost" onClick={() => removeField(i)} className="rounded-full text-rose-600 hover:bg-rose-50" data-testid={`custom-field-remove-${i}`}>
                                    <Trash2 className="h-4 w-4 mr-1" /> Remove
                                </Button>
                            </div>
                            {f.type === "select" && (
                                <Input value={Array.isArray(f.options) ? f.options.join(", ") : f.options || ""} onChange={(e) => updateField(i, { options: e.target.value })} placeholder="Comma-separated options (e.g. Mon, Tue, Wed)" className="rounded-xl text-sm h-9" data-testid={`custom-field-options-${i}`} />
                            )}
                        </div>
                    ))}
                </div>
            </div>

            <div className="flex justify-end">
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="profile-layout-save-btn">{busy ? "Saving…" : "Save layout"}</Button>
            </div>
        </div>
    );
}

function SortableSectionRow({ section, onLabel, onToggleVisible, onRemove }) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: section.key });
    const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.6 : 1 };
    const isBuiltIn = ["identity", "contact", "fraternity", "languages", "education", "social"].includes(section.key);
    return (
        <div ref={setNodeRef} style={style} className={`flex items-center gap-2 bg-white border rounded-xl px-3 py-2 ${section.visible ? "" : "opacity-50"}`} data-testid={`profile-layout-row-${section.key}`}>
            <button type="button" className="touch-none cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground" {...attributes} {...listeners} data-testid={`profile-layout-drag-${section.key}`}>
                <GripVertical className="h-4 w-4" />
            </button>
            <code className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground w-24 shrink-0">{section.key}</code>
            <Input value={section.label || ""} onChange={(e) => onLabel(e.target.value)} className="rounded-lg text-sm h-8 flex-1" data-testid={`profile-layout-label-${section.key}`} />
            <button type="button" onClick={onToggleVisible} className="text-muted-foreground hover:text-foreground p-1" title={section.visible ? "Hide section" : "Show section"} data-testid={`profile-layout-toggle-${section.key}`}>
                {section.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            </button>
            {!isBuiltIn && (
                <button type="button" onClick={onRemove} className="text-rose-500 hover:text-rose-700 p-1" title="Remove custom section">
                    <Trash2 className="h-4 w-4" />
                </button>
            )}
        </div>
    );
}
