import Image from "@tiptap/extension-image";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import { useRef, useState } from "react";
import { AlignLeft, AlignCenter, AlignRight, Trash2, Link2 } from "lucide-react";

/**
 * ResizableImage — TipTap image node with:
 *   • Drag handles on all 4 corners for visual resize
 *   • Floating toolbar (align L/C/R + size presets S/M/L/Full + remove)
 *   • Inline-style HTML output (no CSS classes) so emails render correctly
 *     in Gmail/Outlook/Apple Mail.
 *
 * Rendered HTML shape:
 *   <div data-image-align="center" style="text-align:center;margin:8px 0">
 *     <img src="..." alt="..." width="400"
 *          style="max-width:100%;height:auto;display:inline-block;border-radius:8px;width:400px" />
 *   </div>
 */

const ALIGN_TO_FLEX = { left: "flex-start", center: "center", right: "flex-end" };

function ResizableImageView({ node, updateAttributes, selected, deleteNode, editor }) {
    const { src, alt, width, align, link } = node.attrs;
    const imgRef = useRef(null);
    const [hovered, setHovered] = useState(false);
    const isEditable = editor?.isEditable !== false;
    const showChrome = selected && isEditable;

    function startResize(e, corner) {
        e.preventDefault();
        e.stopPropagation();
        const startX = e.clientX;
        const startWidth = imgRef.current?.offsetWidth || width || 400;
        const isLeft = corner.endsWith("l");
        const onMove = (ev) => {
            const dx = ev.clientX - startX;
            const newW = Math.max(60, Math.min(1200, Math.round(startWidth + (isLeft ? -dx : dx))));
            updateAttributes({ width: newW });
        };
        const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
    }

    const setSize = (w) => updateAttributes({ width: w });
    const setAlign = (a) => updateAttributes({ align: a });
    function editLink() {
        const next = window.prompt("Link URL for this image (leave empty to remove)", link || "https://");
        if (next === null) return;
        updateAttributes({ link: next.trim() || null });
    }

    const wrapperStyle = {
        display: "flex",
        justifyContent: ALIGN_TO_FLEX[align] || "flex-start",
        margin: "8px 0",
    };
    const imgStyle = {
        width: width ? `${width}px` : "100%",
        maxWidth: "100%",
        height: "auto",
        display: "inline-block",
        borderRadius: 8,
        outline: showChrome ? "2px solid #3b82f6" : (hovered && isEditable ? "2px dashed #93c5fd" : "2px solid transparent"),
        outlineOffset: 2,
        cursor: isEditable ? "pointer" : "default",
    };
    const handleBase = {
        position: "absolute",
        width: 12,
        height: 12,
        background: "#3b82f6",
        border: "2px solid white",
        borderRadius: "50%",
        zIndex: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,.4)",
    };

    return (
        <NodeViewWrapper
            as="div"
            data-image-align={align || "left"}
            data-testid="ri-wrapper"
            style={wrapperStyle}
            contentEditable={false}
        >
            <div
                style={{ position: "relative", display: "inline-block", maxWidth: "100%" }}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
            >
                <img
                    ref={imgRef}
                    src={src}
                    alt={alt || ""}
                    style={imgStyle}
                    draggable={false}
                    data-testid="ri-image"
                />
                {showChrome && (
                    <>
                        {[
                            { c: "tl", style: { top: -6, left: -6, cursor: "nwse-resize" } },
                            { c: "tr", style: { top: -6, right: -6, cursor: "nesw-resize" } },
                            { c: "bl", style: { bottom: -6, left: -6, cursor: "nesw-resize" } },
                            { c: "br", style: { bottom: -6, right: -6, cursor: "nwse-resize" } },
                        ].map(({ c, style }) => (
                            <span
                                key={c}
                                onMouseDown={(e) => startResize(e, c)}
                                style={{ ...handleBase, ...style }}
                                data-testid={`ri-handle-${c}`}
                                aria-label={`Resize handle ${c}`}
                            />
                        ))}
                        <div
                            data-testid="ri-toolbar"
                            style={{
                                position: "absolute",
                                top: -42,
                                left: 0,
                                background: "#0f172a",
                                color: "white",
                                borderRadius: 8,
                                padding: "4px 6px",
                                display: "flex",
                                gap: 2,
                                fontSize: 11,
                                alignItems: "center",
                                zIndex: 11,
                                whiteSpace: "nowrap",
                                boxShadow: "0 4px 16px rgba(0,0,0,.25)",
                            }}
                        >
                            <ToolbarBtn active={align === "left"} onClick={() => setAlign("left")} testid="ri-align-left" label="Align left"><AlignLeft className="h-3.5 w-3.5" /></ToolbarBtn>
                            <ToolbarBtn active={align === "center"} onClick={() => setAlign("center")} testid="ri-align-center" label="Align center"><AlignCenter className="h-3.5 w-3.5" /></ToolbarBtn>
                            <ToolbarBtn active={align === "right"} onClick={() => setAlign("right")} testid="ri-align-right" label="Align right"><AlignRight className="h-3.5 w-3.5" /></ToolbarBtn>
                            <span style={{ width: 1, height: 14, background: "#475569", margin: "0 4px" }} />
                            <ToolbarBtn active={width === 200} onClick={() => setSize(200)} testid="ri-size-s" label="Small">S</ToolbarBtn>
                            <ToolbarBtn active={width === 400} onClick={() => setSize(400)} testid="ri-size-m" label="Medium">M</ToolbarBtn>
                            <ToolbarBtn active={width === 600} onClick={() => setSize(600)} testid="ri-size-l" label="Large">L</ToolbarBtn>
                            <ToolbarBtn active={!width} onClick={() => setSize(null)} testid="ri-size-full" label="Full width">Full</ToolbarBtn>
                            <span style={{ width: 1, height: 14, background: "#475569", margin: "0 4px" }} />
                            <ToolbarBtn active={!!link} onClick={editLink} testid="ri-link" label={link ? `Linked to ${link}` : "Add link"}><Link2 className="h-3.5 w-3.5" /></ToolbarBtn>
                            <span style={{ width: 1, height: 14, background: "#475569", margin: "0 4px" }} />
                            <ToolbarBtn onClick={() => deleteNode()} danger testid="ri-remove" label="Remove image"><Trash2 className="h-3.5 w-3.5" /></ToolbarBtn>
                        </div>
                        {width && (
                            <div
                                style={{
                                    position: "absolute",
                                    bottom: -22,
                                    right: 0,
                                    background: "rgba(15,23,42,.85)",
                                    color: "white",
                                    fontSize: 10,
                                    padding: "1px 6px",
                                    borderRadius: 4,
                                    fontVariantNumeric: "tabular-nums",
                                }}
                                data-testid="ri-width-label"
                            >
                                {width}px
                            </div>
                        )}
                    </>
                )}
            </div>
        </NodeViewWrapper>
    );
}

