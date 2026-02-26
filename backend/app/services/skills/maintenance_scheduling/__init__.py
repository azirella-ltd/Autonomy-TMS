from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="maintenance_scheduling",
    display_name="Maintenance Scheduling",
    tier=SkillTier.SONNET,
    trm_type="maintenance_scheduling",
    description="Preventive maintenance scheduling, deferral, and outsourcing decisions",
))
