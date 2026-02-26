from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="mo_execution",
    display_name="MO Execution",
    tier=SkillTier.SONNET,
    trm_type="mo_execution",
    description="Manufacturing order release, sequencing, expedite, and deferral",
))
