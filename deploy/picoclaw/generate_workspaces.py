#!/usr/bin/env python3
"""
PicoClaw Workspace Generator

Generates per-site PicoClaw workspace directories from a supply chain config.
Each workspace contains the deterministic heartbeat script, identity card,
config, and optional LLM skill for human queries.

Usage:
    python deploy/picoclaw/generate_workspaces.py --config-id 1
    python deploy/picoclaw/generate_workspaces.py --config-id 1 --api-base http://localhost:8000
    python deploy/picoclaw/generate_workspaces.py --site-ids 1,2,3
"""

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from string import Template

import requests

SCRIPT_DIR = Path(__file__).parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"
OUTPUT_DIR = SCRIPT_DIR / "workspaces"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate PicoClaw workspaces")
    parser.add_argument("--config-id", type=int, default=1,
                        help="Supply chain config ID (default: 1)")
    parser.add_argument("--site-ids", type=str, default=None,
                        help="Comma-separated site IDs (overrides --config-id)")
    parser.add_argument("--api-base", type=str,
                        default=os.getenv("AUTONOMY_API_BASE", "http://localhost:8000"),
                        help="Autonomy API base URL")
    parser.add_argument("--admin-email", type=str,
                        default=os.getenv("ADMIN_EMAIL", "systemadmin@autonomy.ai"),
                        help="Admin email for authentication")
    parser.add_argument("--admin-password", type=str,
                        default=os.getenv("ADMIN_PASSWORD", "Autonomy@2025"),
                        help="Admin password")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: deploy/picoclaw/workspaces/)")
    parser.add_argument("--llm-api-base", type=str,
                        default=os.getenv("LLM_API_BASE", "http://vllm:8000/v1"),
                        help="LLM API base for human queries")
    parser.add_argument("--llm-model", type=str,
                        default=os.getenv("LLM_MODEL_NAME", "qwen3-8b"),
                        help="LLM model name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be generated without writing")
    return parser.parse_args()


