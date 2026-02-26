"""
Hierarchical Metrics Service

Generates Gartner-aligned supply chain metrics organized into 4 tiers
(ASSESS, DIAGNOSE, CORRECT, AI-as-Labor) with hierarchy-aware demo data
that varies deterministically by Geography, Product, and Time dimensions.

Hierarchy dimensions:
  - Site:    Company > Region > Country > Site
  - Product: Category > Family > Group > Product
  - Time:    Year > Quarter > Month > Week
"""

import hashlib
from typing import Any, Dict, List, Optional


# ============================================================================
# Hierarchy definitions (demo data)
# ============================================================================

SITE_HIERARCHY = {
    "company": {
        "ALL": {
            "label": "HydraBev Corp",
            "children": {
                "region": {
                    "NA": {"label": "North America", "children": {
                        "country": {
                            "US": {"label": "United States", "children": {
                                "site": {
                                    "DC-CHI": {"label": "DC Chicago"},
                                    "DC-IND": {"label": "DC Indianapolis"},
                                    "DC-LA": {"label": "DC Los Angeles"},
                                    "PLT-ATL": {"label": "Plant Atlanta"},
                                }
                            }},
                            "CA": {"label": "Canada", "children": {
                                "site": {
                                    "DC-TOR": {"label": "DC Toronto"},
                                    "DC-VAN": {"label": "DC Vancouver"},
                                }
                            }},
                        }
                    }},
                    "EU": {"label": "Europe", "children": {
                        "country": {
                            "DE": {"label": "Germany", "children": {
                                "site": {"DC-FRA": {"label": "DC Frankfurt"}, "PLT-MUN": {"label": "Plant Munich"}}
                            }},
                            "UK": {"label": "United Kingdom", "children": {
                                "site": {"DC-LON": {"label": "DC London"}}
                            }},
                        }
                    }},
                    "APAC": {"label": "Asia Pacific", "children": {
                        "country": {
                            "JP": {"label": "Japan", "children": {
                                "site": {"DC-TKY": {"label": "DC Tokyo"}}
                            }},
                            "AU": {"label": "Australia", "children": {
                                "site": {"DC-SYD": {"label": "DC Sydney"}}
                            }},
                        }
                    }},
                    "LATAM": {"label": "Latin America", "children": {
                        "country": {
                            "BR": {"label": "Brazil", "children": {
                                "site": {"DC-SAO": {"label": "DC Sao Paulo"}}
                            }},
                            "MX": {"label": "Mexico", "children": {
                                "site": {"DC-MEX": {"label": "DC Mexico City"}}
                            }},
                        }
                    }},
                }
            }
        }
    }
}

PRODUCT_HIERARCHY = {
    "category": {
        "ALL": {
            "label": "All Products",
            "children": {
                "family": {
                    "SPORTS": {"label": "Sports Drinks", "children": {
                        "group": {
                            "HYDRABOOST": {"label": "HydraBoost", "children": {
                                "product": {
                                    "HB-1001": {"label": "HydraBoost Original 12pk"},
                                    "HB-1002": {"label": "HydraBoost Citrus 12pk"},
                                    "HB-1003": {"label": "HydraBoost Berry 12pk"},
                                }
                            }},
                        }
                    }},
                    "ENHANCED": {"label": "Enhanced Water", "children": {
                        "group": {
                            "HYDRALITE": {"label": "HydraLite", "children": {
                                "product": {
                                    "HL-2001": {"label": "HydraLite Lemon 6pk"},
                                    "HL-2002": {"label": "HydraLite Plain 6pk"},
                                }
                            }},
                        }
                    }},
                    "ENERGY": {"label": "Energy Drinks", "children": {
                        "group": {
                            "HYDRASURGE": {"label": "HydraSurge", "children": {
                                "product": {
                                    "HS-3001": {"label": "HydraSurge Original"},
                                    "HS-3002": {"label": "HydraSurge Zero"},
                                }
                            }},
                        }
                    }},
                    "BOTTLED": {"label": "Bottled Water", "children": {
                        "group": {
                            "HYDRAPURE": {"label": "HydraPure", "children": {
                                "product": {
                                    "HP-4001": {"label": "HydraPure Spring 24pk"},
                                    "HP-4002": {"label": "HydraPure Sparkling 12pk"},
                                }
                            }},
                        }
                    }},
                }
            }
        }
    }
}

