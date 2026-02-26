from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="subcontracting",
    display_name="Subcontracting",
    tier=SkillTier.SONNET,
    trm_type="subcontracting",
    description="Make-vs-buy and external manufacturing routing decisions",
))
