import React from "react";
import PropTypes from "prop-types";
import { cn } from "../../lib/utils/cn";

const FLOW_COLOR = "#475569";
const NODE_COLOR_GRADIENT = "linear-gradient(90deg, #10b981 0%, #f97316 50%, #dc2626 100%)";
const LINK_COLOR_GRADIENT = "linear-gradient(90deg, #16a34a 0%, #f97316 50%, #dc2626 100%)";

const SankeyMetricLegend = ({
  orientation = "row",
  justify = "flex-start",
  className,
  mode = "flow",
}) => {
  const metricDescription =
    mode === "capacity"
      ? "Capacity (target inventory / limits)"
      : "Flow (orders processed / shipments)";

  const items = [
    {
      key: "flow",
      title: "Site height & lane width",
      description: metricDescription,
      icon: (
        <div
          className="w-9 h-2.5 rounded"
          style={{ backgroundColor: FLOW_COLOR }}
        />
      ),
    },
    {
      key: "site-color",
      title: "Site color",
      description: "Inventory ratio vs. average inventory (balanced -> constrained)",
      icon: (
        <div
          className="w-9 h-3 rounded-full border border-slate-900/20"
          style={{ background: NODE_COLOR_GRADIENT }}
        />
      ),
    },
    {
      key: "lane-color",
      title: "Lane color",
      description: "Lead time (short -> long)",
      icon: (
        <div
          className="w-9 h-2 rounded-full"
          style={{ background: LINK_COLOR_GRADIENT }}
        />
      ),
    },
  ];

  const justifyClasses = {
    'flex-start': 'justify-start',
    'center': 'justify-center',
    'flex-end': 'justify-end',
    'space-between': 'justify-between',
    'space-around': 'justify-around',
  };

  return (
    <div
      className={cn(
        "flex flex-wrap items-start gap-6",
        orientation === "row" ? "flex-row" : "flex-col",
        justifyClasses[justify] || 'justify-start',
        className
      )}
    >
      {items.map((item) => (
        <div key={item.key} className="flex flex-row items-center gap-3">
          {item.icon}
          <div>
            <span className="text-xs font-semibold text-slate-900 block">
              {item.title}
            </span>
            <span className="text-xs text-slate-600 block">
              {item.description}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};

SankeyMetricLegend.propTypes = {
  orientation: PropTypes.oneOf(["row", "column"]),
  justify: PropTypes.oneOf(["flex-start", "center", "flex-end", "space-between", "space-around"]),
  className: PropTypes.string,
  mode: PropTypes.oneOf(["flow", "capacity"]),
};

export default SankeyMetricLegend;
