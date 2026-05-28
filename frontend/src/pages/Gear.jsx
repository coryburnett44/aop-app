import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { ShoppingBag, Tag } from "lucide-react";
import PayPalCheckout from "../components/PayPalCheckout";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function Gear() {
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [active, setActive] = useState(null);
    const [qty, setQty] = useState(1);

    useEffect(() => { api.get("/gear").then(({ data }) => setItems(data)).catch(() => {}); }, []);
    useEffect(() => { if (active) setQty(1); }, [active]);

    const categories = Array.from(new Set(items.map((i) => i.category))).sort();
    const [cat, setCat] = useState("all");
    const filtered = cat === "all" ? items : items.filter((i) => i.category === cat);

    return (
        <div className="bg-slate-50 min-h-screen">
            <section className="bg-white border-b-2" style={{ borderColor: NAVY }}>
                <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>Wear the crest</div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter" style={{ color: NAVY }}>AOP Gear Store</h1>
                    <p className="text-slate-600 mt-3 max-w-2xl">Officer-grade apparel and collectibles. Every order supports the chapter.</p>
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
                        <p className="mt-3">Gear shelves are empty. Check back soon.</p>
                    </div>
                ) : (
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filtered.map((g) => (
                            <button
                                key={g.id}
                                onClick={() => setActive(g)}
                                className="text-left bg-white rounded-2xl overflow-hidden border-2 border-transparent hover:-translate-y-1 hover:shadow-warm-lg transition-all"
                                style={{ borderColor: "transparent" }}
                                onMouseEnter={(e) => { e.currentTarget.style.borderColor = RED; }}
                                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "transparent"; }}
                                data-testid={`gear-item-${g.id}`}
                            >
                                <div className="aspect-square bg-slate-100 overflow-hidden">
                                    {g.cover_image && <img src={g.cover_image} alt={g.name} className="w-full h-full object-cover" />}
                                </div>
                                <div className="p-5">
                                    <div className="flex items-start justify-between gap-3">
                                        <h3 className="font-heading font-bold text-lg leading-snug" style={{ color: NAVY }}>{g.name}</h3>
                                        <div className="font-heading font-black text-xl shrink-0" style={{ color: RED }}>${g.price.toFixed(0)}</div>
                                    </div>
                                    {g.sizes?.length > 0 && (
                                        <div className="mt-3 flex flex-wrap gap-1">
                                            {g.sizes.map((s) => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                                        </div>
                                    )}
                                    {!g.in_stock && <div className="mt-3 text-xs uppercase tracking-wider font-bold text-amber-700">Sold out</div>}
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </section>

            <Dialog open={!!active} onOpenChange={(o) => !o && setActive(null)}>
                <DialogContent className="max-w-2xl p-0 overflow-hidden max-h-[92vh] sm:max-h-[90vh] grid grid-rows-[auto_1fr] sm:grid-rows-none">
                    {active && (
                        <div className="grid sm:grid-cols-2 overflow-y-auto" data-testid={`gear-dialog-${active.id}`}>
                            <div className="aspect-square sm:aspect-auto bg-slate-100 sm:sticky sm:top-0 sm:h-full">
                                {active.cover_image && <img src={active.cover_image} alt={active.name} className="w-full h-full object-cover" />}
                            </div>
                            <div className="p-6 overflow-y-auto">
                                <DialogHeader><DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>{active.name}</DialogTitle></DialogHeader>
                                <div className="font-heading font-black text-3xl mt-2" style={{ color: RED }}>${active.price.toFixed(2)}</div>
                                {active.sku && <div className="text-xs text-slate-500 mt-1 inline-flex items-center gap-1"><Tag className="h-3 w-3" />SKU: {active.sku}</div>}
                                <p className="text-sm mt-4 leading-relaxed text-slate-700">{active.description}</p>
                                {active.sizes?.length > 0 && (
                                    <div className="mt-4">
                                        <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-2">Sizes</div>
                                        <div className="flex flex-wrap gap-1.5">{active.sizes.map((s) => <Badge key={s} variant="outline">{s}</Badge>)}</div>
                                    </div>
                                )}
                                {active.colors?.length > 0 && (
                                    <div className="mt-4">
                                        <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-2">Colors</div>
                                        <div className="flex flex-wrap gap-1.5">{active.colors.map((c) => <Badge key={c}>{c}</Badge>)}</div>
                                    </div>
                                )}
                                <div className="mt-6 flex items-center gap-3">
                                    <label className="text-sm font-semibold text-slate-700">Qty</label>
                                    <div className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1">
                                        <button onClick={() => setQty(Math.max(1, qty - 1))} className="text-lg font-bold w-6 hover:text-primary" data-testid={`gear-qty-dec-${active.id}`}>−</button>
                                        <span className="w-6 text-center font-semibold" data-testid={`gear-qty-${active.id}`}>{qty}</span>
                                        <button onClick={() => setQty(qty + 1)} className="text-lg font-bold w-6 hover:text-primary" data-testid={`gear-qty-inc-${active.id}`}>+</button>
                                    </div>
                                    <div className="ml-auto font-heading font-black text-xl" style={{ color: NAVY }}>${(active.price * qty).toFixed(2)}</div>
                                </div>
                                <div className="mt-4">
                                    {user ? (
                                        <PayPalCheckout
                                            purpose="gear"
                                            amount={active.price * qty}
                                            gear_id={active.id}
                                            quantity={qty}
                                            note={`${active.name}${qty > 1 ? ` ×${qty}` : ""}`}
                                            onComplete={() => setActive(null)}
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
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
