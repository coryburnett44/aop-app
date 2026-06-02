import { useEffect, useRef, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Upload, Image as ImageIcon, Trash2, FolderPlus, ArrowLeft, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function Photos() {
    const { user } = useAuth();
    const [albums, setAlbums] = useState([]);
    const [activeAlbum, setActiveAlbum] = useState(null); // album object or null=index view
    const [photos, setPhotos] = useState([]);
    const [creatingAlbum, setCreatingAlbum] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [loadingPhotos, setLoadingPhotos] = useState(false);

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
    }, [activeAlbum]);

    async function removePhoto(id) {
        if (!window.confirm("Delete this photo?")) return;
        try {
            await api.delete(`/photos/${id}`);
            toast.success("Photo deleted");
            await loadPhotos(activeAlbum.name);
            await loadAlbums();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed to delete"); }
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
                                    ? `${photos.length} photo${photos.length === 1 ? "" : "s"} in this album.`
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
                                    <UploadButton album={activeAlbum.name} onDone={async () => { await loadPhotos(activeAlbum.name); await loadAlbums(); }} disabled={uploading} setUploading={setUploading} />
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </section>

            <section className="max-w-7xl mx-auto px-6 lg:px-10 py-10">
                {!activeAlbum ? (
                    <AlbumGrid albums={albums} onOpen={setActiveAlbum} onDelete={removeAlbum} currentUser={user} />
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
                            <PhotoTile key={p.id} photo={p} currentUser={user} onDelete={removePhoto} />
                        ))}
                    </div>
                )}
            </section>

            <CreateAlbumDialog open={creatingAlbum} onClose={() => setCreatingAlbum(false)} onCreated={async (a) => { setCreatingAlbum(false); await loadAlbums(); setActiveAlbum(a); }} />
        </div>
    );
}

function AlbumGrid({ albums, onOpen, onDelete, currentUser }) {
    if (albums.length === 0) {
        return (
            <div className="bg-white border-2 border-dashed border-slate-300 rounded-3xl p-16 text-center">
                <ImageIcon className="h-12 w-12 mx-auto text-slate-400" />
                <p className="mt-4 font-heading text-xl" style={{ color: NAVY }}>No albums yet</p>
                <p className="text-sm text-slate-500">Click "New album" to make one.</p>
            </div>
        );
    }
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="album-grid">
            {albums.map((a) => (
                <AlbumCard key={a.id || a.name} album={a} onOpen={() => onOpen(a)} onDelete={() => onDelete(a)} currentUser={currentUser} />
            ))}
        </div>
    );
}

function AlbumCard({ album, onOpen, onDelete, currentUser }) {
    const canDelete = currentUser && !album.is_default && (currentUser.role === "admin" || album.created_by === currentUser.id);
    return (
        <div
            onClick={onOpen}
            className="group cursor-pointer relative bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-warm hover:-translate-y-1 hover:shadow-warm-lg transition-all"
            data-testid={`album-card-${album.name}`}
        >
            <div className="aspect-[4/3] bg-gradient-to-br from-primary/15 to-primary/5 grid place-items-center">
                <ImageIcon className="h-12 w-12 text-primary/40" />
            </div>
            <div className="p-4">
                <h3 className="font-heading font-black text-lg leading-tight truncate" style={{ color: NAVY }}>{album.name}</h3>
                <div className="text-xs text-slate-500 mt-1">
                    {album.count || 0} photo{album.count === 1 ? "" : "s"}
                    {album.is_default ? " · Official album" : album.created_by_name ? ` · by ${album.created_by_name}` : ""}
                </div>
            </div>
            {canDelete && (
                <button
                    onClick={(e) => { e.stopPropagation(); onDelete(); }}
                    className="absolute top-2 right-2 rounded-full bg-white/95 hover:bg-white p-1.5 shadow opacity-0 group-hover:opacity-100 transition-opacity text-destructive"
                    data-testid={`delete-album-${album.name}`}
                >
                    <Trash2 className="h-3.5 w-3.5" />
                </button>
            )}
        </div>
    );
}

function PhotoTile({ photo, currentUser, onDelete }) {
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
            {canDelete && (
                <button
                    onClick={() => onDelete(photo.id)}
                    className="absolute top-2 right-2 rounded-full bg-white/90 hover:bg-white p-1.5 shadow opacity-0 group-hover:opacity-100 transition-opacity"
                    data-testid={`delete-photo-${photo.id}`}
                >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </button>
            )}
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
    const [busy, setBusy] = useState(false);

    useEffect(() => { if (open) setName(""); }, [open]);

    async function create() {
        const value = name.trim();
        if (!value) { toast.error("Give the album a name"); return; }
        setBusy(true);
        try {
            const { data } = await api.post("/photos/albums", { name: value });
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
                        <p className="text-xs text-slate-500 mt-1.5">Album names must be unique. Drop your photos in next.</p>
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
