from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="to_execution",
    display_name="TO Execution",
    tier=SkillTier.HAIKU,
    trm_type="to_execution",
    description="Transfer order release, consolidation, expedite, and deferral",
))
