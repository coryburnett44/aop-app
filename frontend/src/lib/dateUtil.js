/**
 * Date formatting helpers — TZ-safe wrappers around date-fns.
 *
 * Why this file exists:
 *   `format(parseISO(iso), "MMM d, yyyy")` is the obvious one-liner, but it
 *   silently misrenders any timestamp stored as UTC midnight (`2025-11-11T00:00:00Z`)
 *   in any western-hemisphere timezone — it shifts to the *previous* calendar
 *   day. That bit us across Hours, Awards, and Membership-expiration dates.
 *
 *   `formatCalendarDay(iso, "MMM d, yyyy")` ignores the time portion entirely
 *   and formats only the YYYY-MM-DD prefix as local-midnight. This is the
 *   correct semantic for "logical date" fields — a volunteer service date,
 *   a membership expiration date, a birthdate — none of which carry a
 *   meaningful time component.
 *
 *   `format(parseISO(...))` should still be used for timestamps that DO carry
 *   a time (event start, sent_at, created_at when timing matters).
 */
import { format, parseISO } from "date-fns";

/**
 * Format a "calendar day" portion of an ISO string as a local-tz-safe label.
 *
 *   formatCalendarDay("2025-11-11T00:00:00Z", "MMM d, yyyy")
 *     -> "Nov 11, 2025"   (regardless of viewer's timezone)
 *
 * Accepts either a full ISO timestamp or a bare "YYYY-MM-DD". Returns the
 * empty string for null/undefined/empty input — never throws.
 *
 * @param {string|null|undefined} iso  ISO timestamp or "YYYY-MM-DD"
 * @param {string} pattern             date-fns format pattern (default: "MMM d, yyyy")
 * @returns {string}
 */
export function formatCalendarDay(iso, pattern = "MMM d, yyyy") {
    if (!iso || typeof iso !== "string") return "";
    // Extract the date prefix. Works for both "YYYY-MM-DD" (length 10) and any
    // ISO 8601 timestamp like "YYYY-MM-DDTHH:MM:SS[.sss]Z".
    const ymd = iso.length >= 10 ? iso.slice(0, 10) : iso;
    // Append `T00:00:00` so parseISO treats it as local midnight (not UTC midnight).
    // This makes the displayed calendar day match what the submitter typed.
    try {
        return format(parseISO(`${ymd}T00:00:00`), pattern);
    } catch {
        return "";
    }
}

export default formatCalendarDay;
