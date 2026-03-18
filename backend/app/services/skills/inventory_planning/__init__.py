from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="inventory_planning",
    display_name="Inventory Planning",
    tier=SkillTier.SONNET,
    trm_type="inventory_planning",
    description="Inventory planning agent: adjusts safety stock targets, reorder points, and order-up-to levels based on supplier risk, capital constraints, product lifecycle, and RCCP capacity signals",
))
