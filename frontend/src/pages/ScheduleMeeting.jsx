import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Calendar, Plus, Pencil, Trash2, Upload as UploadIcon, ExternalLink, ImageIcon } from "lucide-react";
import { toast } from "sonner";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function ScheduleMeeting() {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    const [cards, setCards] = useState([]);
    const [editor, setEditor] = useState(null); // null=closed, {} new, card edit

    async function load() {
        try {
            const { data } = await api.get("/meeting-cards");
            setCards(data || []);
        } catch { setCards([]); }
    }
    useEffect(() => { load(); }, []);

    return (
        <div className="bg-slate-50 min-h-screen">
            <section className="border-b-2 bg-white" style={{ borderColor: NAVY }}>
                <div className="max-w-5xl mx-auto px-6 lg:px-10 py-12 text-center">
                    <Calendar className="h-10 w-10 mx-auto mb-3" style={{ color: RED }} />
                    <div className="text-xs uppercase tracking-[0.3em] font-bold mb-2" style={{ color: RED }}>One-on-One</div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter" style={{ color: NAVY }}>Schedule a Meeting</h1>
                    <p className="mt-4 text-slate-600 max-w-2xl mx-auto">Connect directly with national leadership and chapter officers.</p>
                    {isAdmin && (
                        <Button onClick={() => setEditor({})} className="mt-6 rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="add-meeting-card-btn">
                            <Plus className="h-4 w-4 mr-1.5" /> Add card
                        </Button>
                    )}
                </div>
            </section>

            <section className="max-w-5xl mx-auto px-6 lg:px-10 py-12">
                {cards.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <p>{isAdmin ? "No meeting cards yet — click 'Add card' to invite leadership to publish their booking links." : "No meetings are scheduled to be bookable right now."}</p>
                    </div>
                ) : (
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="meeting-cards-grid">
                        {cards.map((c) => (
                            <MeetingCard key={c.id} card={c} isAdmin={isAdmin} onEdit={() => setEditor(c)} onChanged={load} />
                        ))}
                    </div>
                )}
            </section>

            <Dialog open={!!editor} onOpenChange={(o) => !o && setEditor(null)}>
                <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto">
                    {editor && <MeetingEditor card={editor.id ? editor : null} onSaved={() => { setEditor(null); load(); }} onClose={() => setEditor(null)} />}
                </DialogContent>
            </Dialog>
        </div>
    );
}

