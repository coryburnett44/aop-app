/**
 * Canonical list of US Armed Forces branches recognized by AOP.
 *
 * Order matches official Department of Defense seniority (Army → Air Force →
 * Marine Corps → Navy → Coast Guard → Space Force). Used by:
 *   - Profile.jsx "Branch of service" dropdown (member self-edit).
 *   - Admin.jsx member edit + create dropdowns (admin override).
 * The free-text `branch_of_service` field on the user document continues to
 * accept any string for backward compatibility with legacy entries, so the
 * select renders existing non-canonical values as-is when present.
 */
export const MILITARY_BRANCHES = [
    "Army",
    "Air Force",
    "Marine Corps",
    "Navy",
    "Coast Guard",
    "Space Force",
];