TIME_HIERARCHY = {
    "year": {
        "2025": {
            "label": "2025",
            "children": {
                "quarter": {
                    "2025-Q1": {"label": "Q1 2025", "children": {
                        "month": {
                            "2025-01": {"label": "Jan 2025"}, "2025-02": {"label": "Feb 2025"}, "2025-03": {"label": "Mar 2025"},
                        }
                    }},
                    "2025-Q2": {"label": "Q2 2025", "children": {
                        "month": {
                            "2025-04": {"label": "Apr 2025"}, "2025-05": {"label": "May 2025"}, "2025-06": {"label": "Jun 2025"},
                        }
                    }},
                    "2025-Q3": {"label": "Q3 2025", "children": {
                        "month": {
                            "2025-07": {"label": "Jul 2025"}, "2025-08": {"label": "Aug 2025"}, "2025-09": {"label": "Sep 2025"},
                        }
                    }},
                    "2025-Q4": {"label": "Q4 2025", "children": {
                        "month": {
                            "2025-10": {"label": "Oct 2025"}, "2025-11": {"label": "Nov 2025"}, "2025-12": {"label": "Dec 2025"},
                        }
                    }},
                }
            }
        },
        "2024": {
            "label": "2024",
            "children": {
                "quarter": {
                    "2024-Q4": {"label": "Q4 2024", "children": {
                        "month": {
                            "2024-10": {"label": "Oct 2024"}, "2024-11": {"label": "Nov 2024"}, "2024-12": {"label": "Dec 2024"},
                        }
                    }},
                }
            }
        },
    }
}

# Region-specific adjustment factors for realistic variation
REGION_FACTORS = {
    "NA":    {"margin": 1.05, "service": 1.02, "cost": 0.95},
    "EU":    {"margin": 0.98, "service": 1.01, "cost": 1.02},
    "APAC":  {"margin": 0.92, "service": 0.97, "cost": 1.08},
    "LATAM": {"margin": 0.85, "service": 0.93, "cost": 1.15},
}

PRODUCT_FACTORS = {
    "SPORTS":   {"margin": 1.10, "volatility": 0.95, "turns": 1.15},
    "ENHANCED": {"margin": 1.05, "volatility": 0.90, "turns": 1.05},
    "ENERGY":   {"margin": 1.20, "volatility": 1.25, "turns": 1.30},
    "BOTTLED":  {"margin": 0.75, "volatility": 0.80, "turns": 0.85},
}

LEVEL_ORDER = {
    "site": ["company", "region", "country", "site"],
    "product": ["category", "family", "group", "product"],
    "time": ["year", "quarter", "month", "week"],
}


def _vary(base: float, context_key: str, amplitude: float = 0.08) -> float:
    """Deterministic pseudo-random variation based on context key."""
    h = int(hashlib.md5(context_key.encode()).hexdigest()[:8], 16)
    offset = ((h % 1000) / 1000.0 - 0.5) * 2 * amplitude
    return round(base * (1 + offset), 2)


def _status(value: float, target: float, lower_is_better: bool = False) -> str:
    if lower_is_better:
        if value <= target:
            return "success"
        elif value <= target * 1.15:
            return "warning"
        return "danger"
    else:
        if value >= target:
            return "success"
        elif value >= target * 0.9:
            return "warning"
        return "danger"


def _find_node(hierarchy: dict, level: str, key: str):
    """Walk a hierarchy tree to find a node at a given level/key."""
    if level in hierarchy and key in hierarchy[level]:
        return hierarchy[level][key]
    for lvl_nodes in hierarchy.values():
        for node in lvl_nodes.values():
            if "children" in node:
                result = _find_node(node["children"], level, key)
                if result:
                    return result
    return None


def _get_ancestors(hierarchy: dict, target_level: str, target_key: str, levels: list):
    """Get breadcrumb trail from root to target node."""
    crumbs = []

    def _walk(tree, depth=0):
        if depth >= len(levels):
            return False
        current_level = levels[depth]
        if current_level not in tree:
            return False
        for key, node in tree[current_level].items():
            is_target = (current_level == target_level and key == target_key)
            crumbs.append({
                "level": current_level,
                "key": key,
                "label": node["label"],
                "is_current": is_target,
            })
            if is_target:
                return True
            if "children" in node:
                if _walk(node["children"], depth + 1):
                    return True
            crumbs.pop()
        return False

    _walk(hierarchy)
    return crumbs