function ToolbarBtn({ children, onClick, active, danger, testid, label }) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-label={label}
            title={label}
            data-testid={testid}
            style={{
                background: active ? "#3b82f6" : "transparent",
                color: danger ? "#fca5a5" : "white",
                border: "none",
                padding: "3px 8px",
                borderRadius: 4,
                cursor: "pointer",
                fontWeight: 600,
                fontSize: 11,
                display: "inline-flex",
                alignItems: "center",
                gap: 2,
            }}
        >
            {children}
        </button>
    );
}

const ResizableImage = Image.extend({
    name: "image",
    draggable: true,
    selectable: true,
    atom: true,

    addAttributes() {
        return {
            ...this.parent?.(),
            width: {
                default: null,
                parseHTML: (el) => {
                    const w = el.getAttribute("width") || (el.style?.width || "").replace("px", "");
                    const n = parseInt(w, 10);
                    return Number.isFinite(n) && n > 0 ? n : null;
                },
                renderHTML: (attrs) => (attrs.width ? { width: attrs.width } : {}),
            },
            align: {
                default: "left",
                parseHTML: (el) => {
                    const parent = el.parentElement;
                    return (
                        el.getAttribute("data-align") ||
                        parent?.getAttribute?.("data-image-align") ||
                        parent?.style?.textAlign ||
                        "left"
                    );
                },
                renderHTML: (attrs) => ({ "data-align": attrs.align || "left" }),
            },
            // Optional href — when set, the rendered image is wrapped in <a>
            // so email clients treat the whole picture as a click target. The
            // editor keeps the raw <img> node so we don't have to fight the
            // separate Link mark; the wrap only happens at render time.
            link: {
                default: null,
                parseHTML: (el) => {
                    const anchor = el.closest?.("a[href]");
                    return anchor?.getAttribute("href") || null;
                },
                renderHTML: () => ({}),  // handled by renderHTML() wrapper
            },
        };
    },

    parseHTML() {
        return [
            {
                tag: "div[data-image-align]",
                getAttrs: (el) => {
                    const img = el.querySelector("img");
                    if (!img) return false;
                    const anchor = el.querySelector("a[href]");
                    const w = parseInt(img.getAttribute("width") || (img.style?.width || "").replace("px", ""), 10);
                    return {
                        src: img.getAttribute("src"),
                        alt: img.getAttribute("alt"),
                        title: img.getAttribute("title"),
                        width: Number.isFinite(w) && w > 0 ? w : null,
                        align: el.getAttribute("data-image-align") || "left",
                        link: anchor?.getAttribute("href") || null,
                    };
                },
            },
            { tag: "img[src]" },
        ];
    },

    renderHTML({ HTMLAttributes, node }) {
        const w = node.attrs.width;
        const align = node.attrs.align || "left";
        const link = node.attrs.link;
        const imgStyle = [
            "max-width:100%",
            "height:auto",
            "display:inline-block",
            "border-radius:8px",
            w ? `width:${w}px` : "width:100%",
        ].join(";");

        const imgAttrs = { ...HTMLAttributes };
        delete imgAttrs.class;
        delete imgAttrs.link;
        if (w) imgAttrs.width = w;
        imgAttrs.style = imgStyle;
        imgAttrs["data-align"] = align;

        const imgTag = ["img", imgAttrs];
        // Wrap in <a> when a link is set — the anchor inherits `text-decoration:none`
        // so email clients don't add an underline around the picture.
        const inner = link
            ? ["a", { href: link, target: "_blank", rel: "noopener", style: "text-decoration:none;display:inline-block" }, imgTag]
            : imgTag;

        return [
            "div",
            {
                "data-image-align": align,
                style: `text-align:${align};margin:8px 0`,
            },
            inner,
        ];
    },

    addNodeView() {
        return ReactNodeViewRenderer(ResizableImageView);
    },
});

export default ResizableImage;
