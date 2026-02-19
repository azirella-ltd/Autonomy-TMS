import { format, isValid, parseISO } from "date-fns";

const TIME_BUCKET_META = {
  week: {
    singular: "Week",
    plural: "Weeks",
    formatter: (date) => format(date, "dd/MM/yyyy"),
  },
  month: {
    singular: "Month",
    plural: "Months",
    formatter: (date) => format(date, "MMM-yyyy"),
  },
  quarter: {
    singular: "Quarter",
    plural: "Quarters",
    formatter: (date) => {
      const quarterIndex = Math.max(
        1,
        Math.min(4, Math.ceil((date.getMonth() + 1) / 3))
      );
      const year = format(date, "yyyy");
      return `Q${quarterIndex}-${year}`;
    },
  },
};

export const normalizeTimeBucket = (bucket) => {
  if (!bucket) return "week";
  const normalized = String(bucket).trim().toLowerCase();
  return TIME_BUCKET_META[normalized] ? normalized : "week";
};

const ensureDate = (value) => {
  if (!value) return null;
  if (value instanceof Date) {
    return isValid(value) ? value : null;
  }
  const parsed = parseISO(String(value));
  return isValid(parsed) ? parsed : null;
};

export const getTimePeriodMeta = (bucket) => {
  const normalized = normalizeTimeBucket(bucket);
  return {
    bucket: normalized,
    singular: TIME_BUCKET_META[normalized].singular,
    plural: TIME_BUCKET_META[normalized].plural,
    formatter: TIME_BUCKET_META[normalized].formatter,
  };
};

export const getTimePeriodLabel = (bucket, { plural = false } = {}) => {
  const meta = getTimePeriodMeta(bucket);
  return plural ? meta.plural : meta.singular;
};

export const formatTimePeriodDate = (value, bucket) => {
  const meta = getTimePeriodMeta(bucket);
  const date = ensureDate(value);
  if (!date) return "";
  return meta.formatter(date);
};

export const buildTimePeriodDisplay = (index, bucket, value) => {
  const dateLabel = formatTimePeriodDate(value, bucket);
  const periodLabel = getTimePeriodLabel(bucket);
  if (dateLabel) {
    return `${periodLabel} ${index}: ${dateLabel}`;
  }
  return `${periodLabel} ${index}`;
};

export const mapSeriesWithPeriodLabels = (series = [], bucket) =>
  series.map((entry) => {
    const periodStart = entry.period_start || entry.periodStart || null;
    const formattedDate = formatTimePeriodDate(periodStart, bucket);
    return {
      ...entry,
      periodStart,
      formattedDate,
      periodLabel:
        formattedDate ||
        `${getTimePeriodLabel(bucket)} ${entry.round ?? ""}`.trim(),
    };
  });

const timePeriodUtils = {
  normalizeTimeBucket,
  getTimePeriodMeta,
  getTimePeriodLabel,
  formatTimePeriodDate,
  buildTimePeriodDisplay,
  mapSeriesWithPeriodLabels,
};

export default timePeriodUtils;
