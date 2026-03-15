from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="demand_planning",
    display_name="Demand Planning",
    tier=SkillTier.SONNET,
    trm_type="demand_planning",
    description="Demand planning agent: adjusts consensus demand plan for novel signals including NPI launches, competitor events, end-of-life transitions, promotion uplifts, and human directives",
))
