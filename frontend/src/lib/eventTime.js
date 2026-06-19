/**
 * Event-time helpers.
 *
 * Per organization policy, every event time displayed in the UI is shown in
 * Eastern Time (EST in winter, EDT in summer — same IANA zone). Members
 * across multiple chapters/timezones see the same canonical time, which
 * matches printed flyers and email blasts.
 *
 * `fmtET(iso, pattern)` is a thin wrapper around `formatInTimeZone` from
 * date-fns-tz. Use it any place we'd otherwise call `format(parseISO(iso))`
 * for an event's start_at / end_at / checked_in_at.
 */
import { formatInTimeZone } from "date-fns-tz";

export const EVENT_TZ = "America/New_York";

export function fmtET(iso, pattern) {
    if (!iso) return "";
    try {
        return formatInTimeZone(iso, EVENT_TZ, pattern);
    } catch {
        return "";
    }
}
