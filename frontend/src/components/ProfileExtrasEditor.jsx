import { useState, useEffect } from "react";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "./ui/select";
import { Button } from "./ui/button";
import { Plus, Trash2 } from "lucide-react";

export const MARITAL_OPTIONS = ["Single", "Engaged", "Domestic Partnership", "Married", "Divorced", "Widowed"];
export const PROFICIENCY_OPTIONS = ["Native", "Fluent", "Advanced", "Intermediate", "Basic"];
export const DEGREE_LEVEL_OPTIONS = ["HS Diploma", "Trade Cert", "Associate", "Bachelors", "Masters", "Masters Certificate", "Doctorate", "Doctor of Philosophy"];
export const DEGREE_TYPE_OPTIONS = ["AA", "AS", "BA", "BS", "MA", "MS", "MBA", "DBA", "Ph.D"];

const MAX_LANGUAGES = 3;
const MAX_DEGREES = 5;

/**
 * Self-service editor for member-side profile extras introduced in iteration 29:
 *   - Marital status (single dropdown — placed near Phone in Profile.jsx)
 *   - Up to 3 spoken languages (with speaking / reading / writing proficiency)
 *   - Up to 5 civilian degrees (level + type + field + institution + grad date)
 *
 * The shape of `value` is { marital_status, languages: [], civilian_degrees: [] }
 * and `onChange` is called with the new full object on every edit.
 *
 * Built as a single component (rather than three) so the layout stays cohesive
 * inside the Profile.jsx form scroll and the controlled-component contract is
 * minimal for the parent.
 */
