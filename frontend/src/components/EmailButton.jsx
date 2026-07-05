/**
 * EmailButton — custom TipTap node that renders a Call-To-Action button
 * as an email-safe `<a>` with inline styles that survive Gmail / Outlook /
 * Apple Mail (which all strip <style> tags).
 *
 * Insert:  editor.chain().focus().insertContent({ type: 'emailButton', attrs: { label, href } }).run()
 *
 * We use a `Node` (not the built-in Link mark) so TipTap's Link extension
 * doesn't hijack the anchor and strip our styles.
 */
import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";

const DEFAULT_STYLE = "display:inline-block;background:#C8102E;color:#ffffff;text-decoration:none;font-weight:700;padding:12px 28px;border-radius:999px;font-size:15px;line-height:1;font-family:Inter,Helvetica,Arial,sans-serif";

function EmailButtonView({ node, updateAttributes, selected, deleteNode, editor }) {
    const { label, href, align } = node.attrs;
    const isEditable = editor?.isEditable !== false;

    function editHref() {
        const next = window.prompt("Button link URL", href || "https://");
        if (next === null) return;
        updateAttributes({ href: next.trim() });
    }
    function editLabel() {
        const next = window.prompt("Button label", label || "Learn more");
        if (next === null) return;
        updateAttributes({ label: next.trim() || label });
    }

    return (
        <NodeViewWrapper
            as="div"
            data-testid="email-button-wrapper"
            style={{ textAlign: align || "center", margin: "18px 0" }}
            contentEditable={false}
        >
            <span style={{ position: "relative", display: "inline-block" }}>
                {/* The visible pill — we render as a <span> in-editor so
                    clicks land on our toolbar, not the actual href. */}
                <span
                    style={{
                        display: "inline-block",
                        background: "#C8102E",
                        color: "#ffffff",
                        fontWeight: 700,
                        padding: "12px 28px",
                        borderRadius: 999,
                        fontSize: 15,
                        lineHeight: 1,
                        outline: selected && isEditable ? "2px solid #3b82f6" : "2px solid transparent",
                        outlineOffset: 3,
                        userSelect: "none",
                    }}
                    data-testid="email-button-pill"
                >
                    {label || "Learn more"}
                </span>
                {selected && isEditable && (
                    <div
                        style={{
                            position: "absolute",
                            top: -34,
                            left: "50%",
                            transform: "translateX(-50%)",
                            background: "#0f172a",
                            color: "#fff",
                            borderRadius: 6,
                            padding: "3px 4px",
                            display: "flex",
                            gap: 2,
                            fontSize: 11,
                            zIndex: 20,
                            whiteSpace: "nowrap",
                            boxShadow: "0 4px 16px rgba(0,0,0,.25)",
                        }}
                        data-testid="email-button-toolbar"
                    >
                        <button type="button" onClick={editLabel} className="px-2 py-0.5 rounded hover:bg-slate-700" data-testid="email-button-edit-label">Label</button>
                        <span style={{ width: 1, background: "#475569" }} />
                        <button type="button" onClick={editHref} className="px-2 py-0.5 rounded hover:bg-slate-700" data-testid="email-button-edit-href" title={href}>URL</button>
                        <span style={{ width: 1, background: "#475569" }} />
                        <button type="button" onClick={() => updateAttributes({ align: "left" })} className={`px-2 py-0.5 rounded hover:bg-slate-700 ${align === "left" ? "bg-blue-600" : ""}`}>L</button>
                        <button type="button" onClick={() => updateAttributes({ align: "center" })} className={`px-2 py-0.5 rounded hover:bg-slate-700 ${(align || "center") === "center" ? "bg-blue-600" : ""}`}>C</button>
                        <button type="button" onClick={() => updateAttributes({ align: "right" })} className={`px-2 py-0.5 rounded hover:bg-slate-700 ${align === "right" ? "bg-blue-600" : ""}`}>R</button>
                        <span style={{ width: 1, background: "#475569" }} />
                        <button type="button" onClick={deleteNode} className="px-2 py-0.5 rounded text-red-300 hover:bg-slate-700" data-testid="email-button-remove">×</button>
                    </div>
                )}
            </span>
        </NodeViewWrapper>
    );
}

const EmailButton = Node.create({
    name: "emailButton",
    group: "block",
    atom: true,
    selectable: true,
    draggable: false,

    addAttributes() {
        return {
            label: { default: "Learn more" },
            href: { default: "https://" },
            align: { default: "center" },
        };
    },

    parseHTML() {
        return [
            {
                tag: "a[data-email-button]",
                getAttrs: (el) => ({
                    label: el.textContent || "",
                    href: el.getAttribute("href") || "",
                    align: el.parentElement?.style?.textAlign || "center",
                }),
            },
        ];
    },

    renderHTML({ node }) {
        const { label, href, align } = node.attrs;
        return [
            "div",
            { style: `text-align:${align || "center"};margin:18px 0` },
            [
                "a",
                mergeAttributes({
                    href: href || "#",
                    target: "_blank",
                    rel: "noopener",
                    "data-email-button": "1",
                    style: DEFAULT_STYLE,
                }),
                label || "Learn more",
            ],
        ];
    },

    addNodeView() {
        return ReactNodeViewRenderer(EmailButtonView);
    },
});

export default EmailButton;
