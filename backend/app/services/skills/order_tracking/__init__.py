from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="order_tracking",
    display_name="Order Tracking",
    tier=SkillTier.DETERMINISTIC,
    trm_type="order_tracking",
    description="Order exception detection — rule-based threshold checks, no LLM needed",
))
