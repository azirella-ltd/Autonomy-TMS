from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="supply_planning",
    display_name="Supply Planning",
    tier=SkillTier.SONNET,
    trm_type="supply_planning",
    description="Supply planning agent: generates supply plans (PO/TO/MO requirements), evaluates sourcing options, lot sizing, and capacity feasibility for the tactical planning layer",
))
