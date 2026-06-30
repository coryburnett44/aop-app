/**
 * Event-time helpers.
 *
 * Per organization policy, every event time displayed in the UI is shown in
 * Eastern Time (EST in winter, EDT in summer — same IANA zone). Members
 * across multiple chapters/timezones see the same canonical time, which
 * matches printed flyers and email blasts.
 *
 * - `fmtET(iso, pattern)` — render a stored UTC ISO in Eastern Time for display.
 * - `etInputToUtc(localStr)` — convert a `<input type="datetime-local">` value
 *   (a naive `YYYY-MM-DDTHH:mm`) to a UTC ISO string by interpreting it AS
 *   Eastern Time. This prevents the "admin in Texas typed 6pm, ticket shows
 *   7pm" bug: the browser would otherwise interpret the naive string as the
 *   admin's local timezone.
 * - `utcToEtInput(iso)` — opposite direction, for pre-filling the same
 *   input from a stored UTC value so what the admin sees in the input is
 *   the Eastern Time wall-clock they expect to edit.
 */
import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

export const EVENT_TZ = "America/New_York";

export function fmtET(iso, pattern) {
    if (!iso) return "";
    try {
        return formatInTimeZone(iso, EVENT_TZ, pattern);
    } catch {
        return "";
    }
}

/**
 * Convert a `datetime-local`-formatted string (no timezone, e.g. "2026-03-15T18:00")
 * into a real UTC ISO string by interpreting the input as Eastern Time.
 * Returns `null` for falsy input so callers can pass it straight to the API
 * (matches how `end_at` is treated as optional).
 */
export function etInputToUtc(localStr) {
    if (!localStr) return null;
    try {
        // fromZonedTime interprets `localStr` as a wall-clock in the given
        // zone and returns the equivalent UTC Date.
        return fromZonedTime(localStr, EVENT_TZ).toISOString();
    } catch {
        return null;
    }
}

/**
 * Convert a UTC ISO string (as stored on the server) into the
 * `YYYY-MM-DDTHH:mm` shape required by `<input type="datetime-local">`,
 * with the wall-clock in Eastern Time. Used to pre-fill the edit form so
 * the admin sees the same time they originally entered (in ET).
 */
export function utcToEtInput(iso) {
    if (!iso) return "";
    try {
        return formatInTimeZone(iso, EVENT_TZ, "yyyy-MM-dd'T'HH:mm");
    } catch {
        return "";
    }
}
