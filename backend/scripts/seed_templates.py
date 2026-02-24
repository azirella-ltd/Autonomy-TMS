#!/usr/bin/env python3
"""
Seed Templates Script
Phase 6 Sprint 4: User Experience Enhancements

Seeds the database with 25+ distribution templates and 10+ scenario templates.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.template import Template, TemplateCategory, TemplateIndustry, TemplateDifficulty
from app.models.user import User

# Distribution Templates (25+)
DISTRIBUTION_TEMPLATES = [
    # Retail Templates (8)
    {
        "name": "Steady Retail Demand",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.BEGINNER,
        "description": "Constant demand with minimal variation. Perfect for learning basics.",
        "short_description": "Constant demand, minimal variation",
        "configuration": {
            "distribution_type": "normal",
            "parameters": {"mean": 100, "std": 5}
        },
        "tags": ["steady", "predictable", "beginner"],
        "icon": "TrendingFlat",
        "color": "#4caf50",
        "is_featured": True
    },
    {
        "name": "Seasonal Retail Pattern",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Quarterly seasonal peaks and troughs typical of retail. High demand in Q4 holidays, low in Q1/Q2.",
        "short_description": "Quarterly peaks and troughs",
        "configuration": {
            "distribution_type": "seasonal",
            "parameters": {"base": 100, "amplitude": 50, "period": 13}
        },
        "tags": ["seasonal", "retail", "holidays"],
        "icon": "ShowChart",
        "color": "#2196f3",
        "is_featured": True
    },
    {
        "name": "Promotional Spike",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Random promotional events causing demand spikes. Models flash sales and marketing campaigns.",
        "short_description": "Random promotional events",
        "configuration": {
            "distribution_type": "poisson_spike",
            "parameters": {"base": 80, "spike_rate": 0.1, "spike_magnitude": 200}
        },
        "tags": ["promotion", "spikes", "marketing"],
        "icon": "LocalOffer",
        "color": "#ff9800"
    },
    {
        "name": "Weekend Peak Retail",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.BEGINNER,
        "description": "Weekly pattern with higher weekend demand. Common for consumer retail.",
        "short_description": "Weekly peaks on weekends",
        "configuration": {
            "distribution_type": "weekly_cycle",
            "parameters": {"weekday_mean": 70, "weekend_mean": 130, "std": 10}
        },
        "tags": ["weekly", "weekend", "cycle"],
        "icon": "DateRange",
        "color": "#9c27b0"
    },
    {
        "name": "Black Friday Rush",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Extreme spike for Black Friday/Cyber Monday followed by normalization.",
        "short_description": "Extreme holiday spike",
        "configuration": {
            "distribution_type": "event_spike",
            "parameters": {"base": 100, "event_week": 48, "spike_multiplier": 5, "duration": 2}
        },
        "tags": ["black friday", "extreme", "holiday"],
        "icon": "LocalMall",
        "color": "#f44336"
    },
    {
        "name": "Back-to-School Season",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "August-September surge for school supplies and clothing.",
        "short_description": "Late summer surge",
        "configuration": {
            "distribution_type": "seasonal_event",
            "parameters": {"base": 90, "peak_week": 35, "peak_magnitude": 180, "duration": 4}
        },
        "tags": ["back-to-school", "seasonal", "education"],
        "icon": "School",
        "color": "#3f51b5"
    },
    {
        "name": "Flash Sale Pattern",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Unpredictable short-duration spikes from flash sales. High volatility.",
        "short_description": "Unpredictable short spikes",
        "configuration": {
            "distribution_type": "exponential_spike",
            "parameters": {"base": 75, "spike_lambda": 0.15, "spike_scale": 150}
        },
        "tags": ["flash sale", "volatile", "unpredictable"],
        "icon": "FlashOn",
        "color": "#ffc107"
    },
    {
        "name": "Clearance Decline",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Declining demand curve for end-of-season clearance items.",
        "short_description": "Declining clearance demand",
        "configuration": {
            "distribution_type": "exponential_decay",
            "parameters": {"initial": 150, "decay_rate": 0.15, "floor": 20}
        },
        "tags": ["clearance", "decline", "end-of-season"],
        "icon": "TrendingDown",
        "color": "#795548"
    },

    # Manufacturing Templates (6)
    {
        "name": "Batch Production Cycle",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Periodic batch orders with lead time gaps. Typical for manufacturing runs.",
        "short_description": "Periodic batch orders",
        "configuration": {
            "distribution_type": "batch_cycle",
            "parameters": {"batch_size": 500, "cycle_length": 4, "variance": 50}
        },
        "tags": ["batch", "cycle", "production"],
        "icon": "Inventory",
        "color": "#607d8b"
    },
    {
        "name": "Continuous Production",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.BEGINNER,
        "description": "Steady continuous demand for high-volume manufacturing.",
        "short_description": "Steady continuous flow",
        "configuration": {
            "distribution_type": "normal",
            "parameters": {"mean": 200, "std": 15}
        },
        "tags": ["continuous", "steady", "high-volume"],
        "icon": "Sync",
        "color": "#4caf50"
    },
    {
        "name": "Just-in-Time Demand",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Tight JIT pattern with minimal inventory buffers. Very low lead time tolerance.",
        "short_description": "Tight JIT pattern",
        "configuration": {
            "distribution_type": "deterministic",
            "parameters": {"quantity": 100, "tolerance": 2}
        },
        "tags": ["jit", "lean", "tight"],
        "icon": "AccessTime",
        "color": "#f44336"
    },
    {
        "name": "Production Ramp-Up",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Gradual increase in production volume. New product launch scenario.",
        "short_description": "Gradual volume increase",
        "configuration": {
            "distribution_type": "linear_growth",
            "parameters": {"initial": 50, "growth_rate": 5, "max": 200}
        },
        "tags": ["ramp-up", "growth", "launch"],
        "icon": "TrendingUp",
        "color": "#8bc34a"
    },
    {
        "name": "Maintenance Shutdown",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Periodic zero-demand weeks for planned maintenance shutdowns.",
        "short_description": "Periodic maintenance gaps",
        "configuration": {
            "distribution_type": "maintenance_cycle",
            "parameters": {"normal_demand": 150, "shutdown_frequency": 12, "shutdown_duration": 1}
        },
        "tags": ["maintenance", "shutdown", "cycle"],
        "icon": "Build",
        "color": "#ff5722"
    },
    {
        "name": "Assembly Line Demand",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Stable demand with occasional line changeovers causing brief gaps.",
        "short_description": "Stable with changeovers",
        "configuration": {
            "distribution_type": "stable_with_gaps",
            "parameters": {"base": 120, "std": 8, "gap_frequency": 0.05}
        },
        "tags": ["assembly", "changeover", "stable"],
        "icon": "Precision Manufacturing",
        "color": "#00bcd4"
    },

    # Logistics Templates (5)
    {
        "name": "Express Shipping Volatility",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.LOGISTICS,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "High volatility from last-minute express orders. Large variance.",
        "short_description": "High volatility express",
        "configuration": {
            "distribution_type": "lognormal",
            "parameters": {"mu": 4.5, "sigma": 0.8}
        },
        "tags": ["express", "volatile", "last-minute"],
        "icon": "LocalShipping",
        "color": "#ff5722"
    },
    {
        "name": "Standard Freight Pattern",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.LOGISTICS,
        "difficulty": TemplateDifficulty.BEGINNER,
        "description": "Predictable standard freight with consistent lead times.",
        "short_description": "Predictable standard freight",
        "configuration": {
            "distribution_type": "normal",
            "parameters": {"mean": 180, "std": 20}
        },
        "tags": ["freight", "standard", "predictable"],
        "icon": "LocalShipping",
        "color": "#4caf50"
    },
    {
        "name": "Bulk Shipment Cycles",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.LOGISTICS,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Large infrequent bulk shipments. Low frequency, high volume.",
        "short_description": "Infrequent bulk shipments",
        "configuration": {
            "distribution_type": "bulk_cycle",
            "parameters": {"bulk_size": 1000, "frequency": 8, "variance": 100}
        },
        "tags": ["bulk", "infrequent", "large"],
        "icon": "Inventory2",
        "color": "#9c27b0"
    },
    {
        "name": "Cross-Dock Flow",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.LOGISTICS,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Continuous flow through cross-dock facility with minimal storage.",
        "short_description": "Continuous cross-dock flow",
        "configuration": {
            "distribution_type": "uniform",
            "parameters": {"min": 140, "max": 160}
        },
        "tags": ["cross-dock", "flow", "continuous"],
        "icon": "CompareArrows",
        "color": "#00bcd4"
    },
    {
        "name": "Port Congestion",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.LOGISTICS,
        "difficulty": TemplateDifficulty.EXPERT,
        "description": "Random delays from port congestion. Unpredictable timing.",
        "short_description": "Unpredictable port delays",
        "configuration": {
            "distribution_type": "delayed_poisson",
            "parameters": {"rate": 100, "delay_prob": 0.3, "delay_range": [1, 5]}
        },
        "tags": ["port", "delays", "congestion"],
        "icon": "DirectionsBoat",
        "color": "#f44336"
    },

    # Healthcare Templates (3)
    {
        "name": "Hospital Steady Demand",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.HEALTHCARE,
        "difficulty": TemplateDifficulty.BEGINNER,
        "description": "Consistent hospital supply needs with minimal variation.",
        "short_description": "Consistent hospital needs",
        "configuration": {
            "distribution_type": "normal",
            "parameters": {"mean": 250, "std": 15}
        },
        "tags": ["hospital", "steady", "medical"],
        "icon": "LocalHospital",
        "color": "#4caf50"
    },
    {
        "name": "Flu Season Surge",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.HEALTHCARE,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Winter flu season surge in medical supplies.",
        "short_description": "Winter season surge",
        "configuration": {
            "distribution_type": "seasonal",
            "parameters": {"base": 200, "amplitude": 100, "peak_week": 6}
        },
        "tags": ["flu", "seasonal", "surge"],
        "icon": "Sick",
        "color": "#ff9800"
    },
    {
        "name": "Emergency Stockpile",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.HEALTHCARE,
        "difficulty": TemplateDifficulty.EXPERT,
        "description": "Rare but massive emergency demand spikes. Pandemic response.",
        "short_description": "Rare emergency spikes",
        "configuration": {
            "distribution_type": "rare_extreme",
            "parameters": {"base": 150, "event_prob": 0.01, "event_magnitude": 2000}
        },
        "tags": ["emergency", "pandemic", "extreme"],
        "icon": "Warning",
        "color": "#f44336"
    },

    # Technology Templates (3)
    {
        "name": "Product Launch Demand",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.TECHNOLOGY,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Initial launch spike followed by gradual stabilization.",
        "short_description": "Launch spike to stable",
        "configuration": {
            "distribution_type": "launch_curve",
            "parameters": {"launch_demand": 500, "steady_demand": 150, "decay_rate": 0.2}
        },
        "tags": ["launch", "tech", "new product"],
        "icon": "RocketLaunch",
        "color": "#2196f3"
    },
    {
        "name": "Component Shortage",
        "category": TemplateCategory.DISTRIBUTION,
        "industry": TemplateIndustry.TECHNOLOGY,
        "difficulty": TemplateDifficulty.EXPERT,
        "description": "Supply constraints causing demand suppression and backlog.",
        "short_description": "Constrained supply",
        "configuration": {
            "distribution_type": "constrained",
            "parameters": {"demand_mean": 200, "supply_limit": 120, "backlog_decay": 0.1}
        },
        "tags": ["shortage", "constrained", "backlog"],
        "icon": "Report",
        "color": "#f44336"
    }
]

# Scenario Templates (10+)
SCENARIO_TEMPLATES = [
    {
        "name": "Classic Beer Game",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.GENERAL,
        "difficulty": TemplateDifficulty.BEGINNER,
        "description": "Traditional 4-echelon supply chain simulation with retailer, wholesaler, distributor, and factory. Perfect for learning bullwhip effect.",
        "short_description": "Traditional 4-echelon simulation",
        "configuration": {
            "supply_chain_config_id": 1,
            "num_players": 4,
            "initial_inventory": 12,
            "initial_orders": 4,
            "holding_cost": 0.5,
            "backlog_cost": 1.0,
            "demand_pattern": "steady"
        },
        "tags": ["classic", "4-echelon", "beginner"],
        "icon": "Sports",
        "color": "#4caf50",
        "is_featured": True
    },
    {
        "name": "Retail Supply Chain",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Multi-store retail network with regional distribution center. Seasonal demand patterns.",
        "short_description": "Multi-store retail network",
        "configuration": {
            "supply_chain_config_id": 2,
            "num_players": 6,
            "demand_pattern": "seasonal",
            "features": ["stochastic", "multi_tier"]
        },
        "tags": ["retail", "multi-store", "seasonal"],
        "icon": "Store",
        "color": "#2196f3",
        "is_featured": True
    },
    {
        "name": "Manufacturing Assembly Line",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.MANUFACTURING,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Complex assembly with multiple component suppliers and Bill of Materials transformations.",
        "short_description": "Multi-component assembly",
        "configuration": {
            "supply_chain_config_id": 3,
            "num_players": 8,
            "features": ["bom", "multi_tier", "ai_agents"],
            "demand_pattern": "batch"
        },
        "tags": ["manufacturing", "assembly", "bom"],
        "icon": "PrecisionManufacturing",
        "color": "#ff9800"
    },
    {
        "name": "Global Logistics Network",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.LOGISTICS,
        "difficulty": TemplateDifficulty.EXPERT,
        "description": "International supply chain with multiple shipping modes and long lead times.",
        "short_description": "International multi-mode",
        "configuration": {
            "supply_chain_config_id": 4,
            "num_players": 10,
            "features": ["long_lead_times", "multi_mode", "stochastic"],
            "lead_time_multiplier": 3
        },
        "tags": ["global", "logistics", "international"],
        "icon": "Public",
        "color": "#9c27b0"
    },
    {
        "name": "Pharmaceutical Distribution",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.HEALTHCARE,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "Temperature-controlled pharmaceutical supply chain with compliance requirements.",
        "short_description": "Pharma cold chain",
        "configuration": {
            "supply_chain_config_id": 5,
            "num_players": 5,
            "features": ["compliance", "temperature_controlled"],
            "expiration_tracking": True
        },
        "tags": ["pharma", "cold chain", "compliance"],
        "icon": "Medication",
        "color": "#00bcd4"
    },
    {
        "name": "E-Commerce Fulfillment",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Fast-paced e-commerce with multiple fulfillment centers and same-day delivery.",
        "short_description": "Fast e-commerce fulfillment",
        "configuration": {
            "supply_chain_config_id": 6,
            "num_players": 5,
            "demand_pattern": "volatile",
            "features": ["fast_shipping", "multi_channel"],
            "service_level_target": 0.98
        },
        "tags": ["e-commerce", "fast", "omnichannel"],
        "icon": "ShoppingCart",
        "color": "#ff5722"
    },
    {
        "name": "Automotive Parts Network",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.AUTOMOTIVE,
        "difficulty": TemplateDifficulty.EXPERT,
        "description": "Just-in-Time automotive assembly with hundreds of parts and tight tolerances.",
        "short_description": "JIT automotive assembly",
        "configuration": {
            "supply_chain_config_id": 7,
            "num_players": 12,
            "features": ["jit", "complex_bom", "ai_agents"],
            "inventory_target": "minimal"
        },
        "tags": ["automotive", "jit", "complex"],
        "icon": "DirectionsCar",
        "color": "#607d8b"
    },
    {
        "name": "Food Distribution Chain",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.FOOD_BEVERAGE,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Perishable goods distribution with expiration tracking and waste management.",
        "short_description": "Perishable goods chain",
        "configuration": {
            "supply_chain_config_id": 8,
            "num_players": 6,
            "features": ["perishable", "expiration", "waste_tracking"],
            "shelf_life": 14
        },
        "tags": ["food", "perishable", "expiration"],
        "icon": "Restaurant",
        "color": "#8bc34a"
    },
    {
        "name": "Electronics Supply Chain",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.TECHNOLOGY,
        "difficulty": TemplateDifficulty.ADVANCED,
        "description": "High-tech electronics with rapid obsolescence and component dependencies.",
        "short_description": "High-tech electronics",
        "configuration": {
            "supply_chain_config_id": 9,
            "num_players": 8,
            "features": ["obsolescence", "component_dependencies", "rapid_change"],
            "product_lifecycle": "short"
        },
        "tags": ["electronics", "tech", "obsolescence"],
        "icon": "Computer",
        "color": "#3f51b5"
    },
    {
        "name": "Disaster Response Supply Chain",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.HEALTHCARE,
        "difficulty": TemplateDifficulty.EXPERT,
        "description": "Emergency response logistics with unpredictable demand spikes and resource constraints.",
        "short_description": "Emergency response logistics",
        "configuration": {
            "supply_chain_config_id": 10,
            "num_players": 7,
            "demand_pattern": "emergency",
            "features": ["unpredictable", "resource_constrained", "priority_routing"],
            "response_time_critical": True
        },
        "tags": ["disaster", "emergency", "humanitarian"],
        "icon": "LocalFireDepartment",
        "color": "#f44336"
    },
    {
        "name": "Seasonal Fashion Retail",
        "category": TemplateCategory.SCENARIO,
        "industry": TemplateIndustry.RETAIL,
        "difficulty": TemplateDifficulty.INTERMEDIATE,
        "description": "Fast fashion with seasonal collections, rapid product turnover, and trend sensitivity.",
        "short_description": "Fast fashion seasonal",
        "configuration": {
            "supply_chain_config_id": 11,
            "num_players": 6,
            "demand_pattern": "trend_based",
            "features": ["seasonal", "fast_turnover", "trend_sensitive"],
            "collection_cycles": 6
        },
        "tags": ["fashion", "seasonal", "trends"],
        "icon": "Checkroom",
        "color": "#e91e63"
    }
]


def seed_templates():
    """Seed database with templates"""
    db = SessionLocal()

    try:
        # Get or create system admin user
        admin = db.query(User).filter(User.email == "systemadmin@autonomy.ai").first()
        if not admin:
            print("Error: System admin user not found. Please run db bootstrap first.")
            return

        print(f"Seeding templates as user: {admin.email}")

        # Clear existing templates (optional - comment out if you want to keep existing)
        # db.query(Template).delete()
        # db.commit()

        # Seed distribution templates
        print(f"\nSeeding {len(DISTRIBUTION_TEMPLATES)} distribution templates...")
        for template_data in DISTRIBUTION_TEMPLATES:
            # Generate slug
            from python_slugify import slugify
            slug = slugify(template_data["name"])

            # Check if template already exists
            existing = db.query(Template).filter(Template.slug == slug).first()
            if existing:
                print(f"  - Skipping existing: {template_data['name']}")
                continue

            template = Template(
                **template_data,
                slug=slug,
                created_by=admin.id
            )
            db.add(template)
            print(f"  + Added: {template_data['name']}")

        db.commit()

        # Seed scenario templates
        print(f"\nSeeding {len(SCENARIO_TEMPLATES)} scenario templates...")
        for template_data in SCENARIO_TEMPLATES:
            # Generate slug
            slug = slugify(template_data["name"])

            # Check if template already exists
            existing = db.query(Template).filter(Template.slug == slug).first()
            if existing:
                print(f"  - Skipping existing: {template_data['name']}")
                continue

            template = Template(
                **template_data,
                slug=slug,
                created_by=admin.id
            )
            db.add(template)
            print(f"  + Added: {template_data['name']}")

        db.commit()

        # Print summary
        total_templates = db.query(Template).count()
        distribution_count = db.query(Template).filter(Template.category == TemplateCategory.DISTRIBUTION).count()
        scenario_count = db.query(Template).filter(Template.category == TemplateCategory.SCENARIO).count()
        featured_count = db.query(Template).filter(Template.is_featured == True).count()

        print("\n" + "=" * 80)
        print("Template Seeding Complete!")
        print("=" * 80)
        print(f"Total templates in database: {total_templates}")
        print(f"  - Distribution templates: {distribution_count}")
        print(f"  - Scenario templates: {scenario_count}")
        print(f"  - Featured templates: {featured_count}")
        print("=" * 80)

    except Exception as e:
        print(f"Error seeding templates: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_templates()
