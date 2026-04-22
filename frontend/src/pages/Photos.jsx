import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Upload, Image as ImageIcon, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export default function Photos() {
    const { user } = useAuth();
    const [photos, setPhotos] = useState([]);
    const [albums, setAlbums] = useState([]);
    const [activeAlbum, setActiveAlbum] = useState("all");

    const load = async () => {
        const [ps, as] = await Promise.all([
            api.get("/photos" + (activeAlbum !== "all" ? `?album=${encodeURIComponent(activeAlbum)}` : "")),
            api.get("/photos/albums"),
        ]);
        setPhotos(ps.data);
        setAlbums(as.data);
    };

    useEffect(() => { load().catch(() => {}); }, [activeAlbum]);

    async function remove(id) {
        if (!confirm("Delete this photo?")) return;
        await api.delete(`/photos/${id}`);
        toast.success("Deleted");
        load();
    }

    return (
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Photo gallery</h1>
                    <p className="text-muted-foreground mt-2">Moments from our events, rituals, and brotherhood.</p>
                </div>
                {user && <UploadPhotoDialog onDone={load} />}
            </div>

            <div className="flex flex-wrap gap-2 mb-6">
                <Chip active={activeAlbum === "all"} onClick={() => setActiveAlbum("all")} testid="album-all">
                    All ({photos.length})
                </Chip>
                {albums.map((a) => (
                    <Chip key={a.album} active={activeAlbum === a.album} onClick={() => setActiveAlbum(a.album)} testid={`album-${a.album}`}>
                        {a.album} · {a.count}
                    </Chip>
                ))}
            </div>

            {photos.length === 0 ? (
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-3xl p-16 text-center">
                    <ImageIcon className="h-12 w-12 mx-auto text-muted-foreground/50" />
                    <p className="mt-4 font-heading text-xl">No photos yet</p>
                    <p className="text-sm text-muted-foreground">Be the first to share a memory.</p>
                </div>
            ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                    {photos.map((p) => (
                        <div key={p.id} className="group relative aspect-square rounded-2xl overflow-hidden bg-muted border border-border shadow-warm" data-testid={`photo-${p.id}`}>
                            <img src={`${BACKEND}${p.url}`} alt={p.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3 text-white opacity-0 group-hover:opacity-100 transition-opacity">
                                <div className="text-xs font-semibold truncate">{p.title || "Untitled"}</div>
                                <div className="text-[10px] opacity-80">
                                    by {p.uploaded_by_name} · {p.created_at && format(parseISO(p.created_at), "MMM d")}
                                </div>
                            </div>
                            {user && (user.role === "admin" || user.id === p.uploaded_by) && (
                                <button
                                    onClick={() => remove(p.id)}
                                    className="absolute top-2 right-2 rounded-full bg-white/90 hover:bg-white p-1.5 shadow opacity-0 group-hover:opacity-100 transition-opacity"
                                    data-testid={`delete-photo-${p.id}`}
                                >
                                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function Chip({ active, onClick, children, testid }) {
    return (
        <button
            onClick={onClick}
            data-testid={testid}
            className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize transition-colors ${
                active ? "bg-primary text-primary-foreground shadow-warm" : "bg-muted hover:bg-muted/70"
            }`}
        >
            {children}
        </button>
    );
}

function UploadPhotoDialog({ onDone }) {
    const [open, setOpen] = useState(false);
    const [file, setFile] = useState(null);
    const [title, setTitle] = useState("");
    const [album, setAlbum] = useState("general");
    const [busy, setBusy] = useState(false);
    const inputRef = useRef(null);

    async function upload() {
        if (!file) return;
        setBusy(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("title", title);
            fd.append("album", album);
            await api.post("/photos", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Photo uploaded");
            setOpen(false);
            setFile(null);
            setTitle("");
            setAlbum("general");
            onDone();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Upload failed");
        }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button className="rounded-full bg-primary hover:bg-primary/90 shadow-warm" data-testid="upload-photo-btn">
                    <Upload className="h-4 w-4 mr-1.5" /> Upload photo
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl">Upload photo</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    <div
                        onClick={() => inputRef.current?.click()}
                        className="border-2 border-dashed border-border rounded-2xl p-8 text-center cursor-pointer hover:bg-muted/50 transition-colors"
                        data-testid="photo-dropzone"
                    >
                        <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                        <div className="mt-3 text-sm">
                            {file ? <span className="font-medium">{file.name}</span> : "Click to choose an image (jpg, png, gif, webp)"}
                        </div>
                        <input
                            ref={inputRef}
                            type="file"
                            accept="image/*"
                            hidden
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            data-testid="photo-file-input"
                        />
                    </div>
                    <div>
                        <Label>Title</Label>
                        <Input value={title} onChange={(e) => setTitle(e.target.value)} className="rounded-xl mt-1.5" data-testid="photo-title-input" />
                    </div>
                    <div>
                        <Label>Album</Label>
                        <Input value={album} onChange={(e) => setAlbum(e.target.value)} placeholder="e.g. initiation-2026" className="rounded-xl mt-1.5" data-testid="photo-album-input" />
                    </div>
                    <Button onClick={upload} disabled={!file || busy} className="w-full rounded-full bg-primary hover:bg-primary/90" data-testid="photo-upload-submit">
                        {busy ? "Uploading…" : "Upload"}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
