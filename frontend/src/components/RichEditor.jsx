import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import ResizableImage from "./ResizableImage";
import EmailButton from "./EmailButton";
import EmailHorizontalRule from "./EmailHorizontalRule";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import { TextStyle, FontSize } from "@tiptap/extension-text-style";
import { Color } from "@tiptap/extension-color";
import { Highlight } from "@tiptap/extension-highlight";
import { Underline as UnderlineExt } from "@tiptap/extension-underline";
import { useRef, useState, useEffect } from "react";
import { Bold, Italic, Underline as UnderlineIcon, Strikethrough, List, ListOrdered, Link2, Image as ImageIcon, Heading2, Quote, AlignLeft, AlignCenter, AlignRight, Undo, Redo, MousePointerClick, Tag, Minus, Palette, Highlighter, Type } from "lucide-react";
import { api } from "../lib/api";
import { toast } from "sonner";

// Curated palette — high-contrast, brand-friendly. Users can also type
// any hex code in the free-form color input inside the popover.
const COLOR_SWATCHES = [
    "#0F172A", "#334155", "#64748B", "#94A3B8", "#CBD5E1", "#FFFFFF",
    "#C8102E", "#DC2626", "#EA580C", "#F59E0B", "#EAB308", "#84CC16",
    "#22C55E", "#10B981", "#0EA5E9", "#0284C7", "#2563EB", "#4F46E5",
    "#7C3AED", "#A855F7", "#EC4899", "#F43F5E", "#0A2463", "#78350F",
];
const HIGHLIGHT_SWATCHES = [
    "#FEF3C7", "#FDE68A", "#FCA5A5", "#FECACA", "#FED7AA", "#FBCFE8",
    "#DDD6FE", "#C7D2FE", "#BFDBFE", "#A7F3D0", "#D9F99D", "#F5F5F4",
];
const FONT_SIZES = [
    { label: "Small", value: "12px" },
    { label: "Normal", value: "16px" },
    { label: "Medium", value: "18px" },
    { label: "Large", value: "22px" },
    { label: "Huge", value: "28px" },
    { label: "Display", value: "36px" },
];

/**
 * <RichEditor value={html} onChange={(html)=>...} placeholder="..." minHeight={240} />
 * Used for email composer, templates, signatures, and news article body.
 */
