import { useState } from "react";
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
} from "@dnd-kit/core";
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
    Heading1,
    Heading2,
    AlignLeft,
    Image as ImageIcon,
    MousePointerClick,
    Minus,
    SeparatorHorizontal,
    Code2,
    Columns3,
    Youtube,
    GripVertical,
    Trash2,
    Eye,
    EyeOff,
    Plus,
} from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { BlockRenderer } from "./BlockRenderer";
import { api } from "../../lib/api";
import { toast } from "sonner";

const BLOCK_TEMPLATES = [
    { type: "heading", icon: Heading1, label: "Heading", defaults: { text: "New Heading", align: "left", color: "#0A2463" } },
    { type: "subheading", icon: Heading2, label: "Sub-heading", defaults: { text: "New sub-heading", align: "left", color: "#0A2463" } },
    { type: "paragraph", icon: AlignLeft, label: "Paragraph", defaults: { text: "Type your paragraph text here…", align: "left" } },
    { type: "image", icon: ImageIcon, label: "Image", defaults: { url: "", alt: "", caption: "" } },
    { type: "button", icon: MousePointerClick, label: "Button", defaults: { label: "Click here", href: "#", color: "#C8102E", align: "left", target: "_self" } },
    { type: "columns", icon: Columns3, label: "Columns (cards)", defaults: { cols: 3, items: [{ title: "Card 1", body: "" }, { title: "Card 2", body: "" }, { title: "Card 3", body: "" }] } },
    { type: "video", icon: Youtube, label: "Video embed", defaults: { url: "", title: "Video" } },
    { type: "divider", icon: Minus, label: "Divider", defaults: { color: "#0A2463" } },
    { type: "spacer", icon: SeparatorHorizontal, label: "Spacer", defaults: { height: 40 } },
    { type: "html", icon: Code2, label: "HTML embed", defaults: { html: "<p>Custom HTML…</p>" } },
];

function newId() { return `b_${Math.random().toString(36).slice(2, 10)}`; }

function uploadAndGetUrl(file) {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/email/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } })
        .then(({ data }) => data.url);
}

