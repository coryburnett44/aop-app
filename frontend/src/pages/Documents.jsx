import { useEffect, useRef, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "../components/ui/dialog";
import { FileText, Upload, Download, Trash2, ExternalLink, Pencil, Plus, Image as ImageIcon, Folder, FolderPlus, ArrowLeft, ChevronRight } from "lucide-react";
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
    const [folders, setFolders] = useState([]);
    const [filter, setFilter] = useState("all");
    const [activeFolder, setActiveFolder] = useState(null); // null = root view; otherwise folder object
    const [links, setLinks] = useState([]);
    const isAdmin = user?.role === "admin";

    const load = async () => {
        const url = "/documents" + (filter !== "all" ? `?category=${encodeURIComponent(filter)}` : "");
        const { data } = await api.get(url);
        setDocs(data);
    };
    const loadFolders = async () => {
        try {
            const { data } = await api.get("/document-folders");
            setFolders(data || []);
        } catch { setFolders([]); }
    };
    const loadLinks = async () => {
        try {
            const { data } = await api.get("/form-links");
            setLinks(data || []);
        } catch { setLinks([]); }
    };

    useEffect(() => { load().catch(() => {}); }, [filter]);
    useEffect(() => { loadFolders(); loadLinks(); }, []);

    async function remove(id) {
        if (!confirm("Delete this document?")) return;
        await api.delete(`/documents/${id}`);
        toast.success("Deleted");
        load();
    }

    async function removeFolder(folder) {
        if (!confirm(`Delete the folder "${folder.name}"? Documents inside will become uncategorized (not deleted).`)) return;
        try {
            await api.delete(`/document-folders/${folder.id}`);
            toast.success("Folder removed");
            await loadFolders();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    const categories = Array.from(new Set(docs.map((d) => d.category))).sort();
    const rootFolders = folders.filter((f) => !f.parent_id);
    const childFolders = activeFolder ? folders.filter((f) => f.parent_id === activeFolder.id) : [];

    // Documents shown depend on which folder you're inside
    const visibleDocs = activeFolder
        ? docs.filter((d) => d.folder_id === activeFolder.id)
        : docs.filter((d) => !d.folder_id);

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
                <div>
                    {activeFolder && (
                        <button onClick={() => setActiveFolder(null)} className="text-sm text-slate-500 hover:text-primary inline-flex items-center gap-1 mb-2" data-testid="back-to-doc-root">
                            <ArrowLeft className="h-4 w-4" /> All folders
                        </button>
                    )}
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">
                        {activeFolder ? activeFolder.name : "AOP Forms"}
                    </h1>
                    <p className="text-muted-foreground mt-2">
                        {activeFolder ? "Documents in this folder. Subfolders show first." : "Bylaws, minutes, forms, and chapter resources — all in one place."}
                    </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                    {isAdmin && <NewFolderDialog folders={folders} activeFolder={activeFolder} onCreated={loadFolders} />}
                    {isAdmin && <UploadDocDialog folder={activeFolder} folders={folders} onDone={() => { load(); loadFolders(); }} />}
                </div>
            </div>

            {/* Picture link cards — admin manages, members click through to external pages */}
            {!activeFolder && (links.length > 0 || isAdmin) && (
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

            {/* Folder grid */}
            {((activeFolder && childFolders.length > 0) || (!activeFolder && rootFolders.length > 0)) && (
                <section className="mb-8">
                    <h2 className="font-heading text-2xl font-bold mb-3">{activeFolder ? "Subfolders" : "Folders"}</h2>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="doc-folder-grid">
                        {(activeFolder ? childFolders : rootFolders).map((f) => (
                            <button
                                key={f.id}
                                onClick={() => setActiveFolder(f)}
                                className="group bg-card rounded-2xl border border-border p-4 text-left flex items-center gap-3 shadow-warm hover:-translate-y-0.5 transition-all"
                                data-testid={`doc-folder-${f.id}`}
                            >
                                <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary grid place-items-center shrink-0">
                                    <Folder className="h-6 w-6" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-heading font-bold truncate">{f.name}</div>
                                    <div className="text-xs text-muted-foreground">{f.doc_count} document{f.doc_count !== 1 ? "s" : ""}{!activeFolder && folders.some((c) => c.parent_id === f.id) ? ` · ${folders.filter((c) => c.parent_id === f.id).length} subfolders` : ""}</div>
                                </div>
                                {isAdmin && (
                                    <span
                                        onClick={(e) => { e.stopPropagation(); removeFolder(f); }}
                                        className="text-muted-foreground hover:text-destructive p-1"
                                        data-testid={`delete-folder-${f.id}`}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </span>
                                )}
                                <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:translate-x-0.5 transition-transform" />
                            </button>
                        ))}
                    </div>
                </section>
            )}

            {categories.length > 0 && !activeFolder && (
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

            {visibleDocs.length === 0 ? (
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-3xl p-16 text-center">
                    <FileText className="h-12 w-12 mx-auto text-muted-foreground/50" />
                    <p className="mt-4 font-heading text-xl">{activeFolder ? "No documents in this folder yet" : "No AOP forms yet"}</p>
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
                            {visibleDocs.map((d) => (
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

function NewFolderDialog({ folders, activeFolder, onCreated }) {
    const [open, setOpen] = useState(false);
    const [name, setName] = useState("");
    // When inside a root folder, default the new folder's parent to that folder (creating a subfolder)
    const [parentId, setParentId] = useState("root");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (open) { setName(""); setParentId(activeFolder ? activeFolder.id : "root"); }
    }, [open, activeFolder]);

    // Only root folders are eligible to be parents (2-level limit)
    const eligibleParents = folders.filter((f) => !f.parent_id);

    async function save() {
        if (!name.trim()) { toast.error("Folder name is required"); return; }
        setBusy(true);
        try {
            await api.post("/document-folders", { name: name.trim(), parent_id: parentId === "root" ? null : parentId });
            toast.success("Folder created");
            setOpen(false);
            onCreated?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="rounded-full" data-testid="new-folder-btn">
                    <FolderPlus className="h-4 w-4 mr-1.5" /> New folder
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md" data-testid="folder-create-dialog">
                <DialogHeader><DialogTitle className="font-heading text-2xl">New folder</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div>
                        <Label>Folder name</Label>
                        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus className="rounded-xl mt-1.5" placeholder="e.g. 2027 Meeting Minutes" data-testid="folder-name-input" />
                    </div>
                    <div>
                        <Label>Parent folder</Label>
                        <Select value={parentId} onValueChange={setParentId}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="folder-parent-select"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="root">— Top level —</SelectItem>
                                {eligibleParents.map((f) => (
                                    <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground mt-1.5">Subfolders cannot have their own subfolders (max 2 levels).</p>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Cancel</Button>
                    <Button onClick={save} disabled={busy || !name.trim()} className="rounded-full bg-primary hover:bg-primary/90" data-testid="folder-create-submit">
                        {busy ? "Creating…" : "Create folder"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
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

function UploadDocDialog({ onDone, folder, folders }) {
    const [open, setOpen] = useState(false);
    const [files, setFiles] = useState([]);
    const [category, setCategory] = useState("general");
    const [folderId, setFolderId] = useState(folder?.id || "");
    const [busy, setBusy] = useState(false);
    const inputRef = useRef(null);

    useEffect(() => { if (open) setFolderId(folder?.id || ""); }, [open, folder]);

    function addFiles(picked) {
        if (!picked || picked.length === 0) return;
        // Cap at 50 to mirror backend limit
        const merged = [...files, ...picked].slice(0, 50);
        setFiles(merged);
    }

    async function upload() {
        if (files.length === 0) return;
        setBusy(true);
        try {
            if (files.length === 1) {
                const fd = new FormData();
                fd.append("file", files[0]);
                fd.append("title", files[0].name);
                fd.append("category", category);
                if (folderId) fd.append("folder_id", folderId);
                await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
                toast.success("Document uploaded");
            } else {
                const fd = new FormData();
                for (const f of files) fd.append("files", f);
                fd.append("category", category);
                if (folderId) fd.append("folder_id", folderId);
                const { data } = await api.post("/documents/bulk", fd, { headers: { "Content-Type": "multipart/form-data" } });
                const ok = (data.uploaded || []).length;
                const failed = (data.failed || []).length;
                if (ok && !failed) toast.success(`Uploaded ${ok} documents`);
                else if (ok && failed) toast.warning(`Uploaded ${ok}, but ${failed} failed`);
                else toast.error(`All ${failed} uploads failed`);
            }
            setOpen(false);
            setFiles([]);
            setCategory("general");
            onDone?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Upload failed");
        }
        setBusy(false);
    }

    // Flat list of folder choices, with hierarchy hint
    const folderChoices = (folders || []).map((f) => {
        const parent = f.parent_id ? (folders || []).find((p) => p.id === f.parent_id) : null;
        return { id: f.id, label: parent ? `${parent.name} / ${f.name}` : f.name };
    }).sort((a, b) => a.label.localeCompare(b.label));

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="upload-doc-btn">
                    <Upload className="h-4 w-4 mr-1.5" /> Upload form{folder ? ` to ${folder.name}` : ""}
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Upload AOP form{files.length > 1 ? "s" : ""}</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div
                        onClick={() => inputRef.current?.click()}
                        className="border-2 border-dashed border-border rounded-2xl p-8 text-center cursor-pointer hover:bg-muted/50 transition-colors"
                        data-testid="doc-dropzone"
                    >
                        <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                        <div className="mt-3 text-sm">
                            {files.length === 0 ? "Click to choose one or more files (PDF, DOC, XLSX, TXT, CSV, PPTX)" : <span className="font-medium">{files.length} file{files.length !== 1 ? "s" : ""} selected</span>}
                        </div>
                        <input
                            ref={inputRef}
                            type="file"
                            multiple
                            accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.pptx"
                            hidden
                            onChange={(e) => { addFiles(Array.from(e.target.files || [])); e.target.value = ""; }}
                            data-testid="doc-file-input"
                        />
                    </div>
                    {files.length > 0 && (
                        <div className="border border-border rounded-xl p-2 max-h-32 overflow-y-auto space-y-1" data-testid="doc-files-list">
                            {files.map((f, i) => (
                                <div key={i} className="flex items-center gap-2 text-xs">
                                    <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                    <span className="truncate flex-1">{f.name}</span>
                                    <span className="text-muted-foreground shrink-0">{humanSize(f.size)}</span>
                                    <button onClick={() => setFiles((p) => p.filter((_, idx) => idx !== i))} className="text-muted-foreground hover:text-destructive">
                                        <Trash2 className="h-3 w-3" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                    <div>
                        <Label>Category</Label>
                        <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. bylaws, minutes, forms" className="rounded-xl mt-1.5" data-testid="doc-category-input" />
                    </div>
                    <div>
                        <Label>Folder <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                        <Select value={folderId || "_root"} onValueChange={(v) => setFolderId(v === "_root" ? "" : v)}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="doc-folder-select"><SelectValue placeholder="— No folder —" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="_root">— No folder —</SelectItem>
                                {folderChoices.map((f) => <SelectItem key={f.id} value={f.id}>{f.label}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <Button onClick={upload} disabled={files.length === 0 || busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="doc-upload-submit">
                        {busy ? "Uploading…" : files.length > 1 ? `Upload ${files.length} files` : "Upload"}
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
                        <img src={mediaUrl(link.image_url)} alt={link.title} className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-500" />
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
                                <div className="mt-3 rounded-xl overflow-hidden border-2 border-border bg-muted/30">
                                    <div className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-bold text-muted-foreground border-b border-border bg-muted">
                                        Preview
                                    </div>
                                    <img
                                        src={mediaUrl(form.image_url)}
                                        alt="Picture preview"
                                        className="w-full h-64 object-contain bg-white"
                                        onError={(e) => { e.currentTarget.style.opacity = '0.3'; e.currentTarget.alt = 'Preview failed to load — check the URL'; }}
                                    />
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
