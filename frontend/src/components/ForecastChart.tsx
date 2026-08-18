"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ForecastVsActual } from "@/lib/api";

export default function ForecastChart({ data }: { data: ForecastVsActual[] }) {
  const chartData = [...data]
    .sort((a, b) => a.target_date.localeCompare(b.target_date))
    .map((d) => ({
      date: d.target_date.slice(5), // MM-DD
      Forecast: d.predicted_high,
      Actual: d.actual_high,
    }));

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-neutral-500">
        No forecast history yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="date" tick={{ fontSize: 12, fill: "var(--chart-axis)" }} />
        <YAxis
          tick={{ fontSize: 12, fill: "var(--chart-axis)" }}
          unit="°F"
          domain={["dataMin - 3", "dataMax + 3"]}
        />
        <Tooltip
          contentStyle={{
            background: "var(--card-bg)",
            border: "1px solid var(--card-border)",
            borderRadius: 8,
            fontSize: 13,
          }}
        />
        <Line
          type="monotone"
          dataKey="Forecast"
          stroke="var(--accent-forecast)"
          strokeWidth={2}
          dot={{ r: 3 }}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="Actual"
          stroke="var(--accent-actual)"
          strokeWidth={2}
          dot={{ r: 3 }}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
