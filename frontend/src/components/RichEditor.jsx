import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import ResizableImage from "./ResizableImage";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import { useRef, useState, useEffect } from "react";
import { Bold, Italic, Underline, List, ListOrdered, Link2, Image as ImageIcon, Heading2, Quote, AlignLeft, AlignCenter, AlignRight, Undo, Redo } from "lucide-react";
import { api } from "../lib/api";
import { toast } from "sonner";

/**
 * <RichEditor value={html} onChange={(html)=>...} placeholder="..." minHeight={240} />
 * Used for email composer, templates, and signatures.
 */
export default function RichEditor({ value, onChange, placeholder = "Write your message…", minHeight = 240 }) {
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef(null);

    const editor = useEditor({
        extensions: [
            StarterKit.configure({ heading: { levels: [2, 3] } }),
            ResizableImage.configure({ inline: false, allowBase64: false }),
            Link.configure({ openOnClick: false, HTMLAttributes: { class: "underline text-primary" } }),
            Placeholder.configure({ placeholder }),
            TextAlign.configure({ types: ["heading", "paragraph"] }),
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

    if (!editor) return null;
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
                {btn(editor.isActive("strike"), () => editor.chain().focus().toggleStrike().run(), <Underline className="h-4 w-4" />, "fmt-strike", "Strikethrough")}
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
                {btn(false, () => editor.chain().focus().undo().run(), <Undo className="h-4 w-4" />, "fmt-undo", "Undo")}
                {btn(false, () => editor.chain().focus().redo().run(), <Redo className="h-4 w-4" />, "fmt-redo", "Redo")}
                {uploading && <span className="text-xs text-slate-500 ml-2">Uploading…</span>}
            </div>
            <EditorContent editor={editor} />
            <style>{`
                .tiptap p { margin: 0.5em 0; }
                .tiptap h2 { font-size: 1.4em; font-weight: 700; margin: 0.6em 0 0.3em; }
                .tiptap h3 { font-size: 1.2em; font-weight: 600; margin: 0.5em 0 0.3em; }
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
