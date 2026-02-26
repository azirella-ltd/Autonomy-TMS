from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="inventory_rebalancing",
    display_name="Inventory Rebalancing",
    tier=SkillTier.HAIKU,
    trm_type="inventory_rebalancing",
    description="Cross-location inventory transfer recommendations",
))
