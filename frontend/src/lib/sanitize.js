/**
 * Centralized HTML sanitization for `dangerouslySetInnerHTML`.
 *
 * Why a wrapper rather than inlining DOMPurify everywhere:
 *   - Single place to evolve the allow-list (e.g. add an embed source later).
 *   - All admin-authored HTML — gear titles, email previews, signatures, CMS
 *     blocks — goes through the same policy, so one change covers them all.
 *   - Returns the same object shape React expects (`{ __html }`), so call sites
 *     remain a one-liner: `dangerouslySetInnerHTML={safeHtml(content)}`.
 *
 * The default DOMPurify policy strips `<script>`, on* event handlers, javascript:
 * URLs, and dangerous SVG. We extend it slightly to keep the inline styles our
 * TipTap editor emits (width / max-width / text-align on images, etc.) without
 * which the email composer preview would collapse.
 */
import DOMPurify from "dompurify";

const DEFAULT_CONFIG = {
    // Allow common rich-text + email-safe tags.
    ALLOWED_TAGS: [
        "a", "b", "i", "em", "strong", "u", "s", "code", "pre", "blockquote",
        "p", "br", "hr", "span", "div", "section", "header", "footer", "article",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "li",
        "table", "thead", "tbody", "tfoot", "tr", "td", "th",
        "img", "figure", "figcaption",
    ],
    // Allow inline styles + data-* attributes used by our TipTap output for
    // image alignment and sizing.
    ALLOWED_ATTR: [
        "href", "title", "target", "rel",
        "src", "alt", "width", "height", "loading",
        "style", "class",
        "data-align", "data-image-align",
        "colspan", "rowspan",
    ],
    // Force every <a> to open safely in a new tab without leaking referrer.
    ADD_ATTR: ["target"],
    // Block protocols other than http(s), mailto, tel, and data:image
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|data:image\/(?:gif|jpe?g|png|webp);|\/|#)/i,
};

/**
 * Sanitize an arbitrary HTML string and return the props object React expects:
 *
 *     <div dangerouslySetInnerHTML={safeHtml(item.body_html)} />
 *
 * Pass `null`/`undefined`/non-string and we return an empty `__html` string —
 * never throws.
 */
export function safeHtml(raw) {
    const html = typeof raw === "string" ? raw : "";
    return { __html: DOMPurify.sanitize(html, DEFAULT_CONFIG) };
}

export default safeHtml;
