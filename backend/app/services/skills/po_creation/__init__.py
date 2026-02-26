from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="po_creation",
    display_name="PO Creation",
    tier=SkillTier.HAIKU,
    trm_type="po_creation",
    description="Purchase order timing and quantity decisions",
))
