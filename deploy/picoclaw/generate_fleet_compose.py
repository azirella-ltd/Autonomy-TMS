#!/usr/bin/env python3
"""
PicoClaw Fleet Docker Compose Generator

Generates a docker-compose.picoclaw.yml file with one container per site.
Each container runs PicoClaw in gateway mode with workspace volume mount.

Usage:
    python deploy/picoclaw/generate_fleet_compose.py --config-id 1
    python deploy/picoclaw/generate_fleet_compose.py --workspaces-dir deploy/picoclaw/workspaces
    python deploy/picoclaw/generate_fleet_compose.py --site-ids 1,2,3,4

Prerequisites:
    Run generate_workspaces.py first to create per-site workspaces.
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
DEFAULT_WORKSPACES = SCRIPT_DIR / "workspaces"
DEFAULT_OUTPUT = SCRIPT_DIR / "docker-compose.picoclaw.yml"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate PicoClaw fleet Docker Compose")
    parser.add_argument("--workspaces-dir", type=str, default=str(DEFAULT_WORKSPACES),
                        help="Directory containing per-site workspaces")
    parser.add_argument("--site-ids", type=str, default=None,
                        help="Comma-separated site IDs (auto-discovers from workspaces if not set)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help="Output docker-compose file path")
    parser.add_argument("--image", type=str, default="picoclaw/picoclaw:latest",
                        help="PicoClaw Docker image")
    parser.add_argument("--mem-limit", type=str, default="20m",
                        help="Memory limit per instance")
    parser.add_argument("--network", type=str, default="autonomy-network",
                        help="Docker network name")
    return parser.parse_args()


def discover_sites(workspaces_dir: Path) -> list:
    """Discover site keys from workspace directories."""
    sites = []
    if not workspaces_dir.exists():
        return sites
    for d in sorted(workspaces_dir.iterdir()):
        if d.is_dir() and d.name.startswith("site_"):
            sites.append(d.name)
    return sites


def generate_compose(sites: list, args) -> dict:
    """Generate Docker Compose structure."""
    services = {}
    workspaces_dir = Path(args.workspaces_dir)

    for site_key in sites:
        service_name = f"picoclaw-{site_key.replace('_', '-')}"
        ws_path = workspaces_dir / site_key

        services[service_name] = {
            "image": args.image,
            "container_name": service_name,
            "command": "gateway",
            "volumes": [
                f"{ws_path.resolve()}:/root/.picoclaw/workspace:ro",
            ],
            "environment": [
                f"PICOCLAW_SITE_KEY={site_key}",
                "PICOCLAW_API_BASE=${AUTONOMY_API_BASE:-http://backend:8000}",
                f"PICOCLAW_AUTH_TOKEN=${{PICOCLAW_TOKEN_{site_key.upper()}}}",
                f"PICOCLAW_ALERT_CHANNEL=#{site_key.replace('_', '-')}-alerts",
                "PICOCLAW_LLM_API_BASE=${LLM_API_BASE:-http://vllm:8000/v1}",
                "PICOCLAW_LLM_MODEL=${LLM_MODEL_NAME:-qwen3-8b}",
            ],
            "networks": [args.network],
            "restart": "unless-stopped",
            "mem_limit": args.mem_limit,
        }

    compose = {
        "services": services,
        "networks": {
            args.network: {"external": True},
        },
    }
    return compose


def main():
    args = parse_args()
    workspaces_dir = Path(args.workspaces_dir)

    # Discover or parse sites
    if args.site_ids:
        sites = [f"site_{s.strip()}" for s in args.site_ids.split(",")]
    else:
        sites = discover_sites(workspaces_dir)

    if not sites:
        print("No sites found. Run generate_workspaces.py first or specify --site-ids.")
        sys.exit(1)

    print(f"Generating fleet compose for {len(sites)} sites:")
    for s in sites:
        print(f"  - {s}")

    compose = generate_compose(sites, args)

    # Add header comment
    output_path = Path(args.output)
    header = (
        "# PicoClaw Fleet Docker Compose (auto-generated)\n"
        "#\n"
        "# Usage:\n"
        "#   docker compose -f docker-compose.yml -f deploy/picoclaw/docker-compose.picoclaw.yml up -d\n"
        "#\n"
        "# Prerequisites:\n"
        "#   - Autonomy backend running (make up)\n"
        "#   - Per-site workspaces generated (make picoclaw-workspaces)\n"
        "#   - Service account tokens in .env.picoclaw\n"
        "#\n"
        f"# Sites: {len(sites)}\n"
        f"# Memory per instance: {args.mem_limit}\n"
        f"# Total memory: ~{len(sites) * 20}MB\n"
        "\n"
    )

    yaml_content = yaml.dump(compose, default_flow_style=False, sort_keys=False)
    output_path.write_text(header + yaml_content)

    print(f"\nGenerated: {output_path}")
    print(f"Total fleet memory: ~{len(sites) * 20}MB")


if __name__ == "__main__":
    main()