function BlockEditor({ block, onChange, onRemove }) {
    const p = block.props || {};
    const set = (k, v) => onChange({ ...block, props: { ...p, [k]: v } });

    async function handleImageUpload(e) {
        const f = e.target.files?.[0];
        if (!f) return;
        try {
            const url = await uploadAndGetUrl(f);
            set("url", url);
            toast.success("Image uploaded");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Upload failed");
        }
    }

    switch (block.type) {
        case "heading":
        case "subheading":
            return (
                <div className="grid sm:grid-cols-[1fr_140px_120px] gap-2">
                    <Input value={p.text || ""} onChange={(e) => set("text", e.target.value)} placeholder="Text" className="rounded-xl" />
                    <select value={p.align || "left"} onChange={(e) => set("align", e.target.value)} className="rounded-xl border px-3 text-sm">
                        <option value="left">Left</option>
                        <option value="center">Center</option>
                        <option value="right">Right</option>
                    </select>
                    <Input type="color" value={p.color || "#0A2463"} onChange={(e) => set("color", e.target.value)} className="rounded-xl h-10" />
                </div>
            );
        case "paragraph":
            return (
                <div className="space-y-2">
                    <Textarea rows={3} value={p.text || ""} onChange={(e) => set("text", e.target.value)} placeholder="Paragraph text…" className="rounded-xl" />
                    <select value={p.align || "left"} onChange={(e) => set("align", e.target.value)} className="rounded-xl border px-3 py-2 text-sm">
                        <option value="left">Align left</option>
                        <option value="center">Align center</option>
                        <option value="right">Align right</option>
                    </select>
                </div>
            );
        case "image":
            return (
                <div className="space-y-2">
                    <div className="flex gap-2">
                        <Input value={p.url || ""} onChange={(e) => set("url", e.target.value)} placeholder="Image URL or /api/files/…" className="rounded-xl flex-1" />
                        <label className="rounded-xl border px-3 py-2 text-xs cursor-pointer hover:bg-slate-50">
                            Upload<input type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
                        </label>
                    </div>
                    <Input value={p.alt || ""} onChange={(e) => set("alt", e.target.value)} placeholder="Alt text (accessibility)" className="rounded-xl" />
                    <Input value={p.caption || ""} onChange={(e) => set("caption", e.target.value)} placeholder="Caption (optional)" className="rounded-xl" />
                </div>
            );
        case "button":
            return (
                <div className="grid sm:grid-cols-2 gap-2">
                    <Input value={p.label || ""} onChange={(e) => set("label", e.target.value)} placeholder="Button label" className="rounded-xl" />
                    <Input value={p.href || ""} onChange={(e) => set("href", e.target.value)} placeholder="https://… or /route" className="rounded-xl" />
                    <select value={p.align || "left"} onChange={(e) => set("align", e.target.value)} className="rounded-xl border px-3 py-2 text-sm">
                        <option value="left">Align left</option>
                        <option value="center">Align center</option>
                        <option value="right">Align right</option>
                    </select>
                    <div className="flex gap-2 items-center">
                        <Input type="color" value={p.color || "#C8102E"} onChange={(e) => set("color", e.target.value)} className="rounded-xl h-10 w-24" />
                        <select value={p.target || "_self"} onChange={(e) => set("target", e.target.value)} className="rounded-xl border px-2 py-2 text-sm flex-1">
                            <option value="_self">Same tab</option>
                            <option value="_blank">New tab</option>
                        </select>
                    </div>
                </div>
            );
        case "divider":
            return <Input type="color" value={p.color || "#0A2463"} onChange={(e) => set("color", e.target.value)} className="rounded-xl h-10 w-32" />;
        case "spacer":
            return (
                <div className="flex items-center gap-3">
                    <Label className="text-xs">Height (px)</Label>
                    <Input type="number" min={4} max={400} value={p.height || 40} onChange={(e) => set("height", parseInt(e.target.value) || 40)} className="rounded-xl w-32" />
                </div>
            );
        case "html":
            return <Textarea rows={5} value={p.html || ""} onChange={(e) => set("html", e.target.value)} placeholder="<p>raw HTML</p>" className="rounded-xl font-mono text-xs" />;
        case "video":
            return (
                <div className="space-y-2">
                    <Input value={p.url || ""} onChange={(e) => set("url", e.target.value)} placeholder="https://www.youtube.com/embed/VIDEOID" className="rounded-xl" />
                    <p className="text-[11px] text-slate-500">Tip: use the YouTube embed URL (Share → Embed → copy iframe src).</p>
                </div>
            );
        case "columns": {
            const items = p.items || [];
            const setItem = (idx, k, v) => set("items", items.map((it, i) => i === idx ? { ...it, [k]: v } : it));
            const addItem = () => set("items", [...items, { title: "", body: "" }]);
            const removeItem = (idx) => set("items", items.filter((_, i) => i !== idx));
            return (
                <div className="space-y-2">
                    <div className="flex items-center gap-2 mb-2">
                        <Label className="text-xs">Columns</Label>
                        <select value={p.cols || 3} onChange={(e) => set("cols", parseInt(e.target.value))} className="rounded-xl border px-2 py-1 text-sm">
                            <option value={2}>2</option>
                            <option value={3}>3</option>
                            <option value={4}>4</option>
                        </select>
                    </div>
                    {items.map((it, idx) => (
                        <div key={idx} className="border border-slate-200 rounded-xl p-3 space-y-2 bg-slate-50">
                            <div className="flex gap-2 items-center">
                                <Input value={it.title || ""} onChange={(e) => setItem(idx, "title", e.target.value)} placeholder={`Card ${idx + 1} title`} className="rounded-xl" />
                                <Button variant="ghost" size="icon" onClick={() => removeItem(idx)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                            </div>
                            <Textarea rows={2} value={it.body || ""} onChange={(e) => setItem(idx, "body", e.target.value)} placeholder="Card body" className="rounded-xl text-sm" />
                            <Input value={it.image || ""} onChange={(e) => setItem(idx, "image", e.target.value)} placeholder="Image URL (optional)" className="rounded-xl text-sm" />
                        </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addItem} className="rounded-full"><Plus className="h-3 w-3 mr-1" />Add card</Button>
                </div>
            );
        }
        default:
            return <div className="text-xs text-slate-500">No editor</div>;
    }
}

function SortableBlock({ block, onChange, onRemove, expanded, onToggle }) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: block.id });
    const tmpl = BLOCK_TEMPLATES.find((t) => t.type === block.type);
    const Icon = tmpl?.icon || AlignLeft;
    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
    };
    return (
        <div ref={setNodeRef} style={style} className="bg-white border-2 border-slate-200 rounded-xl overflow-hidden" data-testid={`block-row-${block.id}`}>
            <div className="flex items-center gap-2 p-3 bg-slate-50 border-b border-slate-200">
                <button type="button" {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing text-slate-400 hover:text-slate-700" data-testid={`block-drag-${block.id}`}>
                    <GripVertical className="h-4 w-4" />
                </button>
                <Icon className="h-4 w-4 text-slate-600" />
                <div className="text-sm font-semibold flex-1 truncate text-slate-700">{tmpl?.label || block.type}</div>
                <Button variant="ghost" size="icon" onClick={onToggle} data-testid={`block-toggle-${block.id}`}>
                    {expanded ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button variant="ghost" size="icon" onClick={onRemove} data-testid={`block-remove-${block.id}`}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
            </div>
            {expanded && (
                <div className="p-3 space-y-3">
                    <BlockEditor block={block} onChange={onChange} onRemove={onRemove} />
                    <div className="border-t border-dashed pt-3">
                        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 mb-2">Preview</div>
                        <div className="bg-slate-50 rounded-xl p-3">
                            <BlockRenderer block={block} />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default function PageBuilder({ blocks, onChange, testIdPrefix = "page-builder" }) {
    const [expandedId, setExpandedId] = useState(null);
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
    );

    function addBlock(type) {
        const tmpl = BLOCK_TEMPLATES.find((t) => t.type === type);
        const block = { id: newId(), type, props: { ...(tmpl?.defaults || {}) } };
        onChange([...(blocks || []), block]);
        setExpandedId(block.id);
    }
    function updateBlock(updated) {
        onChange(blocks.map((b) => (b.id === updated.id ? updated : b)));
    }
    function removeBlock(id) {
        onChange(blocks.filter((b) => b.id !== id));
        if (expandedId === id) setExpandedId(null);
    }
    function handleDragEnd(event) {
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        const oldIndex = blocks.findIndex((b) => b.id === active.id);
        const newIndex = blocks.findIndex((b) => b.id === over.id);
        onChange(arrayMove(blocks, oldIndex, newIndex));
    }

    return (
        <div className="grid lg:grid-cols-[200px_1fr] gap-4" data-testid={testIdPrefix}>
            {/* Block palette */}
            <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Add a block</div>
                {BLOCK_TEMPLATES.map(({ type, icon: Icon, label }) => (
                    <button
                        key={type}
                        type="button"
                        onClick={() => addBlock(type)}
                        className="w-full flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-[#0A2463] hover:shadow-sm transition-all text-left text-sm"
                        data-testid={`add-block-${type}`}
                    >
                        <Icon className="h-4 w-4 text-[#0A2463]" />
                        <span className="font-medium">{label}</span>
                    </button>
                ))}
            </div>

            {/* Block stack */}
            <div className="space-y-2 min-h-[200px]">
                {(blocks || []).length === 0 ? (
                    <div className="text-center text-sm text-slate-500 py-12 border-2 border-dashed border-slate-300 rounded-xl">
                        No blocks yet. Click a block type on the left to add one.
                    </div>
                ) : (
                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                        <SortableContext items={blocks.map((b) => b.id)} strategy={verticalListSortingStrategy}>
                            {blocks.map((b) => (
                                <SortableBlock
                                    key={b.id}
                                    block={b}
                                    expanded={expandedId === b.id}
                                    onToggle={() => setExpandedId(expandedId === b.id ? null : b.id)}
                                    onChange={updateBlock}
                                    onRemove={() => removeBlock(b.id)}
                                />
                            ))}
                        </SortableContext>
                    </DndContext>
                )}
            </div>
        </div>
    );
}
