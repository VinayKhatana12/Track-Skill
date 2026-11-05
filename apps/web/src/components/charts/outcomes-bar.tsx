"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Outcomes-by-milestone bar chart with accessible colours and tooltips. */
export function OutcomesBar({
  data,
}: {
  data: { milestone: string; rate: number }[];
}) {
  const percent = (value: number) => `${Math.round(value * 100)}%`;
  return (
    <div
      className="h-64 w-full"
      role="img"
      aria-label={`Retention by milestone: ${data
        .map((item) => `${item.milestone} ${percent(item.rate)}`)
        .join(", ")}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="milestone"
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
            stroke="hsl(var(--border))"
          />
          <YAxis
            tickFormatter={percent}
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
            stroke="hsl(var(--border))"
            domain={[0, 1]}
          />
          <Tooltip
            formatter={(value: number | string) => percent(Number(value))}
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              color: "hsl(var(--card-foreground))",
            }}
          />
          <Bar
            dataKey="rate"
            name="Still in work"
            fill="#2f8f8c"
            radius={[6, 6, 0, 0]}
            maxBarSize={56}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