def _get_children_at_level(hierarchy: dict, parent_level: str, parent_key: str):
    """Get children of a node for drill-down."""
    node = _find_node(hierarchy, parent_level, parent_key)
    if not node or "children" not in node:
        return []
    children = []
    for child_level, child_nodes in node["children"].items():
        for key, child in child_nodes.items():
            children.append({
                "key": key,
                "label": child["label"],
                "level": child_level,
                "can_drill_down": "children" in child,
            })
    return children


class HierarchicalMetricsService:
    """Generates Gartner-aligned metrics with hierarchy context."""

    def get_dashboard_metrics(
        self,
        tenant_id: int,
        site_level: str = "company",
        site_key: Optional[str] = None,
        product_level: str = "category",
        product_key: Optional[str] = None,
        time_bucket: str = "quarter",
        time_key: Optional[str] = None,
    ) -> Dict[str, Any]:

        site_key = site_key or "ALL"
        product_key = product_key or "ALL"
        time_key = time_key or "2025-Q3"

        ctx = f"{site_level}:{site_key}|{product_level}:{product_key}|{time_bucket}:{time_key}"

        # Determine adjustment factors from hierarchy position
        region_factor = REGION_FACTORS.get(site_key, {"margin": 1.0, "service": 1.0, "cost": 1.0})
        product_factor = PRODUCT_FACTORS.get(product_key, {"margin": 1.0, "volatility": 1.0, "turns": 1.0})

        return {
            "hierarchy_context": {
                "site_level": site_level,
                "site_key": site_key,
                "product_level": product_level,
                "product_key": product_key,
                "time_bucket": time_bucket,
                "time_key": time_key,
            },
            "breadcrumbs": self._build_breadcrumbs(site_level, site_key, product_level, product_key, time_bucket, time_key),
            "children": self._build_children(site_level, site_key, product_level, product_key, time_bucket, time_key),
            "tiers": {
                "tier1_assess": self._tier1_assess(ctx, region_factor, product_factor),
                "tier2_diagnose": self._tier2_diagnose(ctx, region_factor, product_factor),
                "tier3_correct": self._tier3_correct(ctx, region_factor, product_factor),
                "tier4_agent": self._tier4_agent(ctx),
            },
            "trend_data": self._trend_data(ctx, region_factor),
        }

    # ========================================================================
    # Breadcrumbs and children
    # ========================================================================

    def _build_breadcrumbs(self, site_level, site_key, product_level, product_key, time_bucket, time_key):
        return {
            "site": _get_ancestors(SITE_HIERARCHY, site_level, site_key, LEVEL_ORDER["site"]),
            "product": _get_ancestors(PRODUCT_HIERARCHY, product_level, product_key, LEVEL_ORDER["product"]),
            "time": _get_ancestors(TIME_HIERARCHY, time_bucket, time_key, LEVEL_ORDER["time"]),
        }

    def _build_children(self, site_level, site_key, product_level, product_key, time_bucket, time_key):
        return {
            "site": _get_children_at_level(SITE_HIERARCHY, site_level, site_key),
            "product": _get_children_at_level(PRODUCT_HIERARCHY, product_level, product_key),
            "time": _get_children_at_level(TIME_HIERARCHY, time_bucket, time_key),
        }

    # ========================================================================
    # Tier 1 — ASSESS (Strategic)
    # ========================================================================

    def _tier1_assess(self, ctx, rf, pf):
        m = rf.get("margin", 1.0)
        return {
            "label": "ASSESS \u2014 Strategic Health",
            "description": "Is our supply chain competitive?",
            "metrics": {
                "revenue_growth": {
                    "label": "Revenue Growth", "value": _vary(8.2 * m, ctx + "rg"), "unit": "%",
                    "target": 7.0, "trend": _vary(1.2, ctx + "rg_t", 0.3), "benchmark": "7-10%",
                    "status": _status(_vary(8.2 * m, ctx + "rg"), 7.0),
                    "scor_code": None,
                },
                "ebit_margin": {
                    "label": "EBIT Margin", "value": _vary(12.4 * m, ctx + "em"), "unit": "%",
                    "target": 12.0, "trend": _vary(0.4, ctx + "em_t", 0.5), "benchmark": "8-15%",
                    "status": _status(_vary(12.4 * m, ctx + "em"), 12.0),
                    "scor_code": None,
                },
                "rocs": {
                    "label": "Return on SC Capital", "value": _vary(28.0 * m, ctx + "rc"), "unit": "%",
                    "target": 25.0, "trend": _vary(3.0, ctx + "rc_t", 0.3), "benchmark": "15-40%",
                    "status": _status(_vary(28.0 * m, ctx + "rc"), 25.0),
                    "scor_code": None,
                },
                "gross_margin": {
                    "label": "Gross Margin", "value": _vary(32.5 * m * pf.get("margin", 1.0), ctx + "gm"), "unit": "%",
                    "target": 30.0, "trend": _vary(2.1, ctx + "gm_t", 0.3), "benchmark": "30-50%",
                    "status": _status(_vary(32.5 * m * pf.get("margin", 1.0), ctx + "gm"), 30.0),
                    "scor_code": None,
                },
                "total_cost_to_serve": {
                    "label": "Total Cost to Serve", "value": _vary(7.8 * rf.get("cost", 1.0), ctx + "tcs"), "unit": "% of revenue",
                    "target": 8.0, "trend": _vary(-0.2, ctx + "tcs_t", 0.5), "benchmark": "4-12%",
                    "status": _status(_vary(7.8 * rf.get("cost", 1.0), ctx + "tcs"), 8.0, lower_is_better=True),
                    "scor_code": "CO.1.1",
                },
            },
        }

    # ========================================================================
    # Tier 2 — DIAGNOSE (Tactical)
    # ========================================================================

    def _tier2_diagnose(self, ctx, rf, pf):
        sf = rf.get("service", 1.0)
        return {
            "label": "DIAGNOSE \u2014 Tactical Diagnostics",
            "description": "Where is value leaking?",
            "metrics": {
                "perfect_order_fulfillment": {
                    "label": "Perfect Order Fulfillment",
                    "value": _vary(91.3 * sf, ctx + "pof"), "unit": "%",
                    "target": 95.0, "trend": _vary(1.8, ctx + "pof_t", 0.3), "benchmark": ">90%",
                    "status": _status(_vary(91.3 * sf, ctx + "pof"), 95.0),
                    "scor_code": "RL.1.1",
                    "components": {
                        "otd": {"label": "On-Time Delivery", "value": _vary(95.2 * sf, ctx + "otd"), "unit": "%", "target": 95.0},
                        "in_full": {"label": "In-Full", "value": _vary(97.1 * sf, ctx + "if"), "unit": "%", "target": 97.0},
                        "damage_free": {"label": "Damage-Free", "value": _vary(99.2, ctx + "df"), "unit": "%", "target": 99.0},
                        "doc_accuracy": {"label": "Documentation", "value": _vary(98.5, ctx + "da"), "unit": "%", "target": 98.0},
                    },
                },
                "cash_to_cash": {
                    "label": "Cash-to-Cash Cycle",
                    "value": round(_vary(42, ctx + "c2c")), "unit": "days",
                    "target": 35, "trend": _vary(-3, ctx + "c2c_t", 0.3), "benchmark": "20-60 days",
                    "status": _status(_vary(42, ctx + "c2c"), 35, lower_is_better=True),
                    "scor_code": "AM.1.1",
                    "components": {
                        "dio": {"label": "Days Inventory (DIO)", "value": round(_vary(38, ctx + "dio")), "unit": "days", "target": 30},
                        "dso": {"label": "Days Sales (DSO)", "value": round(_vary(34, ctx + "dso")), "unit": "days", "target": 30},
                        "dpo": {"label": "Days Payable (DPO)", "value": round(_vary(30, ctx + "dpo")), "unit": "days", "target": 35},
                    },
                    "formula": "DIO + DSO - DPO",
                },
                "ofct": {
                    "label": "Order Fulfillment Cycle Time",
                    "value": _vary(4.2, ctx + "ofct"), "unit": "days",
                    "target": 3.5, "trend": _vary(-0.3, ctx + "ofct_t", 0.4), "benchmark": "1-30 days",
                    "status": _status(_vary(4.2, ctx + "ofct"), 3.5, lower_is_better=True),
                    "scor_code": "RS.1.1",
                    "components": {
                        "source_cycle": {"label": "Source Cycle", "value": _vary(1.8, ctx + "sc"), "unit": "days", "target": 1.5},
                        "make_cycle": {"label": "Make Cycle", "value": _vary(1.2, ctx + "mc"), "unit": "days", "target": 1.0},
                        "deliver_cycle": {"label": "Deliver Cycle", "value": _vary(1.2, ctx + "dc"), "unit": "days", "target": 1.0},
                    },
                    "formula": "Source + Make + Deliver",
                },
            },
        }

    # ========================================================================
    # Tier 3 — CORRECT (Operational)
    # ========================================================================

    def _tier3_correct(self, ctx, rf, pf):
        sf = rf.get("service", 1.0)
        vol = pf.get("volatility", 1.0)
        turns = pf.get("turns", 1.0)

        return {
            "label": "CORRECT \u2014 Operational Root Cause",
            "description": "What specific action fixes it?",
            "categories": {
                "demand_planning": {
                    "label": "Demand Planning",
                    "metrics": {
                        "wmape": {"label": "Forecast Accuracy (WMAPE)", "value": _vary(23.0 * vol, ctx + "wm"), "unit": "%", "target": 25.0, "trend": _vary(-2.1, ctx + "wm_t", 0.3), "agent": "ForecastAdjustmentTRM", "lower_is_better": True, "status": _status(_vary(23.0 * vol, ctx + "wm"), 25.0, lower_is_better=True)},
                        "forecast_bias": {"label": "Forecast Bias", "value": _vary(2.1, ctx + "fb"), "unit": "%", "target": 5.0, "trend": _vary(-0.5, ctx + "fb_t", 0.4), "agent": "ForecastAdjustmentTRM", "lower_is_better": True, "status": _status(abs(_vary(2.1, ctx + "fb")), 5.0, lower_is_better=True)},
                        "fva": {"label": "Forecast Value Added", "value": _vary(4.2, ctx + "fva"), "unit": "%", "trend": _vary(1.1, ctx + "fva_t", 0.3), "agent": "ForecastAdjustmentTRM", "status": "success"},
                    },
                },
                "inventory": {
                    "label": "Inventory",
                    "metrics": {
                        "inventory_turns": {"label": "Inventory Turns", "value": _vary(8.5 * turns, ctx + "it"), "unit": "x/yr", "target": 10.0, "trend": _vary(1.2, ctx + "it_t", 0.3), "agent": "SafetyStockTRM", "status": _status(_vary(8.5 * turns, ctx + "it"), 10.0)},
                        "dos": {"label": "Days of Supply", "value": round(_vary(28 / turns, ctx + "dos")), "unit": "days", "target": 30, "trend": _vary(-2.5, ctx + "dos_t", 0.3), "agent": "SafetyStockTRM", "status": "success"},
                        "excess_pct": {"label": "Excess Inventory", "value": _vary(3.2, ctx + "ex"), "unit": "%", "target": 5.0, "trend": _vary(-0.8, ctx + "ex_t", 0.3), "agent": "InventoryRebalancingTRM", "lower_is_better": True, "status": _status(_vary(3.2, ctx + "ex"), 5.0, lower_is_better=True)},
                        "ss_coverage": {"label": "Safety Stock Coverage", "value": _vary(95, ctx + "ss"), "unit": "%", "target": 100, "trend": _vary(2.0, ctx + "ss_t", 0.3), "agent": "SafetyStockTRM", "status": _status(_vary(95, ctx + "ss"), 90)},
                    },
                },
                "procurement": {
                    "label": "Supply / Procurement",
                    "metrics": {
                        "supplier_otd": {"label": "Supplier OTD", "value": _vary(94.2 * sf, ctx + "sotd"), "unit": "%", "target": 95.0, "trend": _vary(0.5, ctx + "sotd_t", 0.3), "agent": "POCreationTRM", "status": _status(_vary(94.2 * sf, ctx + "sotd"), 95.0)},
                        "material_availability": {"label": "Material Availability", "value": _vary(97.8 * sf, ctx + "ma"), "unit": "%", "target": 98.0, "trend": _vary(0.3, ctx + "ma_t", 0.3), "agent": "POCreationTRM", "status": _status(_vary(97.8 * sf, ctx + "ma"), 98.0)},
                        "po_cycle_time": {"label": "PO Cycle Time", "value": round(_vary(18, ctx + "poct")), "unit": "hrs", "target": 24, "trend": _vary(-2, ctx + "poct_t", 0.4), "agent": "POCreationTRM", "lower_is_better": True, "status": _status(_vary(18, ctx + "poct"), 24, lower_is_better=True)},
                    },
                },
                "manufacturing": {
                    "label": "Manufacturing",
                    "metrics": {
                        "oee": {"label": "OEE", "value": _vary(87.0, ctx + "oee"), "unit": "%", "target": 85.0, "trend": _vary(1.5, ctx + "oee_t", 0.3), "agent": "MOExecutionTRM", "status": _status(_vary(87.0, ctx + "oee"), 85.0)},
                        "schedule_adherence": {"label": "Schedule Adherence", "value": _vary(95.2 * sf, ctx + "sa"), "unit": "%", "target": 95.0, "trend": _vary(0.8, ctx + "sa_t", 0.3), "agent": "MOExecutionTRM", "status": _status(_vary(95.2 * sf, ctx + "sa"), 95.0)},
                        "fpy": {"label": "First Pass Yield", "value": _vary(96.5, ctx + "fpy"), "unit": "%", "target": 95.0, "trend": _vary(0.3, ctx + "fpy_t", 0.3), "agent": "QualityDispositionTRM", "status": _status(_vary(96.5, ctx + "fpy"), 95.0)},
                        "capacity_utilization": {"label": "Capacity Utilization", "value": _vary(87, ctx + "cu"), "unit": "%", "target": 85.0, "trend": _vary(2.0, ctx + "cu_t", 0.3), "agent": "MOExecutionTRM", "status": _status(_vary(87, ctx + "cu"), 85.0)},
                    },
                },
                "fulfillment": {
                    "label": "Fulfillment / ATP",
                    "metrics": {
                        "otif": {"label": "OTIF", "value": _vary(95.5 * sf, ctx + "otif"), "unit": "%", "target": 95.0, "trend": _vary(0.8, ctx + "otif_t", 0.3), "agent": "TOExecutionTRM", "status": _status(_vary(95.5 * sf, ctx + "otif"), 95.0)},
                        "promise_accuracy": {"label": "Promise Accuracy", "value": _vary(97.2 * sf, ctx + "pa"), "unit": "%", "target": 98.0, "trend": _vary(0.5, ctx + "pa_t", 0.3), "agent": "ATPExecutorTRM", "status": _status(_vary(97.2 * sf, ctx + "pa"), 98.0)},
                        "exception_rate": {"label": "Exception Rate", "value": _vary(4.1, ctx + "er"), "unit": "%", "target": 5.0, "trend": _vary(-0.6, ctx + "er_t", 0.3), "agent": "OrderTrackingTRM", "lower_is_better": True, "status": _status(_vary(4.1, ctx + "er"), 5.0, lower_is_better=True)},
                        "aatp_utilization": {"label": "AATP Utilization", "value": _vary(78, ctx + "aatp"), "unit": "%", "target": 80.0, "trend": _vary(3.0, ctx + "aatp_t", 0.3), "agent": "ATPExecutorTRM", "status": _status(_vary(78, ctx + "aatp"), 80.0)},
                    },
                },
            },
        }

    # ========================================================================
    # Tier 4 — AI-as-Labor
    # ========================================================================

    def _tier4_agent(self, ctx):
        trm_agents = [
            {"name": "ATPExecutorTRM", "phase": "SENSE", "score": 22, "touchless": 94, "override": 6, "urgency": 0.12},
            {"name": "OrderTrackingTRM", "phase": "SENSE", "score": 18, "touchless": 88, "override": 12, "urgency": 0.25},
            {"name": "POCreationTRM", "phase": "ACQUIRE", "score": 15, "touchless": 82, "override": 18, "urgency": 0.31},
            {"name": "SubcontractingTRM", "phase": "ACQUIRE", "score": 10, "touchless": 72, "override": 28, "urgency": 0.35},
            {"name": "SafetyStockTRM", "phase": "ASSESS", "score": 19, "touchless": 91, "override": 9, "urgency": 0.08},
            {"name": "ForecastAdjustmentTRM", "phase": "ASSESS", "score": 11, "touchless": 79, "override": 21, "urgency": 0.22},
            {"name": "QualityDispositionTRM", "phase": "PROTECT", "score": 25, "touchless": 95, "override": 5, "urgency": 0.05},
            {"name": "MaintenanceSchedulingTRM", "phase": "PROTECT", "score": 14, "touchless": 85, "override": 15, "urgency": 0.15},
            {"name": "MOExecutionTRM", "phase": "BUILD", "score": 16, "touchless": 83, "override": 17, "urgency": 0.28},
            {"name": "TOExecutionTRM", "phase": "BUILD", "score": 13, "touchless": 80, "override": 20, "urgency": 0.20},
            {"name": "InventoryRebalancingTRM", "phase": "REFLECT", "score": 12, "touchless": 76, "override": 24, "urgency": 0.18},
        ]
        # Vary scores per context
        for agent in trm_agents:
            agent["score"] = round(_vary(agent["score"], ctx + agent["name"] + "s", 0.15))
            agent["touchless"] = round(_vary(agent["touchless"], ctx + agent["name"] + "t", 0.05))
            agent["override"] = 100 - agent["touchless"]
            agent["urgency"] = round(_vary(agent["urgency"], ctx + agent["name"] + "u", 0.2), 2)

        avg_touchless = round(sum(a["touchless"] for a in trm_agents) / len(trm_agents), 1)
        avg_score = round(sum(a["score"] for a in trm_agents) / len(trm_agents), 1)
        avg_override = round(100 - avg_touchless, 1)
        max_urgency = max(a["urgency"] for a in trm_agents)
        mean_urgency = round(sum(a["urgency"] for a in trm_agents) / len(trm_agents), 2)

        return {
            "label": "AI-as-Labor Performance",
            "description": "How well are agents producing outcomes?",
            "metrics": {
                "touchless_rate": {"label": "Touchless Rate", "value": avg_touchless, "unit": "%", "target": 80, "trend": 3.0, "status": _status(avg_touchless, 80)},
                "agent_score": {"label": "Agent Score", "value": avg_score, "unit": "", "target": 10, "trend": 5.0, "status": _status(avg_score, 10)},
                "override_rate": {"label": "Override Rate", "value": avg_override, "unit": "%", "target": 20, "trend": -2.0, "status": _status(avg_override, 20, lower_is_better=True)},
                "hive_stress": {"label": "Hive Stress", "value": 12, "unit": "%", "target": 15, "trend": -1.0, "status": "success"},
                "cdc_triggers_per_day": {"label": "CDC Triggers/Day", "value": 2.1, "unit": "", "target": 3.0, "trend": -0.3, "status": "success"},
            },
            "hive_metrics": {
                "mean_urgency": mean_urgency,
                "max_urgency": max_urgency,
                "signal_bus_activity": 18,
                "conflict_rate": 3.2,
                "stress_index": 12,
            },
            "per_trm": trm_agents,
        }

    # ========================================================================
    # Trend data
    # ========================================================================

    def _trend_data(self, ctx, rf):
        sf = rf.get("service", 1.0)
        periods = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
        data = []
        for i, p in enumerate(periods):
            progress = 0.7 + (i / len(periods)) * 0.3  # gradual improvement
            data.append({
                "period": p,
                "pof": round(88 * sf + i * 0.5, 1),
                "c2c": round(48 - i * 0.8, 0),
                "ofct": round(5.0 - i * 0.1, 1),
                "touchless": round(60 + i * 3, 0),
                "otif": round(91 * sf + i * 0.6, 1),
                "inventory_turns": round(7.5 + i * 0.15, 1),
                "wmape": round(28 - i * 0.7, 1),
                "agent_score": round(8 + i * 1.2, 0),
            })
        return data
