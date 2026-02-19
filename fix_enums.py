#!/usr/bin/env python3
"""
Fix unnamed PostgreSQL Enum columns by adding name= parameters.
"""
import re
import sys
from pathlib import Path

# Mapping of Enum types to their canonical names (lowercase, underscore-separated)
ENUM_NAME_MAP = {
    'CycleType': 'cycle_type',
    'CycleStatus': 'cycle_status',
    'SnapshotTier': 'snapshot_tier',
    'SnapshotType': 'snapshot_type',
    'DeltaEntityType': 'delta_entity_type',
    'DeltaOperation': 'delta_operation',
    'PolicySource': 'policy_source',
    'CommitStatus': 'commit_status',
    'LayerName': 'layer_name',
    'LayerMode': 'layer_mode',
    'AuditAction': 'audit_action',
    'AuditStatus': 'audit_status',
    'PlatformType': 'platform_type',
    'DecisionCategory': 'decision_category',
    'DecisionAction': 'decision_action',
    'DecisionPriority': 'decision_priority',
    'DecisionStatus': 'decision_status',
    'TenantStatus': 'tenant_status',
    'BillingPlan': 'billing_plan',
    'PlanStatus': 'plan_status',
    'SSOProviderType': 'sso_provider_type',
    'JobStatus': 'job_status',
    'SyncDirection': 'sync_direction',
    'NodeMasterType': 'node_master_type',
    'TemplateCategory': 'template_category',
    'TemplateIndustry': 'template_industry',
    'WorkflowStatus': 'workflow_status',
    'WorkflowTrigger': 'workflow_trigger',
    'ActionStatus': 'action_status',
    'ActionType': 'action_type',
}

def fix_enum_column(line: str) -> str:
    """Add name= parameter to Enum column if missing."""
    # Pattern: Column(Enum(EnumType), ...other params...)
    # We want to insert name="enumtype" after the EnumType
    pattern = r'Column\(Enum\(([A-Za-z_]+)\),'

    match = re.search(pattern, line)
    if match:
        enum_type = match.group(1)
        enum_name = ENUM_NAME_MAP.get(enum_type, enum_type.lower())

        # Replace Enum(EnumType), with Enum(EnumType, name="enumname"),
        old_str = f'Enum({enum_type}),'
        new_str = f'Enum({enum_type}, name="{enum_name}"),'
        line = line.replace(old_str, new_str)

    return line

def fix_file(filepath: Path) -> int:
    """Fix all unnamed enums in a file. Returns number of fixes made."""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    fixed_count = 0
    new_lines = []

    for line in lines:
        # Check if line has Column(Enum without name=
        if 'Column(Enum' in line and 'name=' not in line:
            new_line = fix_enum_column(line)
            if new_line != line:
                fixed_count += 1
                print(f"  Fixed: {filepath.name}:{lines.index(line)+1}")
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    if fixed_count > 0:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)

    return fixed_count

def main():
    models_dir = Path('backend/app/models')

    if not models_dir.exists():
        print(f"Error: {models_dir} not found")
        sys.exit(1)

    total_fixed = 0
    files_with_enums = [
        'planning_cycle.py',
        'planning_cascade.py',
        'workflow.py',
        'planning_decision.py',
        'template.py',
        'tenant.py',
        'sync_job.py',
        'audit_log.py',
        'supply_plan.py',
        'supply_chain_config.py',
        'sso_provider.py',
        'notification.py',
    ]

    print("Fixing unnamed PostgreSQL Enum columns...")
    print()

    for filename in files_with_enums:
        filepath = models_dir / filename
        if filepath.exists():
            print(f"Processing {filename}...")
            count = fix_file(filepath)
            total_fixed += count
            if count > 0:
                print(f"  ✓ Fixed {count} enum(s)")
            print()

    print(f"\n✓ Total fixes: {total_fixed}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
