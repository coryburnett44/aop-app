import { useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Plus, Trash2, Upload, ArrowUp, ArrowDown, UserCircle } from "lucide-react";
import { toast } from "sonner";

/**
 * Admin editor for the homepage Founders strip.
 * Same pattern as LeadershipTeamAdmin — but uses /api/founders/upload-image
 * and the items shape is { name, image_url, role }.
 */
export default function FoundersAdmin({ form, set }) {
    const items = form.founders_items || [];
    const [uploadingIdx, setUploadingIdx] = useState(null);

    function setItem(idx, key, value) {
        set("founders_items", items.map((it, i) => (i === idx ? { ...it, [key]: value } : it)));
    }
    function addItem() {
        set("founders_items", [...items, { name: "", image_url: "", role: "Founder" }]);
    }
    function removeItem(idx) {
        if (!window.confirm("Remove this founder?")) return;
        set("founders_items", items.filter((_, i) => i !== idx));
    }
    function move(idx, dir) {
        const swap = idx + dir;
        if (swap < 0 || swap >= items.length) return;
        const next = items.slice();
        [next[idx], next[swap]] = [next[swap], next[idx]];
        set("founders_items", next);
    }
    async function uploadImage(idx, file) {
        if (!file) return;
        setUploadingIdx(idx);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/founders/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setItem(idx, "image_url", data.url);
            toast.success("Image uploaded — click Save to publish");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Upload failed");
        }
        setUploadingIdx(null);
    }

    return (
        <div data-testid="founders-admin">
            <div className="flex items-center gap-2 mb-2">
                <UserCircle className="h-4 w-4 text-muted-foreground" />
                <h4 className="font-bold uppercase tracking-wider text-xs text-muted-foreground">Founders strip (homepage)</h4>
            </div>
            <p className="text-xs text-muted-foreground mb-3">The portrait strip at the top of the homepage. Section is hidden if there are no founders.</p>
            <div className="grid sm:grid-cols-2 gap-3 mb-4">
                <div>
                    <Label>Eyebrow</Label>
                    <Input
                        value={form.founders_section_eyebrow || ""}
                        onChange={(e) => set("founders_section_eyebrow", e.target.value)}
                        placeholder="Founders"
                        className="rounded-xl mt-1.5"
                        data-testid="founders-eyebrow-input"
                    />
                </div>
                <div>
                    <Label>Section title (shown above the strip)</Label>
                    <Input
                        value={form.founders_section_title || ""}
                        onChange={(e) => set("founders_section_title", e.target.value)}
                        placeholder="Meet our Founders"
                        className="rounded-xl mt-1.5"
                        data-testid="founders-title-input"
                    />
                </div>
            </div>

            <div className="space-y-3" data-testid="founders-items-list">
                {items.length === 0 && (
                    <div className="text-sm text-center text-slate-500 py-8 border-2 border-dashed border-slate-300 rounded-xl">
                        No founders yet. Click "Add founder" to create the first one.
                    </div>
                )}
                {items.map((it, idx) => (
                    <div key={idx} className="bg-slate-50 border border-slate-200 rounded-2xl p-4" data-testid={`founder-item-${idx}`}>
                        <div className="flex items-start gap-3 mb-3">
                            <div className="text-xs uppercase tracking-wider font-bold text-slate-400 pt-2 w-12">#{idx + 1}</div>
                            <div className="flex-1 grid sm:grid-cols-2 gap-3">
                                <div>
                                    <Label className="text-xs">Display name</Label>
                                    <Input
                                        value={it.name || ""}
                                        onChange={(e) => setItem(idx, "name", e.target.value)}
                                        placeholder="Christian"
                                        className="rounded-xl mt-1"
                                        data-testid={`founder-name-input-${idx}`}
                                    />
                                </div>
                                <div>
                                    <Label className="text-xs">Role / title</Label>
                                    <Input
                                        value={it.role || ""}
                                        onChange={(e) => setItem(idx, "role", e.target.value)}
                                        placeholder="Founder"
                                        className="rounded-xl mt-1"
                                        data-testid={`founder-role-input-${idx}`}
                                    />
                                </div>
                            </div>
                            <div className="flex flex-col gap-1 pt-1">
                                <Button variant="ghost" size="icon" onClick={() => move(idx, -1)} disabled={idx === 0} data-testid={`founder-move-up-${idx}`}><ArrowUp className="h-4 w-4" /></Button>
                                <Button variant="ghost" size="icon" onClick={() => move(idx, 1)} disabled={idx === items.length - 1} data-testid={`founder-move-down-${idx}`}><ArrowDown className="h-4 w-4" /></Button>
                                <Button variant="ghost" size="icon" onClick={() => removeItem(idx)} data-testid={`founder-remove-${idx}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </div>
                        </div>

                        <div className="grid sm:grid-cols-[1fr_140px] gap-3 items-start">
                            <div>
                                <Label className="text-xs">Portrait</Label>
                                <div className="flex gap-2 mt-1">
                                    <label className="rounded-xl border-2 border-dashed border-slate-300 px-3 py-2 text-xs font-semibold cursor-pointer hover:bg-white hover:border-primary transition-colors flex items-center gap-1.5 flex-1 justify-center" data-testid={`founder-upload-${idx}`}>
                                        {uploadingIdx === idx ? "Uploading…" : (<><Upload className="h-3 w-3" />{it.image_url ? "Replace photo" : "Upload photo"}</>)}
                                        <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(idx, e.target.files?.[0])} />
                                    </label>
                                </div>
                            </div>
                            {it.image_url ? (
                                <div className="border border-slate-200 rounded-xl overflow-hidden bg-white aspect-square">
                                    <img src={it.image_url} alt="" className="block w-full h-full object-contain" onError={(e) => { e.currentTarget.style.opacity = "0.3"; }} />
                                </div>
                            ) : (
                                <div className="border border-dashed border-slate-300 rounded-xl bg-white aspect-square grid place-items-center text-[10px] text-slate-400 uppercase tracking-wider">No photo</div>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <Button variant="outline" size="sm" onClick={addItem} className="rounded-full mt-3" data-testid="founder-add-btn">
                <Plus className="h-3 w-3 mr-1" /> Add founder
            </Button>
        </div>
    );
}
