from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="quality_disposition",
    display_name="Quality Disposition",
    tier=SkillTier.SONNET,
    trm_type="quality_disposition",
    description="Quality hold/release/rework/scrap decisions with vendor history",
))
