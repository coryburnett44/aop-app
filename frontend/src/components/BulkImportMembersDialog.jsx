import { useState, useRef } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "./ui/select";
import { Upload, Download, CheckCircle2, AlertTriangle, XCircle, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";

/**
 * Bulk-import members from a CSV (typically a ClubExpress roster export).
 *
 * Flow:
 *   1. Admin downloads the template (gets all expected headers + 1 example row).
 *   2. Admin pastes their roster into the template and uploads.
 *   3. Server reads each row, creates one user. membership_expires_at is set
 *      to renewal_date + 365 days (per row).
 *   4. Result panel shows created / skipped / errors with row numbers so the
 *      admin can fix and re-upload.
 *
 * A "Dry run" toggle validates the file without inserting any users — useful
 * for sanity-checking a large file before committing.
 */
export default function BulkImportMembersDialog({ chapters = [], onImported }) {
    const [open, setOpen] = useState(false);
    const [file, setFile] = useState(null);
    const [defaultChapter, setDefaultChapter] = useState("");
    const [dryRun, setDryRun] = useState(true);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const fileRef = useRef(null);

    async function downloadTemplate() {
        try {
            const res = await api.get("/admin/members/bulk-import/template", { responseType: "blob" });
            const url = URL.createObjectURL(res.data);
            const a = document.createElement("a");
            a.href = url;
            a.download = "aop-bulk-import-template.csv";
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
        } catch (e) {
            toast.error("Could not download template");
        }
    }

    async function submit() {
        if (!file) { toast.error("Choose a CSV file first"); return; }
        setBusy(true);
        setResult(null);
        try {
            const fd = new FormData();
            fd.append("file", file);
            if (defaultChapter) fd.append("default_chapter_id", defaultChapter);
            fd.append("dry_run", dryRun ? "true" : "false");
            const { data } = await api.post("/admin/members/bulk-import", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setResult(data);
            if (dryRun) {
                toast.success(`Dry run: ${data.created_count} would be created, ${data.skipped_count} skipped, ${data.error_count} errors`);
            } else {
                toast.success(`Imported ${data.created_count} members 🎉`);
                onImported?.();
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || "Import failed");
        }
        setBusy(false);
    }

    function reset() {
        setFile(null);
        setResult(null);
        setDryRun(true);
        if (fileRef.current) fileRef.current.value = "";
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
            <DialogTrigger asChild>
                <Button variant="outline" className="rounded-full" data-testid="bulk-import-open-btn">
                    <Upload className="h-4 w-4 mr-1.5" /> Bulk import CSV
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="bulk-import-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl flex items-center gap-2">
                        <FileSpreadsheet className="h-6 w-6 text-primary" /> Bulk-import members
                    </DialogTitle>
                    <DialogDescription>
                        Upload a CSV (e.g. exported from ClubExpress). One user per row. Membership expiry is set to <strong>Renewal Date + 365 days</strong>.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 mt-2">
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-900 leading-relaxed">
                        <strong>Tip:</strong> Download the template first to see exactly which columns are accepted.
                        Aliases like <code>FirstName</code>, <code>First Name</code>, or <code>First</code> all work.
                        Duplicate emails are skipped (never overwritten).
                    </div>

                    <div className="flex gap-2">
                        <Button type="button" variant="outline" onClick={downloadTemplate} className="rounded-full" data-testid="bulk-import-download-template">
                            <Download className="h-4 w-4 mr-1.5" /> Download template
                        </Button>
                    </div>

                    <div>
                        <Label>CSV file</Label>
                        <input
                            ref={fileRef}
                            type="file"
                            accept=".csv,text/csv"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            className="mt-1.5 block w-full text-sm file:rounded-full file:border-0 file:bg-primary file:text-white file:px-4 file:py-2 file:mr-3 file:font-semibold hover:file:bg-primary/90"
                            data-testid="bulk-import-file"
                        />
                        {file && (
                            <div className="text-xs text-muted-foreground mt-1.5">
                                Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                            </div>
                        )}
                    </div>

                    <div className="grid sm:grid-cols-2 gap-4">
                        <div>
                            <Label>Default chapter <span className="text-xs text-muted-foreground font-normal">(optional)</span></Label>
                            <Select value={defaultChapter || "__none__"} onValueChange={(v) => setDefaultChapter(v === "__none__" ? "" : v)}>
                                <SelectTrigger className="rounded-xl mt-1.5" data-testid="bulk-import-default-chapter"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__none__">— None —</SelectItem>
                                    {chapters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <p className="text-[11px] text-muted-foreground mt-1.5">Used when a row has no "Chapter" column or it doesn't match any existing chapter name.</p>
                        </div>
                        <div>
                            <Label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={dryRun}
                                    onChange={(e) => setDryRun(e.target.checked)}
                                    className="h-4 w-4 rounded border-2 border-slate-300 accent-primary"
                                    data-testid="bulk-import-dry-run"
                                />
                                <span className="text-sm font-medium">Dry run (preview only — no users created)</span>
                            </Label>
                            <p className="text-[11px] text-muted-foreground mt-3">Recommended for your first upload. Uncheck after verifying the preview looks right.</p>
                        </div>
                    </div>

                    {result && (
                        <div className="space-y-3 mt-2 border-t pt-4" data-testid="bulk-import-result">
                            <div className="flex flex-wrap gap-3">
                                <div className="flex-1 min-w-[120px] rounded-xl border-2 border-emerald-300 bg-emerald-50 p-3 text-center" data-testid="bulk-import-created">
                                    <div className="flex items-center justify-center gap-1.5 text-emerald-700 text-xs font-bold uppercase tracking-wider">
                                        <CheckCircle2 className="h-3.5 w-3.5" /> {result.dry_run ? "Would create" : "Created"}
                                    </div>
                                    <div className="font-heading text-3xl font-black text-emerald-800 mt-1">{result.created_count}</div>
                                </div>
                                <div className="flex-1 min-w-[120px] rounded-xl border-2 border-amber-300 bg-amber-50 p-3 text-center" data-testid="bulk-import-skipped">
                                    <div className="flex items-center justify-center gap-1.5 text-amber-700 text-xs font-bold uppercase tracking-wider">
                                        <AlertTriangle className="h-3.5 w-3.5" /> Skipped
                                    </div>
                                    <div className="font-heading text-3xl font-black text-amber-800 mt-1">{result.skipped_count}</div>
                                </div>
                                <div className="flex-1 min-w-[120px] rounded-xl border-2 border-rose-300 bg-rose-50 p-3 text-center" data-testid="bulk-import-errors">
                                    <div className="flex items-center justify-center gap-1.5 text-rose-700 text-xs font-bold uppercase tracking-wider">
                                        <XCircle className="h-3.5 w-3.5" /> Errors
                                    </div>
                                    <div className="font-heading text-3xl font-black text-rose-800 mt-1">{result.error_count}</div>
                                </div>
                            </div>

                            {result.errors?.length > 0 && (
                                <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3 text-xs">
                                    <div className="font-bold text-rose-800 mb-1.5">Errors</div>
                                    <ul className="space-y-0.5 text-rose-900">
                                        {result.errors.slice(0, 10).map((r, i) => (
                                            <li key={i}>Row {r.row}{r.email ? ` (${r.email})` : ""}: {r.reason}</li>
                                        ))}
                                        {result.errors.length > 10 && <li className="opacity-70">…and {result.errors.length - 10} more</li>}
                                    </ul>
                                </div>
                            )}

                            {result.skipped?.length > 0 && (
                                <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 text-xs">
                                    <div className="font-bold text-amber-800 mb-1.5">Skipped (duplicates)</div>
                                    <ul className="space-y-0.5 text-amber-900">
                                        {result.skipped.slice(0, 10).map((r, i) => (
                                            <li key={i}>Row {r.row}: {r.email}</li>
                                        ))}
                                        {result.skipped.length > 10 && <li className="opacity-70">…and {result.skipped.length - 10} more</li>}
                                    </ul>
                                </div>
                            )}

                            {result.dry_run && result.created_count > 0 && (
                                <div className="rounded-xl border-2 border-primary/40 bg-primary/5 p-3 text-xs">
                                    <strong className="text-primary">Looks good!</strong> Uncheck "Dry run" above and click <em>Import</em> again to actually create these {result.created_count} members.
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <DialogFooter className="mt-3">
                    <Button type="button" variant="outline" onClick={() => setOpen(false)} className="rounded-full">Close</Button>
                    <Button
                        onClick={submit}
                        disabled={busy || !file}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid="bulk-import-submit-btn"
                    >
                        {busy ? "Working…" : dryRun ? "Run preview" : "Import members"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
