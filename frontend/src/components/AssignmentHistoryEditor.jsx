import { useState, useEffect } from "react";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "./ui/select";
import { Button } from "./ui/button";
import { Plus, Trash2, ArrowUp, ArrowDown } from "lucide-react";

export const RANK_OPTIONS = [
    { value: "Grand Sirius", label: "Grand Sirius (5★)" },
    { value: "Master Sirius", label: "Master Sirius (4★)" },
    { value: "Senior Sirius", label: "Senior Sirius (3★)" },
    { value: "Advanced Sirius", label: "Advanced Sirius (2★)" },
    { value: "Junior Sirius", label: "Junior Sirius (1★)" },
    { value: "Eagle", label: "Eagle" },
    { value: "Clover", label: "Clover" },
    { value: "Guardian", label: "Guardian" },
];

const MAX_ASSIGNMENTS = 30;

/**
 * Admin-only editor for a member's assignment history.
 *
 * Each row = a single-line strip listing (in order): start date · end date or
 * "Current" · chapter · state · location · duty title · rank. Rows display
 * "current first" automatically when read back via the Personnel Brief; in this
 * admin editor we let the admin re-order with ↑ / ↓ for visual clarity.
 *
 * Compact-but-complete: all 8 ranks live in the dropdown including the
 * 5★ Grand Sirius down to Guardian per the user's spec.
 */
