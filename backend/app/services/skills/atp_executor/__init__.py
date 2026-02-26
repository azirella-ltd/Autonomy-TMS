from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="atp_executor",
    display_name="ATP Executor",
    tier=SkillTier.DETERMINISTIC,
    trm_type="atp_executor",
    description="AATP priority-based consumption — fully deterministic, no LLM needed",
))
