import { useRef, useState, useEffect } from "react";
import { api, mediaUrl } from "../lib/api";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Camera, Upload, RefreshCw } from "lucide-react";
import { toast } from "sonner";

/**
 * AvatarUploader — lets the signed-in member set a new avatar via:
 *  (a) Upload file from phone gallery or laptop
 *  (b) Take photo via device camera (getUserMedia)
 * On success: POST /members/me/avatar (multipart), receive avatar_url, calls onUpdated.
 */
export default function AvatarUploader({ user, onUpdated }) {
    const fileInputRef = useRef(null);
    const [camOpen, setCamOpen] = useState(false);

    async function uploadBlob(blob, filename) {
        const fd = new FormData();
        fd.append("file", blob, filename);
        try {
            const { data } = await api.post("/members/me/avatar", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            toast.success("Avatar updated");
            onUpdated?.(data.avatar_url);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Upload failed");
        }
    }

    async function handleFile(file) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { toast.error("Avatar must be under 10 MB"); return; }
        await uploadBlob(file, file.name || "avatar.jpg");
    }

    return (
        <div className="flex items-center gap-4" data-testid="avatar-uploader">
            <Avatar className="h-20 w-20 border-2 border-white shadow-warm" data-testid="avatar-current">
                {user?.avatar_url && <AvatarImage src={mediaUrl(user.avatar_url)} />}
                <AvatarFallback className="bg-primary/15 text-primary text-2xl font-bold">
                    {user?.name?.[0]?.toUpperCase() || "M"}
                </AvatarFallback>
            </Avatar>
            <div className="flex flex-col gap-2">
                <div className="flex flex-wrap gap-2">
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        data-testid="avatar-file-input"
                        onChange={(e) => handleFile(e.target.files?.[0])}
                    />
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="rounded-full"
                        onClick={() => fileInputRef.current?.click()}
                        data-testid="avatar-upload-btn"
                    >
                        <Upload className="h-3.5 w-3.5 mr-1" /> Upload
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="rounded-full"
                        onClick={() => setCamOpen(true)}
                        data-testid="avatar-camera-btn"
                    >
                        <Camera className="h-3.5 w-3.5 mr-1" /> Take photo
                    </Button>
                </div>
                <p className="text-xs text-muted-foreground">JPG / PNG / WebP — up to 10 MB.</p>
            </div>
            <CameraDialog open={camOpen} onClose={() => setCamOpen(false)} onCapture={(blob) => { setCamOpen(false); uploadBlob(blob, "avatar.jpg"); }} />
        </div>
    );
}

function CameraDialog({ open, onClose, onCapture }) {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const streamRef = useRef(null);
    const [ready, setReady] = useState(false);
    const [facing, setFacing] = useState("user");
    const [err, setErr] = useState("");

    useEffect(() => {
        let cancelled = false;
        async function start() {
            setErr("");
            setReady(false);
            try {
                const constraints = { video: { facingMode: facing }, audio: false };
                const s = await navigator.mediaDevices.getUserMedia(constraints);
                if (cancelled) { s.getTracks().forEach((t) => t.stop()); return; }
                streamRef.current = s;
                if (videoRef.current) {
                    videoRef.current.srcObject = s;
                    await videoRef.current.play().catch(() => {});
                    setReady(true);
                }
            } catch (e) {
                setErr(e?.message || "Camera unavailable");
            }
        }
        if (open) start();
        return () => {
            cancelled = true;
            if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
        };
    }, [open, facing]);

    function capture() {
        if (!videoRef.current || !canvasRef.current) return;
        const v = videoRef.current;
        const c = canvasRef.current;
        c.width = v.videoWidth || 640;
        c.height = v.videoHeight || 480;
        const ctx = c.getContext("2d");
        ctx.drawImage(v, 0, 0, c.width, c.height);
        c.toBlob((blob) => { if (blob) onCapture(blob); }, "image/jpeg", 0.9);
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading">Take a new photo</DialogTitle></DialogHeader>
                {err ? (
                    <div className="text-sm text-destructive py-4" data-testid="avatar-cam-error">{err}</div>
                ) : (
                    <>
                        <div className="rounded-2xl overflow-hidden bg-black aspect-square w-full">
                            <video ref={videoRef} playsInline muted className="w-full h-full object-cover" data-testid="avatar-cam-video" />
                        </div>
                        <canvas ref={canvasRef} className="hidden" />
                        <div className="flex justify-between gap-2 mt-2">
                            <Button type="button" variant="outline" size="sm" className="rounded-full" onClick={() => setFacing((f) => (f === "user" ? "environment" : "user"))} data-testid="avatar-cam-flip">
                                <RefreshCw className="h-3.5 w-3.5 mr-1" /> Flip
                            </Button>
                            <Button type="button" size="sm" className="rounded-full bg-primary hover:bg-primary/90" onClick={capture} disabled={!ready} data-testid="avatar-cam-capture">
                                <Camera className="h-3.5 w-3.5 mr-1" /> Capture
                            </Button>
                        </div>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
}
