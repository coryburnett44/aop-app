import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { FileText, Upload, Download, Trash2 } from "lucide-react";
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

    const load = async () => {
        const url = "/documents" + (filter !== "all" ? `?category=${encodeURIComponent(filter)}` : "");
        const { data } = await api.get(url);
        setDocs(data);
    };

    useEffect(() => { load().catch(() => {}); }, [filter]);

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
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Documents</h1>
                    <p className="text-muted-foreground mt-2">Bylaws, minutes, forms, resources — all in one place.</p>
                </div>
                {user && <UploadDocDialog onDone={load} />}
            </div>

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
                    <p className="mt-4 font-heading text-xl">No documents yet</p>
                    <p className="text-sm text-muted-foreground">Upload the bylaws, meeting notes, and resources.</p>
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
                    <Upload className="h-4 w-4 mr-1.5" /> Upload document
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Upload document</DialogTitle></DialogHeader>
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