function MeetingCard({ card, isAdmin, onEdit, onChanged }) {
    const initials = (card.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
    async function remove() {
        if (!window.confirm(`Remove ${card.name} from the Schedule a Meeting page?`)) return;
        try { await api.delete(`/meeting-cards/${card.id}`); toast.success("Card removed"); onChanged?.(); }
        catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }
    function openBooking() {
        if (!card.button_url) return;
        const href = /^https?:\/\//i.test(card.button_url) ? card.button_url : `https://${card.button_url}`;
        window.open(href, "_blank", "noopener,noreferrer");
    }
    return (
        <div className="relative group bg-white rounded-2xl border border-border overflow-hidden shadow-warm hover:-translate-y-1 hover:shadow-warm-lg transition-all flex flex-col" data-testid={`meeting-card-${card.id}`}>
            <div className="aspect-[4/3] bg-gradient-to-br from-primary/15 to-primary/5 overflow-hidden flex items-center justify-center">
                {card.image_url ? (
                    <img src={mediaUrl(card.image_url)} alt={card.name} className="w-full h-full object-contain" />
                ) : (
                    <Avatar className="h-28 w-28">
                        <AvatarFallback className="text-white font-black text-4xl" style={{ backgroundColor: NAVY }}>{initials}</AvatarFallback>
                    </Avatar>
                )}
            </div>
            <div className="p-5 flex-1 flex flex-col">
                <h3 className="font-heading font-black text-xl leading-tight" style={{ color: NAVY }}>{card.name}</h3>
                {card.title && <div className="text-xs font-bold uppercase tracking-widest mt-1" style={{ color: RED }}>{card.title}</div>}
                {card.description && <p className="text-sm text-slate-600 mt-3 leading-relaxed flex-1">{card.description}</p>}
                <Button onClick={openBooking} className="mt-4 rounded-full bg-primary hover:bg-primary/90 shadow-warm w-full" disabled={!card.button_url} data-testid={`meeting-book-${card.id}`}>
                    <ExternalLink className="h-4 w-4 mr-1.5" /> {card.button_label || "Book Meeting"}
                </Button>
            </div>
            {isAdmin && (
                <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button size="sm" variant="outline" onClick={onEdit} className="h-7 w-7 p-0 bg-white shadow-warm" data-testid={`meeting-edit-${card.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button size="sm" variant="outline" onClick={remove} className="h-7 w-7 p-0 bg-white text-destructive shadow-warm" data-testid={`meeting-delete-${card.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
            )}
        </div>
    );
}

function MeetingEditor({ card, onSaved, onClose }) {
    const isEdit = !!card;
    const [form, setForm] = useState({
        name: "", title: "", description: "", image_url: "",
        button_label: "Book Meeting", button_url: "", order: 0,
    });
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (card) {
            setForm({
                name: card.name || "", title: card.title || "", description: card.description || "",
                image_url: card.image_url || "",
                button_label: card.button_label || "Book Meeting",
                button_url: card.button_url || "", order: card.order ?? 0,
            });
        }
    }, [card]);

    async function uploadImage(file) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { toast.error("Image must be under 10 MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const { data } = await api.post("/meeting-cards/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setForm((f) => ({ ...f, image_url: data.url }));
            toast.success("Photo uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }

    async function save() {
        if (!form.name.trim() || !form.button_url.trim()) { toast.error("Name and Book Meeting URL are required"); return; }
        setBusy(true);
        try {
            if (isEdit) await api.put(`/meeting-cards/${card.id}`, form);
            else await api.post("/meeting-cards", form);
            toast.success("Saved");
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    return (
        <div data-testid="meeting-editor">
            <DialogHeader><DialogTitle className="font-heading text-2xl">{isEdit ? `Edit ${form.name || "card"}` : "Add a meeting card"}</DialogTitle></DialogHeader>
            <div className="space-y-4 mt-3">
                <div>
                    <Label>Name *</Label>
                    <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" placeholder="e.g. Coley Burnett" data-testid="meeting-name-input" />
                </div>
                <div>
                    <Label>Title</Label>
                    <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-xl mt-1.5" placeholder="e.g. National President" data-testid="meeting-title-input" />
                </div>
                <div>
                    <Label>Description <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                    <Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-xl mt-1.5" placeholder="What the meeting is for, what to expect…" data-testid="meeting-description-input" />
                </div>
                <div>
                    <Label>Photo</Label>
                    <div className="flex items-center gap-2 mt-1.5">
                        <Input value={form.image_url} onChange={(e) => setForm({ ...form, image_url: e.target.value })} className="rounded-xl flex-1" placeholder="https://… or upload" data-testid="meeting-image-url-input" />
                        <label className="cursor-pointer">
                            <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                <span data-testid="meeting-upload-btn"><UploadIcon className="h-3.5 w-3.5 mr-1" />Upload</span>
                            </Button>
                            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0])} />
                        </label>
                    </div>
                    {form.image_url && (
                        <div className="mt-3 rounded-xl overflow-hidden border-2 border-border max-w-xs bg-slate-100">
                            <img src={mediaUrl(form.image_url)} alt="Preview" className="w-full h-48 object-contain" />
                        </div>
                    )}
                    {!form.image_url && (
                        <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1.5">
                            <ImageIcon className="h-3.5 w-3.5" /> No photo — the card will show the person's initials.
                        </p>
                    )}
                </div>
                <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                        <Label>Button label</Label>
                        <Input value={form.button_label} onChange={(e) => setForm({ ...form, button_label: e.target.value })} className="rounded-xl mt-1.5" placeholder="Book Meeting" data-testid="meeting-button-label-input" />
                    </div>
                    <div>
                        <Label>Sort order</Label>
                        <Input type="number" value={form.order} onChange={(e) => setForm({ ...form, order: parseInt(e.target.value || "0", 10) })} className="rounded-xl mt-1.5" data-testid="meeting-order-input" />
                    </div>
                </div>
                <div>
                    <Label>Book Meeting URL *</Label>
                    <Input value={form.button_url} onChange={(e) => setForm({ ...form, button_url: e.target.value })} className="rounded-xl mt-1.5" placeholder="https://calendly.com/your-handle/30min" data-testid="meeting-button-url-input" />
                    <p className="text-xs text-muted-foreground mt-1.5">Calendly, Google Calendar, Cal.com — anywhere this person accepts bookings.</p>
                </div>
            </div>
            <DialogFooter className="mt-6">
                <Button variant="outline" onClick={onClose} className="rounded-full" type="button">Cancel</Button>
                <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="meeting-save-btn">
                    {busy ? "Saving…" : (isEdit ? "Save changes" : "Add card")}
                </Button>
            </DialogFooter>
        </div>
    );
}
