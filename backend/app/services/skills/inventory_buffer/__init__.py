from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="inventory_buffer",
    display_name="Inventory Buffer",
    tier=SkillTier.HAIKU,
    trm_type="inventory_buffer",
    description="Buffer multiplier adjustment on baseline safety stock",
))
