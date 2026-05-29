import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "../components/ui/dialog";
import { FileText, Upload, Download, Trash2, ExternalLink, Pencil, Plus, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

function humanSize(n) {
    if (!n) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function Documents() {
    const { user } = useAuth();
    const [docs, setDocs] = useState([]);
    const [filter, setFilter] = useState("all");
    const [links, setLinks] = useState([]);
    const isAdmin = user?.role === "admin";

    const load = async () => {
        const url = "/documents" + (filter !== "all" ? `?category=${encodeURIComponent(filter)}` : "");
        const { data } = await api.get(url);
        setDocs(data);
    };
    const loadLinks = async () => {
        try {
            const { data } = await api.get("/form-links");
            setLinks(data || []);
        } catch { setLinks([]); }
    };

    useEffect(() => { load().catch(() => {}); }, [filter]);
    useEffect(() => { loadLinks(); }, []);

    async function remove(id) {
        if (!confirm("Delete this document?")) return;
        await api.delete(`/documents/${id}`);
        toast.success("Deleted");
        load();
    }

    const categories = Array.from(new Set(docs.map((d) => d.category))).sort();

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">AOP Forms</h1>
                    <p className="text-muted-foreground mt-2">Bylaws, minutes, forms, and chapter resources — all in one place.</p>
                </div>
                {user && <UploadDocDialog onDone={load} />}
            </div>

            {/* Picture link cards — admin manages, members click through to external pages */}
            {(links.length > 0 || isAdmin) && (
                <section className="mb-10" data-testid="form-links-section">
                    <div className="flex items-end justify-between mb-4 gap-3 flex-wrap">
                        <div>
                            <h2 className="font-heading text-2xl font-bold">Quick links</h2>
                            <p className="text-xs text-muted-foreground mt-1">Pinned resources and external pages chapter admins want members to see.</p>
                        </div>
                        {isAdmin && <LinkEditor onSaved={loadLinks} trigger={(
                            <Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="add-form-link-btn">
                                <Plus className="h-4 w-4 mr-1.5" /> Add link
                            </Button>
                        )} />}
                    </div>
                    {links.length === 0 ? (
                        <div className="bg-muted/30 border-2 border-dashed border-border rounded-2xl p-10 text-center text-sm text-muted-foreground" data-testid="form-links-empty">
                            No quick links yet. Add a picture-card link to point members at an external resource.
                        </div>
                    ) : (
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="form-links-grid">
                            {links.map((l) => (
                                <LinkCard key={l.id} link={l} isAdmin={isAdmin} onChanged={loadLinks} />
                            ))}
                        </div>
                    )}
                </section>
            )}

            {categories.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-6">
                    <button
                        onClick={() => setFilter("all")}
                        className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize ${filter === "all" ? "bg-primary text-primary-foreground shadow-warm" : "bg-muted hover:bg-muted/70"}`}
                        data-testid="docs-filter-all"
                    >
                        All
                    </button>
                    {categories.map((c) => (
                        <button
                            key={c}
                            onClick={() => setFilter(c)}
                            className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize ${filter === c ? "bg-primary text-primary-foreground shadow-warm" : "bg-muted hover:bg-muted/70"}`}
                            data-testid={`docs-filter-${c}`}
                        >
                            {c}
                        </button>
                    ))}
                </div>
            )}

            {docs.length === 0 ? (
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-3xl p-16 text-center">
                    <FileText className="h-12 w-12 mx-auto text-muted-foreground/50" />
                    <p className="mt-4 font-heading text-xl">No AOP forms yet</p>
                    <p className="text-sm text-muted-foreground">Upload the bylaws, meeting notes, and chapter resources.</p>
                </div>
            ) : (
                <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-warm">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-5 py-3">Title</th>
                                <th className="text-left px-5 py-3">Category</th>
                                <th className="text-left px-5 py-3 hidden sm:table-cell">Uploaded by</th>
                                <th className="text-left px-5 py-3 hidden md:table-cell">Size</th>
                                <th className="text-right px-5 py-3"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {docs.map((d) => (
                                <tr key={d.id} className="border-t border-border hover:bg-muted/30" data-testid={`doc-row-${d.id}`}>
                                    <td className="px-5 py-3">
                                        <div className="font-medium">{d.title}</div>
                                        {d.description && <div className="text-xs text-muted-foreground mt-0.5">{d.description}</div>}
                                        <div className="text-xs text-muted-foreground mt-0.5">
                                            {d.created_at && format(parseISO(d.created_at), "MMM d, yyyy")}
                                        </div>
                                    </td>
                                    <td className="px-5 py-3">
                                        <span className="text-xs bg-accent/30 rounded-full px-2.5 py-0.5 font-medium capitalize">{d.category}</span>
                                    </td>
                                    <td className="px-5 py-3 hidden sm:table-cell text-muted-foreground">{d.uploaded_by_name}</td>
                                    <td className="px-5 py-3 hidden md:table-cell text-muted-foreground">{humanSize(d.size)}</td>
                                    <td className="px-5 py-3 text-right">
                                        <DocDownloadLink doc={d} />
                                        {user && (user.role === "admin" || user.id === d.uploaded_by) && (
                                            <button onClick={() => remove(d.id)} className="ml-3 text-muted-foreground hover:text-destructive" data-testid={`delete-doc-${d.id}`}>
                                                <Trash2 className="h-4 w-4" />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function DocDownloadLink({ doc }) {
    const [busy, setBusy] = useState(false);
    async function open() {
        setBusy(true);
        try {
            const path = doc.url.startsWith("/api") ? doc.url.slice(4) : doc.url;
            const { data } = await api.get(path, { responseType: "blob" });
            const url = URL.createObjectURL(data);
            const a = document.createElement("a");
            a.href = url;
            a.download = doc.original_filename || doc.title || "download";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch {
            toast.error("Failed to download");
        }
        setBusy(false);
    }
    return (
        <button
            onClick={open}
            disabled={busy}
            className="inline-flex items-center gap-1.5 text-primary hover:underline text-sm"
            data-testid={`download-doc-${doc.id}`}
        >
            <Download className="h-4 w-4" /> {busy ? "Loading…" : "Open"}
        </button>
    );
}

function UploadDocDialog({ onDone }) {
    const [open, setOpen] = useState(false);
    const [file, setFile] = useState(null);
    const [title, setTitle] = useState("");
    const [category, setCategory] = useState("general");
    const [description, setDescription] = useState("");
    const [busy, setBusy] = useState(false);
    const inputRef = useRef(null);

    async function upload() {
        if (!file) return;
        setBusy(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("title", title || file.name);
            fd.append("category", category);
            fd.append("description", description);
            await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Document uploaded");
            setOpen(false);
            setFile(null);
            setTitle("");
            setCategory("general");
            setDescription("");
            onDone();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Upload failed");
        }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="upload-doc-btn">
                    <Upload className="h-4 w-4 mr-1.5" /> Upload form
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Upload AOP form</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div
                        onClick={() => inputRef.current?.click()}
                        className="border-2 border-dashed border-border rounded-2xl p-8 text-center cursor-pointer hover:bg-muted/50 transition-colors"
                        data-testid="doc-dropzone"
                    >
                        <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                        <div className="mt-3 text-sm">{file ? <span className="font-medium">{file.name}</span> : "Click to choose a file (PDF, DOC, XLSX, TXT, CSV)"}</div>
                        <input
                            ref={inputRef}
                            type="file"
                            accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.pptx"
                            hidden
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            data-testid="doc-file-input"
                        />
                    </div>
                    <div>
                        <Label>Title</Label>
                        <Input value={title} onChange={(e) => setTitle(e.target.value)} className="rounded-xl mt-1.5" data-testid="doc-title-input" />
                    </div>
                    <div>
                        <Label>Category</Label>
                        <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. bylaws, minutes, forms" className="rounded-xl mt-1.5" data-testid="doc-category-input" />
                    </div>
                    <div>
                        <Label>Description (optional)</Label>
                        <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} className="rounded-xl mt-1.5" />
                    </div>
                    <Button onClick={upload} disabled={!file || busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="doc-upload-submit">
                        {busy ? "Uploading…" : "Upload"}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}


// ---------- Picture-card link to an external webpage (AOP Forms quick links) ----------
function LinkCard({ link, isAdmin, onChanged }) {
    const initials = (link.title || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

    async function openUrl(e) {
        e.preventDefault();
        if (!link.url) return;
        // Open in a new tab; normalize protocol if missing.
        const href = /^https?:\/\//i.test(link.url) ? link.url : `https://${link.url}`;
        window.open(href, "_blank", "noopener,noreferrer");
    }

    async function remove() {
        if (!window.confirm(`Delete "${link.title}"?`)) return;
        try {
            await api.delete(`/form-links/${link.id}`);
            toast.success("Link removed");
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    return (
        <div className="group relative rounded-2xl border border-border bg-card overflow-hidden shadow-warm hover:shadow-lg transition-all flex flex-col" data-testid={`form-link-card-${link.id}`}>
            <button onClick={openUrl} className="block text-left" data-testid={`form-link-open-${link.id}`}>
                <div className="aspect-[16/10] w-full overflow-hidden bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center">
                    {link.image_url ? (
                        <img src={link.image_url} alt={link.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                    ) : (
                        <span className="font-heading text-5xl font-black text-primary/40">{initials}</span>
                    )}
                </div>
                <div className="p-4">
                    <div className="flex items-start gap-2">
                        <h3 className="font-heading text-lg font-bold leading-tight flex-1">{link.title}</h3>
                        <ExternalLink className="h-4 w-4 text-muted-foreground shrink-0 mt-1 group-hover:text-primary transition-colors" />
                    </div>
                    {link.description && <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed line-clamp-3">{link.description}</p>}
                </div>
            </button>
            {isAdmin && (
                <div className="px-4 py-2 border-t border-border flex justify-end gap-3 bg-muted/20">
                    <LinkEditor existing={link} onSaved={onChanged} trigger={(
                        <button className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1" data-testid={`edit-form-link-${link.id}`}>
                            <Pencil className="h-3 w-3" /> Edit
                        </button>
                    )} />
                    <button onClick={remove} className="text-xs text-destructive hover:underline inline-flex items-center gap-1" data-testid={`delete-form-link-${link.id}`}>
                        <Trash2 className="h-3 w-3" /> Delete
                    </button>
                </div>
            )}
        </div>
    );
}

function LinkEditor({ trigger, existing, onSaved }) {
    const isEdit = !!existing;
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ title: "", description: "", url: "", image_url: "", order: 0 });
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (open) {
            setForm({
                title: existing?.title || "",
                description: existing?.description || "",
                url: existing?.url || "",
                image_url: existing?.image_url || "",
                order: existing?.order ?? 0,
            });
        }
    }, [open, existing]);

    async function uploadImage(file) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { toast.error("Image must be under 10 MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const { data } = await api.post("/form-links/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setForm((f) => ({ ...f, image_url: data.url }));
            toast.success("Picture uploaded");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    }

    async function save() {
        if (!form.title.trim() || !form.url.trim()) { toast.error("Title and URL are required"); return; }
        setBusy(true);
        try {
            if (isEdit) {
                await api.put(`/form-links/${existing.id}`, form);
                toast.success("Link updated");
            } else {
                await api.post("/form-links", form);
                toast.success("Link added");
            }
            setOpen(false);
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
        setBusy(false);
    }

    return (
        <>
            <span onClick={() => setOpen(true)}>{trigger}</span>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-lg" data-testid="form-link-editor">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">{isEdit ? "Edit quick link" : "Add a quick link"}</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 mt-2">
                        <div>
                            <Label>Title *</Label>
                            <Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} className="rounded-xl mt-1.5" placeholder="e.g. National AOP Bylaws" data-testid="form-link-title-input" />
                        </div>
                        <div>
                            <Label>Link URL *</Label>
                            <Input value={form.url} onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))} className="rounded-xl mt-1.5" placeholder="https://…" data-testid="form-link-url-input" />
                        </div>
                        <div>
                            <Label>Description <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                            <Textarea rows={2} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} className="rounded-xl mt-1.5" placeholder="What members will find when they click." data-testid="form-link-description-input" />
                        </div>
                        <div>
                            <Label>Picture <span className="text-xs text-muted-foreground font-normal">(shown on the card)</span></Label>
                            <div className="flex items-center gap-2 mt-1.5">
                                <Input value={form.image_url} onChange={(e) => setForm((f) => ({ ...f, image_url: e.target.value }))} className="rounded-xl flex-1" placeholder="https://… or upload below" data-testid="form-link-image-url-input" />
                                <label className="cursor-pointer">
                                    <Button asChild variant="outline" size="sm" className="rounded-full" type="button">
                                        <span data-testid="form-link-upload-btn"><Upload className="h-3.5 w-3.5 mr-1" />Upload</span>
                                    </Button>
                                    <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0])} />
                                </label>
                            </div>
                            {form.image_url && (
                                <div className="mt-3 rounded-xl overflow-hidden border border-border">
                                    <img src={form.image_url} alt="Preview" className="w-full max-h-48 object-cover" />
                                </div>
                            )}
                            {!form.image_url && (
                                <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1.5">
                                    <ImageIcon className="h-3.5 w-3.5" /> No picture — the card will show the first letters of the title.
                                </p>
                            )}
                        </div>
                        <div>
                            <Label>Sort order <span className="text-xs text-muted-foreground font-normal">(smaller appears first)</span></Label>
                            <Input type="number" value={form.order} onChange={(e) => setForm((f) => ({ ...f, order: parseInt(e.target.value || "0", 10) }))} className="rounded-xl mt-1.5" data-testid="form-link-order-input" />
                        </div>
                    </div>
                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Cancel</Button>
                        <Button onClick={save} disabled={busy || !form.title.trim() || !form.url.trim()} className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="form-link-save-btn">
                            {busy ? "Saving…" : (isEdit ? "Save changes" : "Add link")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
