import { useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Plus, Trash2, Upload, ArrowUp, ArrowDown, Users } from "lucide-react";
import { toast } from "sonner";

/**
 * Admin editor for the homepage Leadership Team section.
 * Receives the current items + setters from the parent (SiteSettingsAdmin)
 * so the entire site-settings form saves in one call via the parent's Save button.
 */
export default function LeadershipTeamAdmin({ form, set }) {
    const items = form.leadership_team_items || [];
    const [uploadingIdx, setUploadingIdx] = useState(null);

    function setItem(idx, key, value) {
        set("leadership_team_items", items.map((it, i) => (i === idx ? { ...it, [key]: value } : it)));
    }
    function addItem() {
        set("leadership_team_items", [...items, { term: "", image_url: "", alt: "" }]);
    }
    function removeItem(idx) {
        if (!window.confirm("Remove this leadership term?")) return;
        set("leadership_team_items", items.filter((_, i) => i !== idx));
    }
    function move(idx, dir) {
        const swap = idx + dir;
        if (swap < 0 || swap >= items.length) return;
        const next = items.slice();
        [next[idx], next[swap]] = [next[swap], next[idx]];
        set("leadership_team_items", next);
    }
    async function uploadImage(idx, file) {
        if (!file) return;
        setUploadingIdx(idx);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/leadership/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setItem(idx, "image_url", data.url);
            toast.success("Image uploaded — click Save to publish");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Upload failed");
        }
        setUploadingIdx(null);
    }

    return (
        <div data-testid="leadership-team-admin">
            <div className="flex items-center gap-2 mb-2">
                <Users className="h-4 w-4 text-muted-foreground" />
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground">Leadership Team section</h4>
            </div>
            <p className="text-xs text-muted-foreground mb-3">Set the eyebrow text, section title, and the banner images shown on the homepage Leadership Team strip.</p>
            <div className="grid sm:grid-cols-2 gap-3 mb-4">
                <div>
                    <Label>Eyebrow</Label>
                    <Input
                        value={form.leadership_team_eyebrow || ""}
                        onChange={(e) => set("leadership_team_eyebrow", e.target.value)}
                        placeholder="National board"
                        className="rounded-xl mt-1.5"
                        data-testid="leadership-eyebrow-input"
                    />
                </div>
                <div>
                    <Label>Section title</Label>
                    <Input
                        value={form.leadership_team_title || ""}
                        onChange={(e) => set("leadership_team_title", e.target.value)}
                        placeholder="Leadership Team"
                        className="rounded-xl mt-1.5"
                        data-testid="leadership-title-input"
                    />
                </div>
            </div>

            <div className="space-y-3" data-testid="leadership-items-list">
                {items.length === 0 && (
                    <div className="text-sm text-center text-slate-500 py-8 border-2 border-dashed border-slate-300 rounded-xl">
                        No leadership terms yet. Click "Add term" to create the first one.
                    </div>
                )}
                {items.map((it, idx) => (
                    <div key={idx} className="bg-slate-50 border border-slate-200 rounded-2xl p-4" data-testid={`leadership-item-${idx}`}>
                        <div className="flex items-start gap-3 mb-3">
                            <div className="text-xs uppercase tracking-wider font-bold text-slate-400 pt-2 w-12">#{idx + 1}</div>
                            <div className="flex-1 grid sm:grid-cols-2 gap-3">
                                <div>
                                    <Label className="text-xs">Term</Label>
                                    <Input
                                        value={it.term || ""}
                                        onChange={(e) => setItem(idx, "term", e.target.value)}
                                        placeholder="2024-2026"
                                        className="rounded-xl mt-1"
                                        data-testid={`leadership-term-input-${idx}`}
                                    />
                                </div>
                                <div>
                                    <Label className="text-xs">Alt text (accessibility)</Label>
                                    <Input
                                        value={it.alt || ""}
                                        onChange={(e) => setItem(idx, "alt", e.target.value)}
                                        placeholder="2024-2026 — Names"
                                        className="rounded-xl mt-1"
                                        data-testid={`leadership-alt-input-${idx}`}
                                    />
                                </div>
                            </div>
                            <div className="flex flex-col gap-1 pt-1">
                                <Button variant="ghost" size="icon" onClick={() => move(idx, -1)} disabled={idx === 0} data-testid={`leadership-move-up-${idx}`}><ArrowUp className="h-4 w-4" /></Button>
                                <Button variant="ghost" size="icon" onClick={() => move(idx, 1)} disabled={idx === items.length - 1} data-testid={`leadership-move-down-${idx}`}><ArrowDown className="h-4 w-4" /></Button>
                                <Button variant="ghost" size="icon" onClick={() => removeItem(idx)} data-testid={`leadership-remove-${idx}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>

                        <div className="grid sm:grid-cols-[1fr_180px] gap-3">
                            <div>
                                <Label className="text-xs">Banner image URL</Label>
                                <div className="flex gap-2 mt-1">
                                    <Input
                                        value={it.image_url || ""}
                                        onChange={(e) => setItem(idx, "image_url", e.target.value)}
                                        placeholder="https://… or /api/files/…"
                                        className="rounded-xl flex-1"
                                        data-testid={`leadership-image-url-${idx}`}
                                    />
                                    <label className="rounded-xl border px-3 py-2 text-xs font-semibold cursor-pointer hover:bg-white transition-colors flex items-center gap-1.5" data-testid={`leadership-upload-${idx}`}>
                                        {uploadingIdx === idx ? "Uploading…" : (<><Upload className="h-3 w-3" />Upload</>)}
                                        <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(idx, e.target.files?.[0])} />
                                    </label>
                                </div>
                            </div>
                            {it.image_url ? (
                                <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
                                    <img src={it.image_url} alt="" className="block w-full h-24 object-contain" onError={(e) => { e.currentTarget.style.opacity = "0.3"; }} />
                                </div>
                            ) : (
                                <div className="border border-dashed border-slate-300 rounded-xl bg-white h-24 grid place-items-center text-[10px] text-slate-400 uppercase tracking-wider">Preview</div>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <Button variant="outline" size="sm" onClick={addItem} className="rounded-full mt-3" data-testid="leadership-add-btn">
                <Plus className="h-3 w-3 mr-1" /> Add term
            </Button>
        </div>
    );
}