export default function RichEditor({ value, onChange, placeholder = "Write your message…", minHeight = 240 }) {
    const [uploading, setUploading] = useState(false);
    const [mergeOpen, setMergeOpen] = useState(false);
    const [colorOpen, setColorOpen] = useState(false);
    const [highlightOpen, setHighlightOpen] = useState(false);
    const [sizeOpen, setSizeOpen] = useState(false);
    const fileInputRef = useRef(null);

    const editor = useEditor({
        extensions: [
            // StarterKit's default HR is replaced with our email-safe variant.
            StarterKit.configure({ heading: { levels: [2, 3] }, horizontalRule: false }),
            EmailHorizontalRule,
            ResizableImage.configure({ inline: false, allowBase64: false }),
            EmailButton,
            Link.configure({ openOnClick: false, HTMLAttributes: { class: "underline text-primary" } }),
            Placeholder.configure({ placeholder }),
            TextAlign.configure({ types: ["heading", "paragraph"] }),
            TextStyle,
            FontSize,
            Color,
            Highlight.configure({ multicolor: true }),
            UnderlineExt,
        ],
        content: value || "",
        onUpdate: ({ editor: ed }) => {
            onChange?.(ed.getHTML());
        },
        editorProps: {
            attributes: {
                class: "tiptap prose prose-sm max-w-none focus:outline-none px-4 py-3",
                style: `min-height: ${minHeight}px;`,
                "data-testid": "rich-editor-area",
            },
            handlePaste(view, event) {
                const items = event.clipboardData?.items;
                if (!items) return false;
                for (const it of items) {
                    if (it.kind === "file" && it.type.startsWith("image/")) {
                        event.preventDefault();
                        const file = it.getAsFile();
                        if (file) uploadAndInsert(file);
                        return true;
                    }
                }
                return false;
            },
            handleDrop(view, event) {
                const dt = event.dataTransfer;
                if (!dt?.files?.length) return false;
                const files = Array.from(dt.files).filter((f) => f.type.startsWith("image/"));
                if (!files.length) return false;
                event.preventDefault();
                files.forEach((f) => uploadAndInsert(f));
                return true;
            },
        },
    });

    // Keep editor in sync when parent resets `value` (e.g. picking a template)
    useEffect(() => {
        if (!editor) return;
        const current = editor.getHTML();
        if ((value || "") !== current) {
            editor.commands.setContent(value || "", false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value]);

    async function uploadAndInsert(file) {
        if (!file.type.startsWith("image/")) {
            toast.error("Only images are supported for inline insertion.");
            return;
        }
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/email/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
            const base = process.env.REACT_APP_BACKEND_URL || "";
            const fullUrl = data.url.startsWith("http") ? data.url : base + data.url;
            editor.chain().focus().setImage({ src: fullUrl, alt: data.filename, width: 400, align: "center" }).run();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Image upload failed");
        }
        setUploading(false);
    }

    function pickFile() {
        fileInputRef.current?.click();
    }

    function setLink() {
        const prev = editor.getAttributes("link").href;
        const url = window.prompt("Link URL", prev || "https://");
        if (url === null) return;
        if (url === "") { editor.chain().focus().extendMarkRange("link").unsetLink().run(); return; }
        editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    }

    // Insert an email-safe CTA button via our custom node — survives round-
    // tripping and inline styles are baked in at renderHTML time.
    function insertButton() {
        const label = window.prompt("Button label", "Learn more");
        if (!label) return;
        const url = window.prompt("Button link URL", "https://");
        if (!url) return;
        editor.chain().focus().insertContent({
            type: "emailButton",
            attrs: { label: label.trim(), href: url.trim(), align: "center" },
        }).run();
    }

    function insertMergeTag(tag) {
        // Backend already substitutes {{first_name}}, {{last_name}}, {{name}},
        // {{email}}, {{line_name}} at send time (see routes/email.py::357).
        editor.chain().focus().insertContent(`{{${tag}}}`).run();
        setMergeOpen(false);
    }

    function insertDivider() {
        editor.chain().focus().setHorizontalRule().run();
    }

    function applyColor(hex) {
        editor.chain().focus().setColor(hex).run();
        setColorOpen(false);
    }
    function clearColor() {
        editor.chain().focus().unsetColor().run();
        setColorOpen(false);
    }
    function applyHighlight(hex) {
        editor.chain().focus().setHighlight({ color: hex }).run();
        setHighlightOpen(false);
    }
    function clearHighlight() {
        editor.chain().focus().unsetHighlight().run();
        setHighlightOpen(false);
    }
    function applyFontSize(px) {
        editor.chain().focus().setFontSize(px).run();
        setSizeOpen(false);
    }

    if (!editor) return null;
    const currentColor = editor.getAttributes("textStyle").color || "";
    const currentHighlight = editor.getAttributes("highlight").color || "";
    const btn = (active, onClick, icon, testid, label) => (
        <button
            type="button"
            onClick={onClick}
            title={label}
            aria-label={label}
            data-testid={testid}
            className={`p-1.5 rounded-md hover:bg-slate-200 transition-colors ${active ? "bg-slate-200 text-primary" : "text-slate-600"}`}
        >
            {icon}
        </button>
    );

    return (
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden" data-testid="rich-editor">
            <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-slate-200 bg-slate-50 flex-wrap">
                {btn(editor.isActive("bold"), () => editor.chain().focus().toggleBold().run(), <Bold className="h-4 w-4" />, "fmt-bold", "Bold")}
                {btn(editor.isActive("italic"), () => editor.chain().focus().toggleItalic().run(), <Italic className="h-4 w-4" />, "fmt-italic", "Italic")}
                {btn(editor.isActive("underline"), () => editor.chain().focus().toggleUnderline().run(), <UnderlineIcon className="h-4 w-4" />, "fmt-underline", "Underline")}
                {btn(editor.isActive("strike"), () => editor.chain().focus().toggleStrike().run(), <Strikethrough className="h-4 w-4" />, "fmt-strike", "Strikethrough")}
                <div className="w-px h-5 bg-slate-200 mx-0.5" />
                {/* Font size dropdown */}
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setSizeOpen((v) => !v)}
                        onBlur={(e) => { if (!e.currentTarget.parentElement.contains(e.relatedTarget)) setSizeOpen(false); }}
                        title="Font size"
                        aria-label="Font size"
                        data-testid="fmt-size"
                        className={`p-1.5 rounded-md hover:bg-slate-200 transition-colors ${sizeOpen ? "bg-slate-200 text-primary" : "text-slate-600"} inline-flex items-center gap-1`}
                    >
                        <Type className="h-4 w-4" />
                        <span className="text-[10px] uppercase tracking-wider font-bold">Size</span>
                    </button>
                    {sizeOpen && (
                        <div className="absolute z-20 top-full left-0 mt-1 min-w-[140px] bg-white border border-slate-200 rounded-lg shadow-lg py-1 text-sm" data-testid="fmt-size-menu">
                            {FONT_SIZES.map((sz) => (
                                <button
                                    key={sz.value}
                                    type="button"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => applyFontSize(sz.value)}
                                    className="w-full text-left px-3 py-1.5 hover:bg-slate-50 flex items-center justify-between gap-3"
                                    data-testid={`fmt-size-${sz.value}`}
                                >
                                    <span style={{ fontSize: sz.value }}>{sz.label}</span>
                                    <code className="text-[10px] text-slate-400">{sz.value}</code>
                                </button>
                            ))}
                            <button
                                type="button"
                                onMouseDown={(e) => e.preventDefault()}
                                onClick={() => { editor.chain().focus().unsetFontSize().run(); setSizeOpen(false); }}
                                className="w-full text-left px-3 py-1.5 hover:bg-slate-50 text-slate-500 border-t border-slate-100 mt-1"
                                data-testid="fmt-size-reset"
                            >
                                Reset size
                            </button>
                        </div>
                    )}
                </div>
                {/* Font color popover */}
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setColorOpen((v) => !v)}
                        onBlur={(e) => { if (!e.currentTarget.parentElement.contains(e.relatedTarget)) setColorOpen(false); }}
                        title="Font color"
                        aria-label="Font color"
                        data-testid="fmt-color"
                        className={`p-1.5 rounded-md hover:bg-slate-200 transition-colors ${colorOpen ? "bg-slate-200 text-primary" : "text-slate-600"} inline-flex items-center gap-1`}
                    >
                        <Palette className="h-4 w-4" />
                        <span
                            className="inline-block h-3 w-3 rounded-full border border-slate-300"
                            style={{ backgroundColor: currentColor || "#0F172A" }}
                        />
                    </button>
                    {colorOpen && (
                        <div className="absolute z-20 top-full left-0 mt-1 w-56 bg-white border border-slate-200 rounded-lg shadow-lg p-2" data-testid="fmt-color-menu">
                            <div className="grid grid-cols-6 gap-1">
                                {COLOR_SWATCHES.map((c) => (
                                    <button
                                        key={c}
                                        type="button"
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => applyColor(c)}
                                        title={c}
                                        aria-label={`Color ${c}`}
                                        data-testid={`fmt-color-swatch-${c.replace("#", "").toLowerCase()}`}
                                        className="w-7 h-7 rounded-md border border-slate-200 hover:scale-110 transition-transform"
                                        style={{ backgroundColor: c }}
                                    />
                                ))}
                            </div>
                            <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                                <span>Custom</span>
                                <input
                                    type="color"
                                    onChange={(e) => applyColor(e.target.value)}
                                    className="h-6 w-8 cursor-pointer bg-transparent"
                                    data-testid="fmt-color-custom"
                                />
                                <button
                                    type="button"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={clearColor}
                                    className="ml-auto text-xs px-2 py-1 rounded hover:bg-slate-100 text-slate-500"
                                    data-testid="fmt-color-clear"
                                >
                                    Clear
                                </button>
                            </label>
                        </div>
                    )}
                </div>
                {/* Text-background / highlight popover */}
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setHighlightOpen((v) => !v)}
                        onBlur={(e) => { if (!e.currentTarget.parentElement.contains(e.relatedTarget)) setHighlightOpen(false); }}
                        title="Text highlight color"
                        aria-label="Text highlight color"
                        data-testid="fmt-highlight"
                        className={`p-1.5 rounded-md hover:bg-slate-200 transition-colors ${highlightOpen ? "bg-slate-200 text-primary" : "text-slate-600"} inline-flex items-center gap-1`}
                    >
                        <Highlighter className="h-4 w-4" />
                        <span
                            className="inline-block h-3 w-3 rounded-full border border-slate-300"
                            style={{ backgroundColor: currentHighlight || "#FEF3C7" }}
                        />
                    </button>
                    {highlightOpen && (
                        <div className="absolute z-20 top-full left-0 mt-1 w-56 bg-white border border-slate-200 rounded-lg shadow-lg p-2" data-testid="fmt-highlight-menu">
                            <div className="grid grid-cols-6 gap-1">
                                {HIGHLIGHT_SWATCHES.map((c) => (
                                    <button
                                        key={c}
                                        type="button"
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => applyHighlight(c)}
                                        title={c}
                                        aria-label={`Highlight ${c}`}
                                        data-testid={`fmt-highlight-swatch-${c.replace("#", "").toLowerCase()}`}
                                        className="w-7 h-7 rounded-md border border-slate-200 hover:scale-110 transition-transform"
                                        style={{ backgroundColor: c }}
                                    />
                                ))}
                            </div>
                            <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                                <span>Custom</span>
                                <input
                                    type="color"
                                    onChange={(e) => applyHighlight(e.target.value)}
                                    className="h-6 w-8 cursor-pointer bg-transparent"
                                    data-testid="fmt-highlight-custom"
                                />
                                <button
                                    type="button"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={clearHighlight}
                                    className="ml-auto text-xs px-2 py-1 rounded hover:bg-slate-100 text-slate-500"
                                    data-testid="fmt-highlight-clear"
                                >
                                    Clear
                                </button>
                            </label>
                        </div>
                    )}
                </div>
                <div className="w-px h-5 bg-slate-200 mx-0.5" />
                {btn(editor.isActive("heading", { level: 2 }), () => editor.chain().focus().toggleHeading({ level: 2 }).run(), <Heading2 className="h-4 w-4" />, "fmt-h2", "Heading")}
                {btn(editor.isActive("blockquote"), () => editor.chain().focus().toggleBlockquote().run(), <Quote className="h-4 w-4" />, "fmt-quote", "Quote")}
                {btn(editor.isActive("bulletList"), () => editor.chain().focus().toggleBulletList().run(), <List className="h-4 w-4" />, "fmt-ul", "Bullet list")}
                {btn(editor.isActive("orderedList"), () => editor.chain().focus().toggleOrderedList().run(), <ListOrdered className="h-4 w-4" />, "fmt-ol", "Numbered list")}
                <div className="w-px h-5 bg-slate-200 mx-0.5" />
                {btn(editor.isActive({ textAlign: "left" }), () => editor.chain().focus().setTextAlign("left").run(), <AlignLeft className="h-4 w-4" />, "fmt-align-left", "Align left")}
                {btn(editor.isActive({ textAlign: "center" }), () => editor.chain().focus().setTextAlign("center").run(), <AlignCenter className="h-4 w-4" />, "fmt-align-center", "Align center")}
                {btn(editor.isActive({ textAlign: "right" }), () => editor.chain().focus().setTextAlign("right").run(), <AlignRight className="h-4 w-4" />, "fmt-align-right", "Align right")}
                <div className="w-px h-5 bg-slate-200 mx-0.5" />
                {btn(editor.isActive("link"), setLink, <Link2 className="h-4 w-4" />, "fmt-link", "Insert link")}
                {btn(false, pickFile, <ImageIcon className="h-4 w-4" />, "fmt-image", "Insert image (or drag/paste)")}
                <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => {
                    const f = e.target.files?.[0]; if (f) uploadAndInsert(f); e.target.value = "";
                }} />
                <div className="w-px h-5 bg-slate-200 mx-0.5" />
                {btn(false, insertButton, <MousePointerClick className="h-4 w-4" />, "fmt-button", "Insert CTA button with link")}
                {btn(false, insertDivider, <Minus className="h-4 w-4" />, "fmt-divider", "Insert divider")}
                {/* Merge tags dropdown — inserts a {{token}} the backend substitutes at send time. */}
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setMergeOpen((v) => !v)}
                        onBlur={(e) => { if (!e.currentTarget.parentElement.contains(e.relatedTarget)) setMergeOpen(false); }}
                        title="Insert personalization tag"
                        aria-label="Insert personalization tag"
                        data-testid="fmt-merge"
                        className={`p-1.5 rounded-md hover:bg-slate-200 transition-colors ${mergeOpen ? "bg-slate-200 text-primary" : "text-slate-600"} inline-flex items-center gap-1`}
                    >
                        <Tag className="h-4 w-4" />
                        <span className="text-[10px] uppercase tracking-wider font-bold">Merge</span>
                    </button>
                    {mergeOpen && (
                        <div className="absolute z-20 top-full left-0 mt-1 min-w-[200px] bg-white border border-slate-200 rounded-lg shadow-lg py-1 text-sm" data-testid="fmt-merge-menu">
                            {[
                                { key: "first_name", label: "First name", example: "Sarah" },
                                { key: "last_name", label: "Last name", example: "Chen" },
                                { key: "name", label: "Full name", example: "Sarah Chen" },
                                { key: "email", label: "Email", example: "sarah@example.com" },
                                { key: "line_name", label: "Line name", example: "Alpha Line" },
                            ].map((t) => (
                                <button
                                    key={t.key}
                                    type="button"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => insertMergeTag(t.key)}
                                    className="w-full text-left px-3 py-1.5 hover:bg-slate-50 flex items-center justify-between gap-3"
                                    data-testid={`fmt-merge-${t.key}`}
                                >
                                    <span className="font-medium text-slate-700">{t.label}</span>
                                    <code className="text-[10px] text-slate-400">{`{{${t.key}}}`}</code>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                <div className="w-px h-5 bg-slate-200 mx-0.5" />
                {btn(false, () => editor.chain().focus().undo().run(), <Undo className="h-4 w-4" />, "fmt-undo", "Undo")}
                {btn(false, () => editor.chain().focus().redo().run(), <Redo className="h-4 w-4" />, "fmt-redo", "Redo")}
                {uploading && <span className="text-xs text-slate-500 ml-2">Uploading…</span>}
            </div>
            <EditorContent editor={editor} />
            <style>{`
                .tiptap p { margin: 0.5em 0; }
                .tiptap h2 { font-size: 1.4em; font-weight: 700; margin: 0.6em 0 0.3em; }
                .tiptap h3 { font-size: 1.2em; font-weight: 600; margin: 0.5em 0 0.3em; }
                .tiptap u { text-decoration: underline; }
                .tiptap mark { padding: 0 2px; border-radius: 2px; }
                .tiptap blockquote { border-left: 3px solid #C8102E; padding-left: 1em; margin: 0.6em 0; color: #475569; }
                .tiptap ul, .tiptap ol { padding-left: 1.5em; margin: 0.5em 0; }
                .tiptap img { max-width: 100%; height: auto; }
                .tiptap p.is-editor-empty:first-child::before {
                    content: attr(data-placeholder);
                    float: left; color: #94a3b8; pointer-events: none; height: 0;
                }
            `}</style>
        </div>
    );
}
