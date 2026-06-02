import { useEffect, useMemo, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import { ShoppingBag, Tag, Pencil, Plus, Trash2, Upload as UploadIcon, Image as ImageIcon, Palette, Ruler } from "lucide-react";
import PayPalCheckout from "../components/PayPalCheckout";
import { toast } from "sonner";

const NAVY = "#0A2463";
const RED = "#C8102E";
const STANDARD_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL"];

// Color name → swatch CSS. Falls back to the literal value if it's a hex/CSS color.
const COLOR_SWATCHES = {
    red: "#C8102E", navy: "#0A2463", black: "#000000", white: "#FFFFFF",
    grey: "#9CA3AF", gray: "#9CA3AF", silver: "#C0C0C0", gold: "#D4AF37",
    blue: "#3B82F6", "royal blue": "#1E40AF", green: "#16A34A", forest: "#15803D",
    olive: "#556B2F", yellow: "#EAB308", orange: "#F97316", pink: "#EC4899",
    purple: "#9333EA", maroon: "#7F1D1D", cream: "#FFF8E1", tan: "#D2B48C",
    burgundy: "#800020", charcoal: "#36454F",
};
function swatchFor(c) {
    if (!c) return "#94A3B8";
    const v = c.trim().toLowerCase();
    if (COLOR_SWATCHES[v]) return COLOR_SWATCHES[v];
    if (/^#?[0-9a-f]{3,8}$/i.test(c)) return c.startsWith("#") ? c : `#${c}`;
    return "#94A3B8";
}

export default function Gear() {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    const [items, setItems] = useState([]);
    const [page, setPage] = useState({ hero_image: "", title: "", subtitle: "", intro: "" });
    const [active, setActive] = useState(null);
    const [editorItem, setEditorItem] = useState(null); // null when closed, {} for new, item for edit
    const [pageEditorOpen, setPageEditorOpen] = useState(false);

    async function load() {
        try {
            const [{ data }, { data: p }] = await Promise.all([
                api.get("/gear"),
                api.get("/gear-page").catch(() => ({ data: { hero_image: "", title: "", subtitle: "", intro: "" } })),
            ]);
            setItems(data || []);
            setPage(p || { hero_image: "", title: "", subtitle: "", intro: "" });
        } catch { /* ignore */ }
    }
    useEffect(() => { load(); }, []);

    const categories = Array.from(new Set(items.map((i) => i.category))).sort();
    const [cat, setCat] = useState("all");
    const filtered = cat === "all" ? items : items.filter((i) => i.category === cat);

    return (
        <div className="bg-slate-50 min-h-screen">
            <section className="border-b-2 relative overflow-hidden" style={{ borderColor: NAVY, backgroundColor: page.hero_image ? "transparent" : "#FFFFFF" }}>
                {page.hero_image && (
                    <img src={mediaUrl(page.hero_image)} alt="Gear store banner" className="absolute inset-0 w-full h-full object-cover" />
                )}
                {page.hero_image && <div className="absolute inset-0 bg-gradient-to-r from-black/55 to-black/10" />}
                <div className={`max-w-6xl mx-auto px-6 lg:px-10 py-12 relative ${page.hero_image ? "text-white" : ""}`}>
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: page.hero_image ? "#FFE2C7" : RED }}>{page.subtitle || "Wear the crest"}</div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter" style={{ color: page.hero_image ? "#FFFFFF" : NAVY }}>{page.title || "AOP Gear Store"}</h1>
                    <p className={`mt-3 max-w-2xl ${page.hero_image ? "text-white/90" : "text-slate-600"} whitespace-pre-wrap`}>{page.intro || "Officer-grade apparel and collectibles. Every order supports the chapter."}</p>
                    {isAdmin && (
                        <div className="mt-6 flex flex-wrap gap-3">
                            <Button onClick={() => setPageEditorOpen(true)} variant="outline" className="rounded-full bg-white/90 hover:bg-white text-foreground" data-testid="gear-edit-page-btn">
                                <Pencil className="h-4 w-4 mr-1.5" /> Edit page banner
                            </Button>
                            <Button onClick={() => setEditorItem({})} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="gear-add-item-btn">
                                <Plus className="h-4 w-4 mr-1.5" /> Add item
                            </Button>
                        </div>
                    )}
                </div>
            </section>

            <section className="max-w-6xl mx-auto px-6 lg:px-10 py-10">
                {categories.length > 1 && (
                    <div className="flex flex-wrap gap-2 mb-8">
                        {["all", ...categories].map((c) => (
                            <button
                                key={c}
                                onClick={() => setCat(c)}
                                className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize ${cat === c ? "text-white shadow-warm" : "bg-white border border-slate-200 hover:border-slate-400"}`}
                                style={cat === c ? { backgroundColor: NAVY } : {}}
                                data-testid={`gear-cat-${c}`}
                            >
                                {c}
                            </button>
                        ))}
                    </div>
                )}
                {filtered.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <ShoppingBag className="h-12 w-12 mx-auto text-slate-300" />
                        <p className="mt-3">Gear shelves are empty. {isAdmin ? "Click 'Add item' to populate." : "Check back soon."}</p>
                    </div>
                ) : (
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filtered.map((g) => (
                            <GearCard key={g.id} item={g} isAdmin={isAdmin} onOpen={() => setActive(g)} onEdit={() => setEditorItem(g)} onChanged={load} />
                        ))}
                    </div>
                )}
            </section>

            <Dialog open={!!active} onOpenChange={(o) => !o && setActive(null)}>
                <DialogContent className="max-w-2xl p-0 overflow-hidden max-h-[92vh] sm:max-h-[90vh] flex flex-col">
                    {active && <GearCheckout item={active} user={user} onClose={() => setActive(null)} />}
                </DialogContent>
            </Dialog>

            <Dialog open={!!editorItem} onOpenChange={(o) => !o && setEditorItem(null)}>
                <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
                    {editorItem && (
                        <GearEditor
                            item={editorItem.id ? editorItem : null}
                            onSaved={() => { setEditorItem(null); load(); }}
                            onClose={() => setEditorItem(null)}
                        />
                    )}
                </DialogContent>
            </Dialog>

            <Dialog open={pageEditorOpen} onOpenChange={setPageEditorOpen}>
                <DialogContent className="max-w-xl">
                    <GearPageEditor page={page} onSaved={() => { setPageEditorOpen(false); load(); }} onClose={() => setPageEditorOpen(false)} />
                </DialogContent>
            </Dialog>
        </div>
    );
}

// ---------- Card on the grid ----------
function GearCard({ item, isAdmin, onOpen, onEdit, onChanged }) {
    async function remove(e) {
        e.stopPropagation();
        if (!window.confirm(`Delete "${item.name}" from the store?`)) return;
        try {
            await api.delete(`/gear/${item.id}`);
            toast.success("Item removed");
            onChanged?.();
        } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    }
    return (
        <div className="relative group">
            <button
                onClick={onOpen}
                className="text-left bg-white rounded-2xl overflow-hidden border-2 border-transparent hover:-translate-y-1 hover:shadow-warm-lg transition-all w-full"
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = RED; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "transparent"; }}
                data-testid={`gear-item-${item.id}`}
            >
                <div className="aspect-square bg-slate-100 overflow-hidden">
                    {item.cover_image && <img src={mediaUrl(item.cover_image)} alt={item.name} className="w-full h-full object-cover" />}
                </div>
                <div className="p-5">
                    <div className="flex items-start justify-between gap-3">
                        <h3 className="font-heading font-bold text-lg leading-snug" style={{ color: NAVY }}>{item.name}</h3>
                        <div className="font-heading font-black text-xl shrink-0" style={{ color: RED }}>${item.price.toFixed(0)}</div>
                    </div>
                    {item.sizes?.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1">
                            {item.sizes.map((s) => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                        </div>
                    )}
                    {item.colors?.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                            {item.colors.slice(0, 6).map((c) => (
                                <span key={c} className="h-4 w-4 rounded-full border border-slate-300" style={{ backgroundColor: swatchFor(c) }} title={c} />
                            ))}
                            {item.colors.length > 6 && <span className="text-[10px] text-slate-500">+{item.colors.length - 6}</span>}
                        </div>
                    )}
                    {!item.in_stock && <div className="mt-3 text-xs uppercase tracking-wider font-bold text-amber-700">Sold out</div>}
                </div>
            </button>
            {isAdmin && (
                <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); onEdit(); }} className="h-7 w-7 p-0 bg-white shadow-warm" data-testid={`gear-edit-${item.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button size="sm" variant="outline" onClick={remove} className="h-7 w-7 p-0 bg-white text-destructive shadow-warm" data-testid={`gear-delete-${item.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
            )}
        </div>
    );
}

// ---------- Member checkout dialog (color / size / qty + PayPal) ----------
function GearCheckout({ item, user, onClose }) {
    const [color, setColor] = useState(item.colors?.[0] || "");
    const [size, setSize] = useState(item.sizes?.[0] || "");
    const [qty, setQty] = useState(1);

    // The picture displayed swaps to the per-color image when a color is selected.
    const activeImage = useMemo(() => {
        if (color) {
            const tagged = (item.color_images || []).find((ci) => ci.color === color);
            if (tagged?.image_url) return tagged.image_url;
        }
        return item.cover_image || item.images?.[0] || "";
    }, [color, item]);

    const canCheckout = (!item.colors?.length || color) && (!item.sizes?.length || size);

    return (
        <div className="flex flex-col sm:grid sm:grid-cols-2 overflow-y-auto flex-1 min-h-0" data-testid={`gear-dialog-${item.id}`}>
            <div className="w-full h-52 sm:h-auto sm:aspect-auto sm:sticky sm:top-0 sm:max-h-full bg-slate-100 overflow-hidden shrink-0">
                {activeImage && <img src={mediaUrl(activeImage)} alt={item.name} className="w-full h-full object-cover" />}
            </div>
            <div className="p-5 sm:p-6 overflow-y-auto">
                <DialogHeader><DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>{item.name}</DialogTitle></DialogHeader>
                <div className="font-heading font-black text-3xl mt-2" style={{ color: RED }}>${item.price.toFixed(2)}</div>
                {item.sku && <div className="text-xs text-slate-500 mt-1 inline-flex items-center gap-1"><Tag className="h-3 w-3" />SKU: {item.sku}</div>}
                <p className="text-sm mt-4 leading-relaxed text-slate-700 whitespace-pre-wrap">{item.description}</p>

                {item.colors?.length > 0 && (
                    <div className="mt-5" data-testid="gear-colors-section">
                        <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-2 inline-flex items-center gap-1"><Palette className="h-3 w-3" />Color</div>
                        <div className="flex flex-wrap gap-2">
                            {item.colors.map((c) => (
                                <button
                                    key={c}
                                    onClick={() => setColor(c)}
                                    className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-sm border-2 transition-colors ${c === color ? "border-primary bg-primary/10 font-semibold" : "border-slate-200 hover:border-slate-400"}`}
                                    data-testid={`gear-color-${c}`}
                                >
                                    <span className="h-4 w-4 rounded-full border border-slate-300" style={{ backgroundColor: swatchFor(c) }} />
                                    <span className="capitalize">{c}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}
                {item.sizes?.length > 0 && (
                    <div className="mt-5" data-testid="gear-sizes-section">
                        <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-2 inline-flex items-center gap-1"><Ruler className="h-3 w-3" />Size</div>
                        <div className="flex flex-wrap gap-2">
                            {item.sizes.map((s) => (
                                <button
                                    key={s}
                                    onClick={() => setSize(s)}
                                    className={`min-w-[3rem] rounded-full px-3 py-1.5 text-sm border-2 transition-colors ${s === size ? "border-primary bg-primary/10 font-semibold" : "border-slate-200 hover:border-slate-400"}`}
                                    data-testid={`gear-size-${s}`}
                                >
                                    {s}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                <div className="mt-6 flex items-center gap-3">
                    <label className="text-sm font-semibold text-slate-700">Qty</label>
                    <div className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1">
                        <button onClick={() => setQty(Math.max(1, qty - 1))} className="text-lg font-bold w-6 hover:text-primary" data-testid={`gear-qty-dec-${item.id}`}>−</button>
                        <span className="w-6 text-center font-semibold" data-testid={`gear-qty-${item.id}`}>{qty}</span>
                        <button onClick={() => setQty(qty + 1)} className="text-lg font-bold w-6 hover:text-primary" data-testid={`gear-qty-inc-${item.id}`}>+</button>
                    </div>
                    <div className="ml-auto font-heading font-black text-xl" style={{ color: NAVY }}>${(item.price * qty).toFixed(2)}</div>
                </div>

                {!canCheckout && (
                    <div className="mt-3 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
                        Select {item.colors?.length > 0 && !color ? "a color" : ""}{item.colors?.length > 0 && !color && item.sizes?.length > 0 && !size ? " and " : ""}{item.sizes?.length > 0 && !size ? "a size" : ""} to continue.
                    </div>
                )}

                <div className="mt-4">
                    {user ? (
                        <PayPalCheckout
                            purpose="gear"
                            amount={item.price * qty}
                            gear_id={item.id}
                            quantity={qty}
                            gear_color={color}
                            gear_size={size}
                            disabled={!canCheckout || !item.in_stock}
                            note={`${item.name}${color ? ` · ${color}` : ""}${size ? ` · ${size}` : ""}${qty > 1 ? ` ×${qty}` : ""}`}
                            onComplete={onClose}
                        />
                    ) : (
                        <Button asChild className="w-full rounded-full text-white shadow-warm" style={{ backgroundColor: RED }}>
                            <a href="/login">Log in to checkout</a>
                        </Button>
                    )}
                </div>
                <p className="text-xs text-slate-500 text-center mt-2">Secure checkout via PayPal. Shipping arranged separately by your chapter.</p>
            </div>
        </div>
    );
}

// ---------- Admin: item editor (create or update) ----------
function GearEditor({ item, onSaved, onClose }) {
    const isEdit = !!item;
    const [form, setForm] = useState({
        name: "", description: "", price: 0, sku: "", category: "apparel", in_stock: true,
        sizes: [], colors: [], cover_image: "", images: [], color_images: [],
    });
    const [busy, setBusy] = useState(false);
    const [colorInput, setColorInput] = useState("");
    const [customSizeInput, setCustomSizeInput] = useState("");

    useEffect(() => {
        if (item) {
            setForm({
                name: item.name || "", description: item.description || "",
                price: item.price || 0, sku: item.sku || "",
                category: item.category || "apparel", in_stock: item.in_stock !== false,
                sizes: item.sizes || [], colors: item.colors || [],
                cover_image: item.cover_image || "", images: item.images || [],
                color_images: (item.color_images || []).map((ci) => ({ ...ci })),
            });
        } else {
            setForm({ name: "", description: "", price: 0, sku: "", category: "apparel", in_stock: true, sizes: [], colors: [], cover_image: "", images: [], color_images: [] });
        }
    }, [item]);

    function toggleStandardSize(s) {
        setForm((f) => f.sizes.includes(s) ? { ...f, sizes: f.sizes.filter((x) => x !== s) } : { ...f, sizes: [...f.sizes, s] });
    }
    function addCustomSize() {
        const v = customSizeInput.trim();
        if (!v) return;
        if (form.sizes.includes(v)) { toast.error("Already added"); return; }
        setForm((f) => ({ ...f, sizes: [...f.sizes, v] }));
        setCustomSizeInput("");
    }
    function removeSize(s) {
        setForm((f) => ({ ...f, sizes: f.sizes.filter((x) => x !== s) }));
    }
    function addColor() {
        const v = colorInput.trim();
        if (!v) return;
        if (form.colors.includes(v)) { toast.error("Already added"); return; }
        setForm((f) => ({
            ...f,
            colors: [...f.colors, v],
            color_images: [...f.color_images, { color: v, image_url: "" }],
        }));
        setColorInput("");
    }
    function removeColor(c) {
        setForm((f) => ({
            ...f,
            colors: f.colors.filter((x) => x !== c),
            color_images: f.color_images.filter((ci) => ci.color !== c),
        }));
    }
    function setColorImage(color, image_url) {
        setForm((f) => {
            const existing = f.color_images.find((ci) => ci.color === color);
            return existing
                ? { ...f, color_images: f.color_images.map((ci) => ci.color === color ? { ...ci, image_url } : ci) }
                : { ...f, color_images: [...f.color_images, { color, image_url }] };
        });
    }

    async function uploadGearImage(file, onUrl) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { toast.error("Image must be under 10 MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const { data } = await api.post("/gear/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            onUrl(data.url);
            toast.success("Image uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }

    async function save() {
        if (!form.name.trim()) { toast.error("Item name is required"); return; }
        if (!form.price || form.price <= 0) { toast.error("Price must be greater than zero"); return; }
        setBusy(true);
        try {
            // Filter out color_images for colors that no longer exist
            const validColorImages = form.color_images.filter((ci) => form.colors.includes(ci.color));
            const payload = { ...form, price: Number(form.price), color_images: validColorImages };
            if (isEdit) {
                await api.put(`/gear/${item.id}`, payload);
                toast.success("Item updated");
            } else {
                await api.post("/gear", payload);
                toast.success("Item added");
            }
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    return (
        <div data-testid="gear-editor">
            <DialogHeader><DialogTitle className="font-heading text-2xl">{isEdit ? `Edit ${form.name || "item"}` : "Add gear item"}</DialogTitle></DialogHeader>
            <div className="space-y-5 mt-3">
                <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                        <Label>Name *</Label>
                        <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" placeholder="Crest Polo" data-testid="gear-editor-name" />
                    </div>
                    <div>
                        <Label>Price (USD) *</Label>
                        <Input type="number" step="0.01" min="0" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="rounded-xl mt-1.5" data-testid="gear-editor-price" />
                    </div>
                </div>
                <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                        <Label>Category</Label>
                        <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="rounded-xl mt-1.5" placeholder="apparel, accessories, drinkware…" data-testid="gear-editor-category" />
                    </div>
                    <div>
                        <Label>SKU <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                        <Input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} className="rounded-xl mt-1.5" data-testid="gear-editor-sku" />
                    </div>
                </div>

                <div>
                    <Label>Description</Label>
                    <Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" data-testid="gear-editor-description" />
                </div>

                {/* Cover image */}
                <div>
                    <Label>Cover photo <span className="text-xs text-muted-foreground font-normal">(shown on the grid)</span></Label>
                    <div className="flex items-center gap-2 mt-1.5">
                        <Input value={form.cover_image} onChange={(e) => setForm({ ...form, cover_image: e.target.value })} className="rounded-xl flex-1" placeholder="https://… or upload" data-testid="gear-editor-cover-url" />
                        <label className="cursor-pointer">
                            <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                <span><UploadIcon className="h-3.5 w-3.5 mr-1" />Upload</span>
                            </Button>
                            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadGearImage(e.target.files?.[0], (url) => setForm({ ...form, cover_image: url }))} />
                        </label>
                    </div>
                    {form.cover_image && (
                        <div className="mt-2 rounded-xl overflow-hidden border border-border max-w-xs">
                            <img src={mediaUrl(form.cover_image)} alt="Cover preview" className="w-full h-40 object-cover" />
                        </div>
                    )}
                </div>

                {/* Sizes — toggle standard + free-form */}
                <div>
                    <Label className="flex items-center gap-1.5"><Ruler className="h-4 w-4" />Sizes <span className="text-xs text-muted-foreground font-normal">(toggle standard or type your own)</span></Label>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                        {STANDARD_SIZES.map((s) => (
                            <button
                                key={s}
                                onClick={() => toggleStandardSize(s)}
                                className={`min-w-[2.75rem] rounded-full px-3 py-1.5 text-sm border-2 transition-colors ${form.sizes.includes(s) ? "border-primary bg-primary/15 font-semibold" : "border-slate-200 hover:border-slate-400"}`}
                                type="button"
                                data-testid={`gear-editor-size-toggle-${s}`}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                    {form.sizes.some((s) => !STANDARD_SIZES.includes(s)) && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                            {form.sizes.filter((s) => !STANDARD_SIZES.includes(s)).map((s) => (
                                <Badge key={s} variant="outline" className="rounded-full px-2.5 py-1 gap-1.5">
                                    {s}
                                    <button onClick={() => removeSize(s)} className="text-destructive ml-1 hover:underline" data-testid={`gear-editor-remove-size-${s}`}>×</button>
                                </Badge>
                            ))}
                        </div>
                    )}
                    <div className="mt-3 flex gap-2">
                        <Input
                            value={customSizeInput}
                            onChange={(e) => setCustomSizeInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustomSize(); } }}
                            placeholder='Custom size (e.g. "12oz", "Onesize", "32x34")'
                            className="rounded-xl flex-1"
                            data-testid="gear-editor-custom-size-input"
                        />
                        <Button type="button" variant="outline" onClick={addCustomSize} className="rounded-full" data-testid="gear-editor-add-custom-size">Add</Button>
                    </div>
                </div>

                {/* Colors — free-form add + per-color image */}
                <div>
                    <Label className="flex items-center gap-1.5"><Palette className="h-4 w-4" />Colors <span className="text-xs text-muted-foreground font-normal">(each color can have its own photo)</span></Label>
                    <div className="mt-2 flex gap-2">
                        <Input
                            value={colorInput}
                            onChange={(e) => setColorInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addColor(); } }}
                            placeholder='Add color (e.g. "red", "navy", "#FF6B00")'
                            className="rounded-xl flex-1"
                            data-testid="gear-editor-color-input"
                        />
                        <Button type="button" variant="outline" onClick={addColor} className="rounded-full" data-testid="gear-editor-add-color"><Plus className="h-3.5 w-3.5 mr-1" />Add color</Button>
                    </div>
                    {form.colors.length > 0 && (
                        <div className="mt-4 space-y-3" data-testid="gear-editor-color-rows">
                            {form.colors.map((c) => {
                                const img = form.color_images.find((ci) => ci.color === c)?.image_url || "";
                                return (
                                    <div key={c} className="rounded-2xl border border-border p-3 flex gap-3 items-start">
                                        <div className="flex items-center gap-2 min-w-[8rem]">
                                            <span className="h-6 w-6 rounded-full border border-slate-300 shrink-0" style={{ backgroundColor: swatchFor(c) }} />
                                            <span className="font-semibold capitalize text-sm">{c}</span>
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <Input
                                                    value={img}
                                                    onChange={(e) => setColorImage(c, e.target.value)}
                                                    placeholder="Photo URL or upload"
                                                    className="rounded-xl text-xs"
                                                    data-testid={`gear-editor-color-image-${c}`}
                                                />
                                                <label className="cursor-pointer">
                                                    <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                                        <span><UploadIcon className="h-3.5 w-3.5 mr-1" />Upload</span>
                                                    </Button>
                                                    <input
                                                        type="file"
                                                        accept="image/*"
                                                        className="hidden"
                                                        onChange={(e) => uploadGearImage(e.target.files?.[0], (url) => setColorImage(c, url))}
                                                    />
                                                </label>
                                            </div>
                                            {img && <img src={mediaUrl(img)} alt={c} className="mt-2 w-24 h-24 rounded-xl object-cover border border-border" />}
                                            {!img && <p className="text-xs text-muted-foreground mt-1.5 inline-flex items-center gap-1"><ImageIcon className="h-3 w-3" /> No photo — checkout will fall back to the cover photo for this color.</p>}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => removeColor(c)}
                                            className="text-destructive text-xs hover:underline shrink-0"
                                            data-testid={`gear-editor-remove-color-${c}`}
                                        >
                                            Remove
                                        </button>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    <Switch checked={form.in_stock} onCheckedChange={(v) => setForm({ ...form, in_stock: v })} data-testid="gear-editor-in-stock" />
                    <Label>{form.in_stock ? "In stock — checkout enabled" : "Sold out / hidden from checkout"}</Label>
                </div>
            </div>
            <DialogFooter className="mt-6">
                <Button variant="outline" onClick={onClose} className="rounded-full" type="button">Cancel</Button>
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="gear-editor-save">
                    {busy ? "Saving…" : (isEdit ? "Save changes" : "Add item")}
                </Button>
            </DialogFooter>
        </div>
    );
}

// ---------- Admin: page banner editor ----------
function GearPageEditor({ page, onSaved, onClose }) {
    const [form, setForm] = useState({ hero_image: page.hero_image || "", title: page.title || "", subtitle: page.subtitle || "", intro: page.intro || "" });
    const [busy, setBusy] = useState(false);

    async function uploadImage(file) {
        if (!file) return;
        if (file.size > 15 * 1024 * 1024) { toast.error("Image must be under 15 MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const { data } = await api.post("/gear/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setForm((f) => ({ ...f, hero_image: data.url }));
            toast.success("Banner uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }

    async function save() {
        setBusy(true);
        try {
            await api.put("/gear-page", form);
            toast.success("Gear page updated");
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    return (
        <div data-testid="gear-page-editor">
            <DialogHeader><DialogTitle className="font-heading text-2xl">Edit Gear page</DialogTitle></DialogHeader>
            <div className="space-y-4 mt-3">
                {form.hero_image && (
                    <div className="rounded-xl overflow-hidden border border-border">
                        <img src={mediaUrl(form.hero_image)} alt="Banner preview" className="w-full max-h-56 object-cover" />
                    </div>
                )}
                <div>
                    <Label>Banner image</Label>
                    <div className="flex items-center gap-2 mt-1.5">
                        <Input value={form.hero_image} onChange={(e) => setForm({ ...form, hero_image: e.target.value })} className="rounded-xl flex-1" placeholder="https://… or upload below" data-testid="gear-page-hero-url" />
                        <label className="cursor-pointer">
                            <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                <span><UploadIcon className="h-3.5 w-3.5 mr-1" />Upload</span>
                            </Button>
                            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0])} />
                        </label>
                    </div>
                </div>
                <div>
                    <Label>Headline</Label>
                    <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" placeholder="AOP Gear Store" data-testid="gear-page-title" />
                </div>
                <div>
                    <Label>Sub-headline</Label>
                    <Input value={form.subtitle} onChange={(e) => setForm({ ...form, subtitle: e.target.value })} className="rounded-xl mt-1.5" placeholder="Wear the crest" data-testid="gear-page-subtitle" />
                </div>
                <div>
                    <Label>Intro paragraph</Label>
                    <Textarea rows={3} value={form.intro} onChange={(e) => setForm({ ...form, intro: e.target.value })} className="rounded-xl mt-1.5" placeholder="Officer-grade apparel and collectibles. Every order supports the chapter." data-testid="gear-page-intro" />
                </div>
            </div>
            <DialogFooter className="mt-6">
                <Button variant="outline" onClick={onClose} className="rounded-full" type="button">Cancel</Button>
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="gear-page-save">
                    {busy ? "Saving…" : "Save page"}
                </Button>
            </DialogFooter>
        </div>
    );
}
