from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="sop_adjustment",
    display_name="S&OP Adjustment",
    tier=SkillTier.SONNET,
    trm_type="sop_adjustment",
    description="S&OP adjustment agent: applies bounded real-time corrections to θ* policy parameters between weekly DE runs for time-sensitive signals (supplier disruptions, executive directives, RCCP chronic overload)",
))