export function MaritalStatusField({ value, onChange }) {
    return (
        <div>
            <Label>Marital status <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
            <Select value={value || "__none__"} onValueChange={(v) => onChange(v === "__none__" ? "" : v)}>
                <SelectTrigger className="rounded-xl mt-1.5" data-testid="profile-marital-status"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>
                    <SelectItem value="__none__">— None —</SelectItem>
                    {MARITAL_OPTIONS.map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
}

export function LanguagesEditor({ value, onChange }) {
    const [items, setItems] = useState(value || []);
    useEffect(() => { setItems(value || []); }, [value]);
    function update(i, patch) {
        const next = items.map((it, idx) => idx === i ? { ...it, ...patch } : it);
        setItems(next);
        onChange(next);
    }
    function add() {
        if (items.length >= MAX_LANGUAGES) return;
        const next = [...items, { language: "", speaking: "", reading: "", writing: "", year_accomplished: null }];
        setItems(next);
        onChange(next);
    }
    function remove(i) {
        const next = items.filter((_, idx) => idx !== i);
        setItems(next);
        onChange(next);
    }

    return (
        <div className="rounded-2xl border-2 border-slate-200 bg-slate-50 p-4 space-y-3" data-testid="languages-editor">
            <div className="flex items-center justify-between">
                <div>
                    <Label className="text-base font-semibold">Languages spoken</Label>
                    <p className="text-xs text-muted-foreground">Up to 3. Lists on your Personnel Brief.</p>
                </div>
                <Button type="button" onClick={add} disabled={items.length >= MAX_LANGUAGES} size="sm" variant="outline" className="rounded-full" data-testid="add-language-btn">
                    <Plus className="h-4 w-4 mr-1" /> Add ({items.length}/{MAX_LANGUAGES})
                </Button>
            </div>
            {items.length === 0 && <div className="text-xs text-muted-foreground italic">No languages added yet.</div>}
            {items.map((it, i) => (
                <div key={i} className="bg-white border rounded-xl p-3" data-testid={`language-row-${i}`}>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                        <Input
                            placeholder="Language (e.g. English)"
                            value={it.language || ""}
                            onChange={(e) => update(i, { language: e.target.value })}
                            className="rounded-xl text-sm sm:col-span-2"
                            data-testid={`language-name-${i}`}
                        />
                        <ProficiencySelect value={it.speaking} onChange={(v) => update(i, { speaking: v })} placeholder="Speaking" testid={`language-speaking-${i}`} />
                        <ProficiencySelect value={it.reading} onChange={(v) => update(i, { reading: v })} placeholder="Reading" testid={`language-reading-${i}`} />
                        <ProficiencySelect value={it.writing} onChange={(v) => update(i, { writing: v })} placeholder="Writing" testid={`language-writing-${i}`} />
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-[1fr_auto] gap-2 mt-2">
                        <Input
                            type="number"
                            placeholder="Year accomplished (e.g. 2010)"
                            min="1950"
                            max={new Date().getFullYear() + 1}
                            value={it.year_accomplished || ""}
                            onChange={(e) => update(i, { year_accomplished: e.target.value ? Number(e.target.value) : null })}
                            className="rounded-xl text-sm"
                            data-testid={`language-year-${i}`}
                        />
                        <Button type="button" size="sm" variant="ghost" onClick={() => remove(i)} className="rounded-full text-rose-600 hover:bg-rose-50" data-testid={`language-remove-${i}`}>
                            <Trash2 className="h-4 w-4 mr-1" /> Remove
                        </Button>
                    </div>
                </div>
            ))}
        </div>
    );
}

function ProficiencySelect({ value, onChange, placeholder, testid }) {
    return (
        <Select value={value || "__none__"} onValueChange={(v) => onChange(v === "__none__" ? "" : v)}>
            <SelectTrigger className="rounded-xl text-sm" data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
            <SelectContent>
                <SelectItem value="__none__">— {placeholder} —</SelectItem>
                {PROFICIENCY_OPTIONS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
            </SelectContent>
        </Select>
    );
}

export function CivilianDegreesEditor({ value, onChange }) {
    const [items, setItems] = useState(value || []);
    useEffect(() => { setItems(value || []); }, [value]);
    function update(i, patch) {
        const next = items.map((it, idx) => idx === i ? { ...it, ...patch } : it);
        setItems(next);
        onChange(next);
    }
    function add() {
        if (items.length >= MAX_DEGREES) return;
        const next = [...items, { degree_level: "", degree_type: "", field_of_study: "", institution: "", graduation_month: null, graduation_year: null }];
        setItems(next);
        onChange(next);
    }
    function remove(i) {
        const next = items.filter((_, idx) => idx !== i);
        setItems(next);
        onChange(next);
    }

    return (
        <div className="rounded-2xl border-2 border-slate-200 bg-slate-50 p-4 space-y-3" data-testid="degrees-editor">
            <div className="flex items-center justify-between">
                <div>
                    <Label className="text-base font-semibold">Civilian education</Label>
                    <p className="text-xs text-muted-foreground">Up to 5 degrees. Sorted chronologically on your Personnel Brief.</p>
                </div>
                <Button type="button" onClick={add} disabled={items.length >= MAX_DEGREES} size="sm" variant="outline" className="rounded-full" data-testid="add-degree-btn">
                    <Plus className="h-4 w-4 mr-1" /> Add ({items.length}/{MAX_DEGREES})
                </Button>
            </div>
            {items.length === 0 && <div className="text-xs text-muted-foreground italic">No degrees added yet.</div>}
            {items.map((it, i) => (
                <div key={i} className="bg-white border rounded-xl p-3 space-y-2" data-testid={`degree-row-${i}`}>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <Select value={it.degree_level || "__none__"} onValueChange={(v) => update(i, { degree_level: v === "__none__" ? "" : v })}>
                            <SelectTrigger className="rounded-xl text-sm" data-testid={`degree-level-${i}`}><SelectValue placeholder="Degree level" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">— Degree level —</SelectItem>
                                {DEGREE_LEVEL_OPTIONS.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={it.degree_type || "__none__"} onValueChange={(v) => update(i, { degree_type: v === "__none__" ? "" : v })}>
                            <SelectTrigger className="rounded-xl text-sm" data-testid={`degree-type-${i}`}><SelectValue placeholder="Degree type (BS, MBA…)" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">— Type —</SelectItem>
                                {DEGREE_TYPE_OPTIONS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <Input
                        placeholder="Field of study (e.g. Biology, Communications)"
                        value={it.field_of_study || ""}
                        onChange={(e) => update(i, { field_of_study: e.target.value })}
                        className="rounded-xl text-sm"
                        data-testid={`degree-field-${i}`}
                    />
                    <Input
                        placeholder="College / University"
                        value={it.institution || ""}
                        onChange={(e) => update(i, { institution: e.target.value })}
                        className="rounded-xl text-sm"
                        data-testid={`degree-institution-${i}`}
                    />
                    <div className="grid grid-cols-2 sm:grid-cols-[120px_120px_auto] gap-2">
                        <Select value={it.graduation_month ? String(it.graduation_month) : "__none__"} onValueChange={(v) => update(i, { graduation_month: v === "__none__" ? null : Number(v) })}>
                            <SelectTrigger className="rounded-xl text-sm" data-testid={`degree-month-${i}`}><SelectValue placeholder="Month" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">Month</SelectItem>
                                {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].map((m, idx) => (
                                    <SelectItem key={m} value={String(idx + 1)}>{m}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Input
                            type="number"
                            placeholder="Year"
                            min="1940"
                            max={new Date().getFullYear() + 6}
                            value={it.graduation_year || ""}
                            onChange={(e) => update(i, { graduation_year: e.target.value ? Number(e.target.value) : null })}
                            className="rounded-xl text-sm"
                            data-testid={`degree-year-${i}`}
                        />
                        <Button type="button" size="sm" variant="ghost" onClick={() => remove(i)} className="rounded-full text-rose-600 hover:bg-rose-50 ml-auto" data-testid={`degree-remove-${i}`}>
                            <Trash2 className="h-4 w-4 mr-1" /> Remove
                        </Button>
                    </div>
                </div>
            ))}
        </div>
    );
}
