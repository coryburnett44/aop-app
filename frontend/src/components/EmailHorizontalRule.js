/**
 * Styled email-safe HR. Overrides StarterKit's plain <hr> so we bake inline
 * styles that survive Gmail/Outlook (which strip <style> tags).
 */
import HorizontalRule from "@tiptap/extension-horizontal-rule";

const EmailHorizontalRule = HorizontalRule.extend({
    renderHTML() {
        return [
            "hr",
            {
                style: "border:none;border-top:1px solid #e2e8f0;margin:20px auto;max-width:80%",
                "data-email-hr": "1",
            },
        ];
    },
});

export default EmailHorizontalRule;
