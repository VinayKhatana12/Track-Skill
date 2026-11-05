"use client";

/** Exports table rows as a downloadable CSV file (client-side, no deps). */
export function downloadCsv(
  filename: string,
  rows: readonly Record<string, unknown>[],
): void {
  if (rows.length === 0) {
    return;
  }
  const headers = Object.keys(rows[0]);
  const escape = (value: unknown) =>
    `"${String(value ?? "").replace(/"/g, '""')}"`;
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => escape(row[header])).join(",")),
  ].join("\r\n");

  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Opens the browser print dialog for the element with the given id.
 * The user can "Save as PDF" — the print stylesheet isolates the section. */
export function printSection(elementId: string): void {
  const target = document.getElementById(elementId);
  if (!target) {
    return;
  }
  document.body.classList.add("printing-section");
  target.classList.add("print-target");
  window.print();
  window.setTimeout(() => {
    document.body.classList.remove("printing-section");
    target.classList.remove("print-target");
  }, 400);
}
