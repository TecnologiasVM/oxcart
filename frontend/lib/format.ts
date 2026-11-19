/*
 * Display formatters shared across components.
 *
 * The Issue node's `issue_dates` arrives as a JSON *string* of a date map, e.g.
 *   {"announced": null, "placed_on_sale": "1863-12-01",
 *    "probable_first_circulation": "1863-04-11", "demonetized": "1883-01-31"}
 * Rendering it verbatim dumps raw JSON in the UI. These helpers turn it into
 * either a single year (compact headers) or a readable label list (detail views).
 */

const DATE_LABELS: Record<string, string> = {
  announced: "announced",
  placed_on_sale: "placed on sale",
  probable_first_circulation: "first circulation",
  second_plate_sale: "second plate",
  demonetized: "demonetized",
};

function asDateMap(value: unknown): Record<string, unknown> | null {
  let obj: unknown = value;
  if (typeof value === "string") {
    const s = value.trim();
    if (!s.startsWith("{")) return null;
    try {
      obj = JSON.parse(s);
    } catch {
      return null;
    }
  }
  return obj && typeof obj === "object" ? (obj as Record<string, unknown>) : null;
}

/** Best single year for a compact header (falls back to "1863"). */
export function issueYear(value: unknown): string {
  if (value == null) return "1863";
  const map = asDateMap(value);
  if (!map) return typeof value === "string" ? value : String(value);
  const candidate =
    map.placed_on_sale ?? map.probable_first_circulation ?? map.announced;
  if (typeof candidate === "string" && candidate.length >= 4) {
    return candidate.slice(0, 4);
  }
  return "1863";
}

/**
 * Readable date list for detail/domain views, e.g.
 *   "placed on sale 1863-12-01 · first circulation 1863-04-11 · demonetized 1883-01-31"
 * Returns the original string unchanged when it is not a date map.
 */
export function issueDatesText(value: unknown): string {
  if (value == null) return "—";
  const map = asDateMap(value);
  if (!map) return typeof value === "string" ? value : String(value);
  const parts: string[] = [];
  for (const [key, val] of Object.entries(map)) {
    if (val == null || val === "") continue;
    parts.push(`${DATE_LABELS[key] ?? key.replace(/_/g, " ")} ${String(val)}`);
  }
  return parts.length ? parts.join(" · ") : "—";
}

/*
 * Display-only denomination correction for known Mena source-data errors.
 * The Mena graph is read-only and never mutated; we fix the value only for the
 * UI. Mena 1A (Scott 1a, light blue) is the second-plate ½ real = 0.5 real, but
 * the Mena source records denomination_value=1.5. Show the true denomination.
 */
const DENOM_OVERRIDES: Record<string, { value: number; unit: string }> = {
  "1A": { value: 0.5, unit: "real" },
};

export function displayDenom(
  catalogNo: unknown,
  value: unknown,
  unit: unknown,
): string {
  const cno = String(catalogNo ?? "");
  const o = DENOM_OVERRIDES[cno];
  const v = o ? o.value : value;
  const u = o ? o.unit : unit;
  if (v === null || v === undefined || v === "") return u ? String(u) : "";
  return `${v} ${u ?? ""}`.trim();
}

/*
 * One chronology event per non-empty issue_dates entry, sorted ascending, for
 * the Query-view timeline. The "first circulation" date is the focal moment.
 * Returns [] when the value is not a date map.
 */
export interface DateEvent {
  yr: string;
  label: string;
  focal: boolean;
}

export function issueDateEvents(value: unknown): DateEvent[] {
  const map = asDateMap(value);
  if (!map) return [];
  const events: { iso: string; ev: DateEvent }[] = [];
  for (const [key, val] of Object.entries(map)) {
    if (val == null || val === "") continue;
    const iso = String(val);
    events.push({
      iso,
      ev: {
        yr: iso.slice(0, 4),
        label: DATE_LABELS[key] ?? key.replace(/_/g, " "),
        focal: key === "probable_first_circulation",
      },
    });
  }
  events.sort((a, b) => a.iso.localeCompare(b.iso));
  return events.map((e) => e.ev);
}

/*
 * Repair the single common mojibake in the parsed Scott catalogue: the half (½)
 * glyph decoded as U+FFFD ("�r" → "½r"). The graph is never mutated — this is a
 * display-only fix for Scott catalogue strings (denomination/description).
 */
export function cleanCatalogText(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/�/g, "½");
}
