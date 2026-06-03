import { useEffect, useRef, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Upload, Image as ImageIcon, Trash2, FolderPlus, ArrowLeft, X, Loader2, Star, Settings, Download, CheckSquare, Square } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

const NAVY = "#0A2463";
const RED = "#C8102E";

function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}

const CATEGORY_LABELS = {
    anniversary: "Anniversaries",
    ceremony: "Ceremonies",
    conference: "Conferences",
    tournament: "Tournaments",
    line: "Lines",
    community: "Community Service",
    other: "Other",
};

export default function Photos() {
    const { user } = useAuth();
    const [albums, setAlbums] = useState([]);
    const [activeAlbum, setActiveAlbum] = useState(null);
    const [photos, setPhotos] = useState([]);
    const [creatingAlbum, setCreatingAlbum] = useState(false);
    const [editingAlbum, setEditingAlbum] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [loadingPhotos, setLoadingPhotos] = useState(false);
    const [categoryFilter, setCategoryFilter] = useState("all");
    const [selectMode, setSelectMode] = useState(false);
    const [selectedIds, setSelectedIds] = useState([]);
    const [downloading, setDownloading] = useState(false);

    async function loadAlbums() {
        try {
            const { data } = await api.get("/photos/albums");
            setAlbums(data || []);
        } catch { setAlbums([]); }
    }
    async function loadPhotos(albumName) {
        setLoadingPhotos(true);
        try {
            const { data } = await api.get(`/photos?album=${encodeURIComponent(albumName)}`);
            setPhotos(data || []);
        } catch { setPhotos([]); }
        setLoadingPhotos(false);
    }

    useEffect(() => { loadAlbums(); }, []);
    useEffect(() => {
        if (activeAlbum) loadPhotos(activeAlbum.name);
        else setPhotos([]);
        setSelectMode(false);
        setSelectedIds([]);
    }, [activeAlbum]);

    function toggleSelect(id) {
        setSelectedIds((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
    }

    async function downloadAlbum() {
        if (!activeAlbum) return;
        setDownloading(true);
        try {
            const res = await api.post("/photos/download-zip", { album: activeAlbum.name }, { responseType: "blob" });
            triggerDownload(res.data, `aop-${activeAlbum.name.replace(/[^a-z0-9 -]/gi, "_")}.zip`);
            toast.success(`Downloaded "${activeAlbum.name}"`);
        } catch (e) { toast.error(e.response?.data?.detail || "Download failed"); }
        setDownloading(false);
    }

    async function downloadSelected() {
        if (selectedIds.length === 0) return;
        setDownloading(true);
        try {
            const res = await api.post("/photos/download-zip", { photo_ids: selectedIds }, { responseType: "blob" });
            triggerDownload(res.data, `aop-photos-${selectedIds.length}.zip`);
            toast.success(`Downloaded ${selectedIds.length} photo${selectedIds.length === 1 ? "" : "s"}`);
            setSelectMode(false); setSelectedIds([]);
        } catch (e) { toast.error(e.response?.data?.detail || "Download failed"); }
        setDownloading(false);
    }

    async function removePhoto(id) {
        if (!window.confirm("Delete this photo?")) return;
        try {
            await api.delete(`/photos/${id}`);
            toast.success("Photo deleted");
            await loadPhotos(activeAlbum.name);
            await loadAlbums();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed to delete"); }
    }

    async function setAsCover(photoId) {
        try {
            await api.put(`/photos/albums/${activeAlbum.id}`, { cover_photo_id: photoId });
            toast.success("Cover photo updated");
            await loadAlbums();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed to set cover"); }
    }

    async function removeAlbum(album) {
        if (!window.confirm(`Delete the "${album.name}" album? Photos inside are kept but will lose their grouping.`)) return;
        try {
            await api.delete(`/photos/albums/${album.id}`);
            toast.success("Album removed");
            await loadAlbums();
            if (activeAlbum?.id === album.id) setActiveAlbum(null);
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    const visibleAlbums = categoryFilter === "all" ? albums : albums.filter((a) => a.category === categoryFilter);
    const counts = albums.reduce((acc, a) => { acc[a.category || "other"] = (acc[a.category || "other"] || 0) + 1; return acc; }, {});

    return (
        <div className="bg-slate-50 min-h-screen">
            <section className="border-b-2 bg-white" style={{ borderColor: NAVY }}>
                <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10">
                    <div className="flex flex-wrap items-end justify-between gap-4">
                        <div>
                            {activeAlbum && (
                                <button onClick={() => setActiveAlbum(null)} className="text-sm text-slate-500 hover:text-primary inline-flex items-center gap-1 mb-2" data-testid="back-to-albums">
                                    <ArrowLeft className="h-4 w-4" /> All albums
                                </button>
                            )}
                            <div className="text-xs uppercase tracking-[0.3em] font-bold mb-1" style={{ color: RED }}>Photo Gallery</div>
                            <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter" style={{ color: NAVY }}>
                                {activeAlbum ? activeAlbum.name : "Albums"}
                            </h1>
                            <p className="text-slate-600 mt-2">
                                {activeAlbum
                                    ? `${photos.length} photo${photos.length === 1 ? "" : "s"} in this album. Click the ⭐ on any photo to make it the cover.`
                                    : `${albums.length} album${albums.length === 1 ? "" : "s"} · ${albums.reduce((a, b) => a + (b.count || 0), 0)} photos total.`}
                            </p>
                        </div>
                        {user && (
                            <div className="flex flex-wrap gap-2">
                                {!activeAlbum && (
                                    <Button onClick={() => setCreatingAlbum(true)} variant="outline" className="rounded-full" data-testid="create-album-btn">
                                        <FolderPlus className="h-4 w-4 mr-1.5" /> New album
                                    </Button>
                                )}
                                {activeAlbum && (
                                    <>
                                        {!selectMode ? (
                                            <>
                                                <Button onClick={() => setSelectMode(true)} variant="outline" className="rounded-full" data-testid="select-photos-btn">
                                                    <CheckSquare className="h-4 w-4 mr-1.5" /> Select
                                                </Button>
                                                <Button onClick={downloadAlbum} disabled={downloading || photos.length === 0} variant="outline" className="rounded-full" data-testid="download-album-btn">
                                                    {downloading ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Download className="h-4 w-4 mr-1.5" />}
                                                    Download album
                                                </Button>
                                            </>
                                        ) : (
                                            <>
                                                <Button onClick={() => { setSelectMode(false); setSelectedIds([]); }} variant="outline" className="rounded-full" data-testid="select-cancel-btn">
                                                    <X className="h-4 w-4 mr-1.5" /> Cancel
                                                </Button>
                                                <Button onClick={downloadSelected} disabled={downloading || selectedIds.length === 0} className="rounded-full bg-primary hover:bg-primary/90 text-white" data-testid="download-selected-btn">
                                                    {downloading ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Download className="h-4 w-4 mr-1.5" />}
                                                    Download {selectedIds.length || ""}
                                                </Button>
                                            </>
                                        )}
                                        <UploadButton album={activeAlbum.name} onDone={async () => { await loadPhotos(activeAlbum.name); await loadAlbums(); }} disabled={uploading} setUploading={setUploading} />
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                    {!activeAlbum && (
                        <CategoryFilter value={categoryFilter} onChange={setCategoryFilter} counts={counts} total={albums.length} />
                    )}
                </div>
            </section>

            <section className="max-w-7xl mx-auto px-6 lg:px-10 py-10">
                {!activeAlbum ? (
                    <AlbumGrid albums={visibleAlbums} onOpen={setActiveAlbum} onDelete={removeAlbum} onEdit={setEditingAlbum} currentUser={user} />
                ) : loadingPhotos ? (
                    <div className="grid place-items-center py-24"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
                ) : photos.length === 0 ? (
                    <div className="bg-white border-2 border-dashed border-slate-300 rounded-3xl p-16 text-center">
                        <ImageIcon className="h-12 w-12 mx-auto text-slate-400" />
                        <p className="mt-4 font-heading text-xl" style={{ color: NAVY }}>No photos yet</p>
                        <p className="text-sm text-slate-500">Click "Upload photos" above to start the memories.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="photo-grid">
                        {photos.map((p) => (
                            <PhotoTile
                                key={p.id}
                                photo={p}
                                currentUser={user}
                                onDelete={removePhoto}
                                onSetCover={(albumCanEdit) => albumCanEdit ? setAsCover(p.id) : null}
                                albumCanEdit={user && (user.role === "admin" || activeAlbum?.created_by === user.id)}
                                selectMode={selectMode}
                                selected={selectedIds.includes(p.id)}
                                onToggleSelect={() => toggleSelect(p.id)}
                            />
                        ))}
                    </div>
                )}
            </section>

            <CreateAlbumDialog open={creatingAlbum} onClose={() => setCreatingAlbum(false)} onCreated={async (a) => { setCreatingAlbum(false); await loadAlbums(); setActiveAlbum(a); }} />
            <EditAlbumDialog album={editingAlbum} onClose={() => setEditingAlbum(null)} onSaved={async () => { setEditingAlbum(null); await loadAlbums(); }} />
        </div>
    );
}

function CategoryFilter({ value, onChange, counts, total }) {
    const all = ["all", ...Object.keys(CATEGORY_LABELS)];
    return (
        <div className="flex flex-wrap gap-2 mt-6" data-testid="category-filter">
            {all.map((c) => {
                const n = c === "all" ? total : (counts[c] || 0);
                if (c !== "all" && n === 0) return null;
                const active = value === c;
                return (
                    <button
                        key={c}
                        onClick={() => onChange(c)}
                        className={`text-xs px-3 py-1.5 rounded-full font-semibold uppercase tracking-wide transition-all ${active ? "bg-primary text-white shadow-warm" : "bg-white text-slate-600 border border-slate-200 hover:border-primary"}`}
                        data-testid={`category-pill-${c}`}
                    >
                        {c === "all" ? `All (${n})` : `${CATEGORY_LABELS[c]} (${n})`}
                    </button>
                );
            })}
        </div>
    );
}

function AlbumGrid({ albums, onOpen, onDelete, onEdit, currentUser }) {
    if (albums.length === 0) {
        return (
            <div className="bg-white border-2 border-dashed border-slate-300 rounded-3xl p-16 text-center">
                <ImageIcon className="h-12 w-12 mx-auto text-slate-400" />
                <p className="mt-4 font-heading text-xl" style={{ color: NAVY }}>No albums in this category</p>
                <p className="text-sm text-slate-500">Switch categories or create a new album.</p>
            </div>
        );
    }
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="album-grid">
            {albums.map((a) => (
                <AlbumCard key={a.id || a.name} album={a} onOpen={() => onOpen(a)} onDelete={() => onDelete(a)} onEdit={() => onEdit(a)} currentUser={currentUser} />
            ))}
        </div>
    );
}

function AlbumCard({ album, onOpen, onDelete, onEdit, currentUser }) {
    const canEdit = currentUser && (currentUser.role === "admin" || album.created_by === currentUser.id);
    const canDelete = canEdit && !album.is_default;
    return (
        <div
            onClick={onOpen}
            className="group cursor-pointer relative bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-warm hover:-translate-y-1 hover:shadow-warm-lg transition-all"
            data-testid={`album-card-${album.name}`}
        >
            <div className="aspect-[4/3] bg-gradient-to-br from-primary/15 to-primary/5 grid place-items-center relative overflow-hidden">
                {album.cover_url ? (
                    <img src={mediaUrl(album.cover_url)} alt={album.name} className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" data-testid={`album-cover-${album.name}`} />
                ) : (
                    <ImageIcon className="h-12 w-12 text-primary/40" />
                )}
                <span className="absolute top-2 left-2 text-[10px] font-bold uppercase tracking-wider bg-white/95 text-slate-700 px-2 py-1 rounded-full backdrop-blur">
                    {CATEGORY_LABELS[album.category] || "Other"}
                </span>
            </div>
            <div className="p-4">
                <h3 className="font-heading font-black text-lg leading-tight truncate" style={{ color: NAVY }}>{album.name}</h3>
                <div className="text-xs text-slate-500 mt-1">
                    {album.count || 0} photo{album.count === 1 ? "" : "s"}
                    {album.is_default ? " · Official album" : album.created_by_name ? ` · by ${album.created_by_name}` : ""}
                </div>
            </div>
            <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                    onClick={async (e) => {
                        e.stopPropagation();
                        try {
                            const res = await api.post("/photos/download-zip", { album: album.name }, { responseType: "blob" });
                            triggerDownload(res.data, `aop-${album.name.replace(/[^a-z0-9 -]/gi, "_")}.zip`);
                            toast.success(`Downloaded "${album.name}"`);
                        } catch (err) { toast.error(err.response?.data?.detail || "Download failed"); }
                    }}
                    className="rounded-full bg-white/95 hover:bg-white p-1.5 shadow text-primary"
                    title="Download album"
                    data-testid={`download-album-card-${album.name}`}
                >
                    <Download className="h-3.5 w-3.5" />
                </button>
                {canEdit && (
                    <button
                        onClick={(e) => { e.stopPropagation(); onEdit(); }}
                        className="rounded-full bg-white/95 hover:bg-white p-1.5 shadow text-slate-700"
                        data-testid={`edit-album-${album.name}`}
                        title="Edit album"
                    >
                        <Settings className="h-3.5 w-3.5" />
                    </button>
                )}
                {canDelete && (
                    <button
                        onClick={(e) => { e.stopPropagation(); onDelete(); }}
                        className="rounded-full bg-white/95 hover:bg-white p-1.5 shadow text-destructive"
                        data-testid={`delete-album-${album.name}`}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                    </button>
                )}
            </div>
        </div>
    );
}

function PhotoTile({ photo, currentUser, onDelete, onSetCover, albumCanEdit, selectMode, selected, onToggleSelect }) {
    const [src, setSrc] = useState("");

    useEffect(() => {
        let revoked = null;
        (async () => {
            try {
                const path = photo.url.startsWith("/api") ? photo.url.slice(4) : photo.url;
                const { data } = await api.get(path, { responseType: "blob" });
                const url = URL.createObjectURL(data);
                revoked = url;
                setSrc(url);
            } catch {
                /* ignore */
            }
        })();
        return () => { if (revoked) URL.revokeObjectURL(revoked); };
    }, [photo.url]);

    const canDelete = currentUser && (currentUser.role === "admin" || currentUser.id === photo.uploaded_by);

    async function downloadOne(e) {
        e.stopPropagation();
        try {
            const path = photo.url.startsWith("/api") ? photo.url.slice(4) : photo.url;
            const res = await api.get(path, { responseType: "blob" });
            const ext = (photo.original_filename || photo.url).split(".").pop().toLowerCase();
            const base = (photo.title || photo.original_filename || "photo").replace(/[^a-z0-9._ -]/gi, "_");
            const name = base.toLowerCase().endsWith(`.${ext}`) ? base : `${base}.${ext}`;
            triggerDownload(res.data, name);
        } catch (e) { toast.error("Download failed"); }
    }

    if (selectMode) {
        return (
            <button
                type="button"
                onClick={onToggleSelect}
                className={`group relative aspect-square rounded-2xl overflow-hidden bg-muted border-4 shadow-warm transition-all ${selected ? "border-primary" : "border-transparent hover:border-primary/40"}`}
                data-testid={`photo-select-${photo.id}`}
            >
                {src ? <img src={src} alt={photo.title} className="w-full h-full object-cover" /> : <div className="w-full h-full animate-pulse bg-muted" />}
                <div className={`absolute top-2 left-2 rounded-full p-1.5 shadow ${selected ? "bg-primary text-white" : "bg-white/90 text-slate-400"}`}>
                    {selected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
                </div>
            </button>
        );
    }

    return (
        <div className="group relative aspect-square rounded-2xl overflow-hidden bg-muted border border-slate-200 shadow-warm" data-testid={`photo-${photo.id}`}>
            {src ? (
                <img src={src} alt={photo.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
            ) : (
                <div className="w-full h-full animate-pulse bg-muted" />
            )}
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3 text-white opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="text-xs font-semibold truncate">{photo.title || "Untitled"}</div>
                <div className="text-[10px] opacity-80">
                    by {photo.uploaded_by_name} · {photo.created_at && format(parseISO(photo.created_at), "MMM d")}
                </div>
            </div>
            <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                    onClick={downloadOne}
                    className="rounded-full bg-white/95 hover:bg-white p-1.5 shadow text-primary"
                    title="Download photo"
                    data-testid={`download-photo-${photo.id}`}
                >
                    <Download className="h-3.5 w-3.5" />
                </button>
                {albumCanEdit && (
                    <button
                        onClick={() => onSetCover(true)}
                        className="rounded-full bg-white/95 hover:bg-white p-1.5 shadow text-amber-500"
                        title="Make album cover"
                        data-testid={`set-cover-${photo.id}`}
                    >
                        <Star className="h-3.5 w-3.5" />
                    </button>
                )}
                {canDelete && (
                    <button
                        onClick={() => onDelete(photo.id)}
                        className="rounded-full bg-white/90 hover:bg-white p-1.5 shadow"
                        data-testid={`delete-photo-${photo.id}`}
                    >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </button>
                )}
            </div>
        </div>
    );
}

function UploadButton({ album, onDone, disabled, setUploading }) {
    const inputRef = useRef(null);
    const [busy, setBusy] = useState(false);

    async function pick(files) {
        if (!files || files.length === 0) return;
        setBusy(true); setUploading(true);
        try {
            const fd = new FormData();
            for (const f of files) fd.append("files", f);
            fd.append("album", album);
            const { data } = await api.post("/photos/bulk", fd, { headers: { "Content-Type": "multipart/form-data" } });
            const ok = (data.uploaded || []).length;
            const failed = (data.failed || []).length;
            if (ok && !failed) toast.success(`Uploaded ${ok} photo${ok === 1 ? "" : "s"}`);
            else if (ok && failed) toast.warning(`Uploaded ${ok}, but ${failed} failed`);
            else toast.error(`All ${failed} uploads failed`);
            onDone?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
        setBusy(false); setUploading(false);
        if (inputRef.current) inputRef.current.value = "";
    }

    return (
        <>
            <input
                ref={inputRef}
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={(e) => pick(Array.from(e.target.files || []))}
                data-testid="photos-multi-input"
            />
            <Button
                onClick={() => inputRef.current?.click()}
                disabled={busy || disabled}
                className="rounded-full bg-primary hover:bg-primary/90 shadow-warm text-white"
                data-testid="upload-photos-btn"
            >
                {busy ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Uploading…</> : <><Upload className="h-4 w-4 mr-1.5" /> Upload photos</>}
            </Button>
        </>
    );
}

function CreateAlbumDialog({ open, onClose, onCreated }) {
    const [name, setName] = useState("");
    const [category, setCategory] = useState("other");
    const [busy, setBusy] = useState(false);

    useEffect(() => { if (open) { setName(""); setCategory("other"); } }, [open]);

    async function create() {
        const value = name.trim();
        if (!value) { toast.error("Give the album a name"); return; }
        setBusy(true);
        try {
            const { data } = await api.post("/photos/albums", { name: value, category });
            toast.success(`Album "${data.name}" created`);
            onCreated?.(data);
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>New album</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 mt-2">
                    <div>
                        <Label>Album name</Label>
                        <Input
                            value={name}
                            autoFocus
                            onChange={(e) => setName(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter" && !busy) create(); }}
                            placeholder="e.g. Commitment Ceremony 2031"
                            className="rounded-xl mt-1.5"
                            data-testid="album-name-input"
                        />
                    </div>
                    <div>
                        <Label>Category</Label>
                        <Select value={category} onValueChange={setCategory}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="album-category-select"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                                    <SelectItem key={k} value={k}>{v}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-slate-500 mt-1.5">We'll auto-detect this from the name if you skip it.</p>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} className="rounded-full" type="button">Cancel</Button>
                    <Button onClick={create} disabled={busy || !name.trim()} className="rounded-full bg-primary hover:bg-primary/90 text-white" data-testid="create-album-submit">
                        {busy ? "Creating…" : "Create album"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function EditAlbumDialog({ album, onClose, onSaved }) {
    const [category, setCategory] = useState("other");
    const [busy, setBusy] = useState(false);
    useEffect(() => { if (album) setCategory(album.category || "other"); }, [album]);
    if (!album) return null;

    async function save() {
        setBusy(true);
        try {
            await api.put(`/photos/albums/${album.id}`, { category });
            toast.success("Album updated");
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <Dialog open={!!album} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>Edit "{album.name}"</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2">
                    <div>
                        <Label>Category</Label>
                        <Select value={category} onValueChange={setCategory}>
                            <SelectTrigger className="rounded-xl mt-1.5" data-testid="edit-album-category-select"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                                    <SelectItem key={k} value={k}>{v}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <p className="text-xs text-slate-500">To change the cover photo, open the album and click the ⭐ on any photo.</p>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} className="rounded-full" type="button">Cancel</Button>
                    <Button onClick={save} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90 text-white" data-testid="edit-album-save-btn">
                        {busy ? "Saving…" : "Save"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
