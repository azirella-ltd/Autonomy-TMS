from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="forecast_adjustment",
    display_name="Forecast Adjustment",
    tier=SkillTier.SONNET,
    trm_type="forecast_adjustment",
    description="Signal-driven forecast adjustment from email, voice, and market data",
))
