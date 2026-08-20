export const humanize = (value: string) =>
  value.replace(/[_-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

export const formatNumber = (value: number | null | undefined) =>
  typeof value === "number" ? new Intl.NumberFormat("en-US").format(value) : "—";

export const formatDecimal = (value: number | null | undefined, fractionDigits = 2) =>
  typeof value === "number"
    ? new Intl.NumberFormat("en-US", { maximumFractionDigits: fractionDigits }).format(value)
    : "—";

export const formatDateTime = (value: string | null | undefined) => {
  if (!value) return "Not provided";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
};