export default function AssignmentHistoryEditor({ value, onChange, chapters = [] }) {
    const [items, setItems] = useState(value || []);
    useEffect(() => { setItems(value || []); }, [value]);

    function update(i, patch) {
        const next = items.map((it, idx) => idx === i ? { ...it, ...patch } : it);
        setItems(next);
        onChange(next);
    }

    function add() {
        if (items.length >= MAX_ASSIGNMENTS) return;
        // New rows default to is_current=false so the previous "current" entry stays current.
        const next = [...items, {
            start_date: "", end_date: "", is_current: false,
            chapter_id: "", chapter_name: "", state: "", location: "",
            duty_title: "", rank: "",
        }];
        setItems(next);
        onChange(next);
    }

    function remove(i) {
        const next = items.filter((_, idx) => idx !== i);
        setItems(next);
        onChange(next);
    }

    function move(i, dir) {
        const j = i + dir;
        if (j < 0 || j >= items.length) return;
        const next = [...items];
        [next[i], next[j]] = [next[j], next[i]];
        setItems(next);
        onChange(next);
    }

    return (
        <div className="rounded-2xl border-2 border-slate-200 bg-slate-50 p-4 space-y-3" data-testid="assignment-history-editor">
            <div className="flex items-center justify-between">
                <div>
                    <Label className="text-base font-semibold">Assignment history</Label>
                    <p className="text-xs text-muted-foreground">List from current down to first. Mark exactly one row as "Current".</p>
                </div>
                <Button type="button" onClick={add} disabled={items.length >= MAX_ASSIGNMENTS} size="sm" variant="outline" className="rounded-full" data-testid="add-assignment-btn">
                    <Plus className="h-4 w-4 mr-1" /> Add row
                </Button>
            </div>
            {items.length === 0 && <div className="text-xs text-muted-foreground italic">No assignments yet.</div>}
            {items.map((it, i) => (
                <div key={i} className={`bg-white border rounded-xl p-3 ${it.is_current ? "border-emerald-300 ring-1 ring-emerald-200" : ""}`} data-testid={`assignment-row-${i}`}>
                    <div className="grid grid-cols-12 gap-2 items-end">
                        <div className="col-span-12 sm:col-span-2">
                            <Label className="text-[10px] uppercase tracking-wider">Start</Label>
                            <Input
                                type="date"
                                value={it.start_date || ""}
                                onChange={(e) => update(i, { start_date: e.target.value })}
                                className="rounded-xl text-xs h-9"
                                data-testid={`assignment-start-${i}`}
                            />
                        </div>
                        <div className="col-span-12 sm:col-span-2">
                            <Label className="text-[10px] uppercase tracking-wider">End</Label>
                            <div className="flex items-center gap-1.5">
                                <Input
                                    type="date"
                                    value={it.end_date || ""}
                                    onChange={(e) => update(i, { end_date: e.target.value, is_current: false })}
                                    disabled={it.is_current}
                                    className="rounded-xl text-xs h-9 flex-1"
                                    data-testid={`assignment-end-${i}`}
                                />
                            </div>
                            <label className="flex items-center gap-1.5 mt-1 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={!!it.is_current}
                                    onChange={(e) => update(i, { is_current: e.target.checked, end_date: e.target.checked ? "" : it.end_date })}
                                    className="h-3.5 w-3.5 accent-emerald-600"
                                    data-testid={`assignment-current-${i}`}
                                />
                                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">Current</span>
                            </label>
                        </div>
                        <div className="col-span-6 sm:col-span-2">
                            <Label className="text-[10px] uppercase tracking-wider">Chapter</Label>
                            <Select value={it.chapter_id || "__custom__"} onValueChange={(v) => {
                                if (v === "__custom__") return;
                                const c = chapters.find((c) => c.id === v);
                                update(i, { chapter_id: v, chapter_name: c ? c.name : it.chapter_name });
                            }}>
                                <SelectTrigger className="rounded-xl text-xs h-9" data-testid={`assignment-chapter-${i}`}><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__custom__">— Custom —</SelectItem>
                                    {chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <Input
                                value={it.chapter_name || ""}
                                onChange={(e) => update(i, { chapter_name: e.target.value })}
                                placeholder="Custom name"
                                className="rounded-xl text-xs h-8 mt-1"
                                data-testid={`assignment-chapter-name-${i}`}
                            />
                        </div>
                        <div className="col-span-3 sm:col-span-1">
                            <Label className="text-[10px] uppercase tracking-wider">State</Label>
                            <Input value={it.state || ""} maxLength={3} onChange={(e) => update(i, { state: e.target.value.toUpperCase() })} className="rounded-xl text-xs h-9 uppercase" data-testid={`assignment-state-${i}`} />
                        </div>
                        <div className="col-span-9 sm:col-span-2">
                            <Label className="text-[10px] uppercase tracking-wider">Location</Label>
                            <Input value={it.location || ""} onChange={(e) => update(i, { location: e.target.value })} className="rounded-xl text-xs h-9" data-testid={`assignment-location-${i}`} />
                        </div>
                        <div className="col-span-12 sm:col-span-2">
                            <Label className="text-[10px] uppercase tracking-wider">Duty Title</Label>
                            <Input value={it.duty_title || ""} onChange={(e) => update(i, { duty_title: e.target.value })} className="rounded-xl text-xs h-9" data-testid={`assignment-duty-${i}`} />
                        </div>
                        <div className="col-span-12 sm:col-span-1">
                            <Label className="text-[10px] uppercase tracking-wider">Rank</Label>
                            <Select value={it.rank || "__none__"} onValueChange={(v) => update(i, { rank: v === "__none__" ? "" : v })}>
                                <SelectTrigger className="rounded-xl text-xs h-9" data-testid={`assignment-rank-${i}`}><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__none__">—</SelectItem>
                                    {RANK_OPTIONS.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div className="flex items-center justify-end gap-1 mt-2 pt-2 border-t border-slate-100">
                        <Button type="button" size="sm" variant="ghost" onClick={() => move(i, -1)} disabled={i === 0} className="rounded-full h-7 text-xs" data-testid={`assignment-up-${i}`}><ArrowUp className="h-3 w-3" /></Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => move(i, 1)} disabled={i === items.length - 1} className="rounded-full h-7 text-xs" data-testid={`assignment-down-${i}`}><ArrowDown className="h-3 w-3" /></Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => remove(i)} className="rounded-full h-7 text-xs text-rose-600 hover:bg-rose-50" data-testid={`assignment-remove-${i}`}><Trash2 className="h-3 w-3 mr-1" />Remove</Button>
                    </div>
                </div>
            ))}
        </div>
    );
}
