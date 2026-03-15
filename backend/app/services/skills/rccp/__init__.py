from ..base_skill import SkillDefinition, SkillTier, register_skill

skill = register_skill(SkillDefinition(
    name="rccp",
    display_name="RCCP",
    tier=SkillTier.SONNET,
    trm_type="rccp",
    description="RCCP agent: validates MPS feasibility against aggregate capacity, recommends overtime/levelling/subcontracting, detects chronic overload patterns for S&OP escalation",
))