def authenticate(api_base: str, email: str, password: str) -> str:
    """Authenticate and return JWT token."""
    resp = requests.post(
        f"{api_base}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("access_token") or data.get("token")


def get_sites(api_base: str, token: str, config_id: int) -> list:
    """Fetch sites from supply chain config."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{api_base}/api/v1/supply-chain-configs/{config_id}",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    config = resp.json()
    sites = config.get("sites") or config.get("nodes") or []
    return [
        {
            "site_key": f"site_{s.get('id', i)}",
            "site_name": s.get("name", f"Site_{i}"),
            "site_type": s.get("sc_site_type", s.get("master_type", "INVENTORY")),
            "region": s.get("region", "default"),
            "site_id": s.get("id", i),
        }
        for i, s in enumerate(sites)
    ]


def create_service_account(api_base: str, token: str, site_key: str) -> dict:
    """Create a service account for a PicoClaw instance."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{api_base}/api/v1/edge-agents/picoclaw/service-accounts",
        headers=headers,
        json={"name": f"picoclaw-{site_key}", "scope": "site", "site_key": site_key},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()
    # May fail if already exists — that's OK
    print(f"  Warning: Could not create service account for {site_key}: {resp.status_code}")
    return {}


def register_instance(api_base: str, token: str, site: dict) -> None:
    """Register PicoClaw instance in the fleet."""
    headers = {"Authorization": f"Bearer {token}"}
    requests.post(
        f"{api_base}/api/v1/edge-agents/picoclaw/fleet/instances",
        headers=headers,
        json={
            "site_key": site["site_key"],
            "site_name": site["site_name"],
            "site_type": site["site_type"],
            "region": site["region"],
            "mode": "deterministic",
            "heartbeat_interval_min": 30,
        },
        timeout=10,
    )


def generate_workspace(site: dict, output_dir: Path, template_dir: Path,
                       api_base: str, llm_api_base: str, llm_model: str,
                       service_token: str = "") -> None:
    """Generate a workspace directory for one site."""
    ws_dir = output_dir / site["site_key"]
    ws_dir.mkdir(parents=True, exist_ok=True)

    substitutions = {
        "SITE_KEY": site["site_key"],
        "SITE_NAME": site["site_name"],
        "SITE_TYPE": site["site_type"],
        "REGION": site["region"],
        "API_BASE": api_base,
        "LLM_API_BASE": llm_api_base,
        "LLM_MODEL": llm_model,
    }

    # Copy and populate template files
    for template_file in ["config.json.template", "IDENTITY.md.template"]:
        src = template_dir / template_file
        if src.exists():
            content = src.read_text()
            for key, val in substitutions.items():
                content = content.replace(f"${{{key}}}", val)
            dest_name = template_file.replace(".template", "")
            (ws_dir / dest_name).write_text(content)

    # Copy static files
    for static_file in ["HEARTBEAT.sh", "DIGEST.sh", "MARKET_SIGNAL.sh", "SOUL.md"]:
        src = template_dir / static_file
        if src.exists():
            shutil.copy2(src, ws_dir / static_file)
            if static_file.endswith(".sh"):
                (ws_dir / static_file).chmod(
                    stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP
                )

    # Copy skills directory
    skills_src = template_dir / "skills"
    skills_dst = ws_dir / "skills"
    if skills_src.exists():
        if skills_dst.exists():
            shutil.rmtree(skills_dst)
        shutil.copytree(skills_src, skills_dst)

    print(f"  Generated workspace: {ws_dir}")


def main():
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    service_tokens = {}

    print("PicoClaw Workspace Generator")
    print("=" * 50)

    # Get sites
    if args.site_ids:
        sites = [
            {
                "site_key": f"site_{sid.strip()}",
                "site_name": f"Site_{sid.strip()}",
                "site_type": "INVENTORY",
                "region": "default",
                "site_id": int(sid.strip()),
            }
            for sid in args.site_ids.split(",")
        ]
        print(f"Using specified site IDs: {[s['site_key'] for s in sites]}")
    else:
        try:
            token = authenticate(args.api_base, args.admin_email, args.admin_password)
            sites = get_sites(args.api_base, token, args.config_id)
            print(f"Loaded {len(sites)} sites from config {args.config_id}")
        except Exception as e:
            print(f"Could not load sites from API: {e}")
            print("Using default 4-site topology")
            sites = [
                {"site_key": "site_1", "site_name": "Retailer", "site_type": "INVENTORY", "region": "default"},
                {"site_key": "site_2", "site_name": "Wholesaler", "site_type": "INVENTORY", "region": "default"},
                {"site_key": "site_3", "site_name": "Distributor", "site_type": "INVENTORY", "region": "default"},
                {"site_key": "site_4", "site_name": "Factory", "site_type": "MANUFACTURER", "region": "default"},
            ]
            token = None

    if args.dry_run:
        print(f"\nDry run — would generate {len(sites)} workspaces in {output_dir}")
        for site in sites:
            print(f"  {site['site_key']}: {site['site_name']} ({site['site_type']})")
        return

    # Generate workspaces
    output_dir.mkdir(parents=True, exist_ok=True)

    for site in sites:
        # Create service account if API is available
        sa_token = ""
        if token:
            try:
                register_instance(args.api_base, token, site)
                sa = create_service_account(args.api_base, token, site["site_key"])
                sa_token = sa.get("token", "")
                if sa_token:
                    service_tokens[site["site_key"]] = sa_token
            except Exception as e:
                print(f"  Warning: API call failed for {site['site_key']}: {e}")

        generate_workspace(
            site=site,
            output_dir=output_dir,
            template_dir=TEMPLATE_DIR,
            api_base=args.api_base,
            llm_api_base=args.llm_api_base,
            llm_model=args.llm_model,
            service_token=sa_token,
        )

    # Write service account tokens to env file
    if service_tokens:
        env_file = output_dir / ".env.picoclaw"
        with open(env_file, "w") as f:
            f.write("# PicoClaw service account tokens (auto-generated)\n")
            f.write("# DO NOT commit this file to version control\n\n")
            for site_key, tok in service_tokens.items():
                f.write(f"PICOCLAW_TOKEN_{site_key.upper()}={tok}\n")
        print(f"\nService tokens written to {env_file}")

    print(f"\nGenerated {len(sites)} workspaces in {output_dir}")


if __name__ == "__main__":
    main()
