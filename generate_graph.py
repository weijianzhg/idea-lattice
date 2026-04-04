#!/usr/bin/env python3
"""
Generate an interactive knowledge graph visualization from a Substack RSS feed.

Usage:
    python generate_graph.py [--rss PATH] [--output PATH] [--crosslinks PATH]

Example:
    python generate_graph.py --rss feed.xml --output lattice-graph.html
"""

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional


def parse_date(date_str: str) -> str:
    """Convert RSS date format to readable format."""
    try:
        # RSS format: "Mon, 09 Dec 2024 18:25:23 GMT"
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return date_str


def split_title(title: str) -> tuple[str, str]:
    """
    Split title into (model, domain).
    Accepts 'Model - Domain' / 'Model – Domain' / 'Model — Domain'.
    """
    m = re.match(r"^(.*?)\s*[\-–—]\s*(.+)$", title.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title.strip(), "Misc"


def slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    s = name.lower().strip()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "untitled"


def parse_rss(rss_path: str) -> list[dict]:
    """Parse RSS feed and extract post data."""
    tree = ET.parse(rss_path)
    root = tree.getroot()

    items = root.findall(".//item")

    posts = []
    for item in items:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date = item.findtext("pubDate") or ""
        description = item.findtext("description") or ""

        # Clean up HTML entities in description
        description = html.unescape(description)
        # Truncate long descriptions
        if len(description) > 150:
            description = description[:147] + "..."

        model, domain = split_title(title)

        posts.append({
            "id": slugify(model),
            "title": model,
            "domain": domain.strip(),
            "link": link,
            "pubDate": parse_date(pub_date),
            "description": description
        })

    return posts


def load_crosslinks(crosslinks_path: Optional[str]) -> list[dict]:
    """Load manual cross-links from JSON file."""
    if not crosslinks_path or not Path(crosslinks_path).exists():
        return []

    with open(crosslinks_path, "r") as f:
        data = json.load(f)

    return data.get("crosslinks", [])


def generate_auto_crosslinks(posts: list[dict]) -> list[dict]:
    """
    Generate automatic cross-links based on domain relationships.
    This creates some sensible default connections.
    """
    crosslinks = []

    # Define some logical cross-domain relationships
    # These are common mental model connections
    domain_bridges = {
        ("Economics", "Psychology"): True,
        ("Mathematics", "Economics"): True,
        ("Mathematics", "Logic"): True,
        ("Psychology", "Logic"): True,
    }

    # Group posts by domain
    by_domain = {}
    for p in posts:
        by_domain.setdefault(p["domain"], []).append(p)

    # Create cross-links between related domains (one link per domain pair)
    domains = list(by_domain.keys())
    for i, d1 in enumerate(domains):
        for d2 in domains[i+1:]:
            pair = tuple(sorted([d1, d2]))
            if pair in domain_bridges or (pair[1], pair[0]) in domain_bridges:
                # Link first post from each domain
                if by_domain[d1] and by_domain[d2]:
                    crosslinks.append({
                        "source": by_domain[d1][0]["id"],
                        "target": by_domain[d2][0]["id"]
                    })

    return crosslinks


def generate_html(posts: list[dict], crosslinks: list[dict]) -> str:
    """Generate the complete HTML visualization."""

    # Convert posts to JavaScript
    posts_json = json.dumps(posts, indent=12, ensure_ascii=False)

    # Build crosslinks JavaScript
    crosslinks_js = ",\n            ".join([
        f'{{ source: "{cl["source"]}", target: "{cl["target"]}", type: "cross-link" }}'
        for cl in crosslinks
    ])

    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Latticework of Mental Models</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-0: #0B0D10;
            --bg-1: #11151A;
            --bg-2: #171C22;
            --bg-3: #1E242C;
            --border: #27303A;
            --border-subtle: #1E242C;
            --text-1: #F3F5F7;
            --text-2: #A8B3C2;
            --text-3: #6B7A8D;
            --accent-50: #EEF2FF;
            --accent-300: #A5B4FC;
            --accent-400: #818CF8;
            --accent-500: #6366F1;
            --accent-600: #4F46E5;
            --accent-800: #3730A3;
            --accent-950: #1E1B4B;
            --success: #34D399;
            --warning: #FBBF24;
            --error: #F87171;
            --info: #60A5FA;
            --link-default: rgba(99, 102, 241, 0.2);
            --link-hover: rgba(99, 102, 241, 0.6);
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 16px;
            --duration-micro: 150ms;
            --duration-default: 200ms;
            --duration-expand: 300ms;
            --ease-default: cubic-bezier(0.25, 0.1, 0.25, 1);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.25);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-0);
            color: var(--text-1);
            overflow: hidden;
            height: 100vh;
            width: 100vw;
        }

        #container {
            position: relative;
            width: 100%;
            height: 100%;
        }

        #graph-canvas {
            width: 100%;
            height: 100%;
            display: block;
        }

        .header {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            padding: 24px 32px;
            background: linear-gradient(to bottom, var(--bg-0) 0%, transparent 100%);
            pointer-events: none;
            z-index: 10;
        }

        .header h1 {
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-1);
            letter-spacing: -0.025em;
        }

        .header p {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-3);
            margin-top: 6px;
            letter-spacing: 0.04em;
        }

        .legend {
            position: absolute;
            bottom: 24px;
            left: 32px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.7rem;
            color: var(--text-2);
            z-index: 10;
            background: rgba(11, 13, 16, 0.85);
            padding: 16px 20px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border);
            backdrop-filter: blur(12px);
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .legend-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            box-shadow: 0 0 8px currentColor;
        }

        .legend-dot.hub {
            width: 14px;
            height: 14px;
            border-radius: 3px;
        }

        .tooltip {
            position: fixed;
            top: 0;
            left: 0;
            pointer-events: none;
            background: var(--bg-1);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 14px 18px;
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 0.8rem;
            color: var(--text-1);
            box-shadow: var(--shadow-md);
            opacity: 0;
            z-index: 100;
            max-width: 320px;
            backdrop-filter: blur(12px);
            will-change: transform, opacity;
            transition: opacity var(--duration-micro) var(--ease-default);
        }

        .tooltip.visible {
            opacity: 1;
        }

        .tooltip-title {
            font-weight: 600;
            font-size: 0.9rem;
            margin-bottom: 8px;
            color: var(--accent-300);
        }

        .tooltip-domain {
            display: inline-block;
            padding: 3px 8px;
            border-radius: var(--radius-sm);
            font-size: 0.65rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 8px;
        }

        .tooltip-description {
            color: var(--text-2);
            line-height: 1.5;
            margin-bottom: 10px;
            font-size: 0.8rem;
        }

        .tooltip-date {
            color: var(--text-3);
            font-size: 0.65rem;
        }

        .tooltip-hint {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid var(--border);
            color: var(--success);
            font-size: 0.65rem;
        }

        .instructions {
            position: absolute;
            bottom: 24px;
            right: 32px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.65rem;
            color: var(--text-3);
            text-align: right;
            z-index: 10;
        }

        .instructions kbd {
            background: var(--bg-2);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            font-family: inherit;
        }

        .node-label {
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 11px;
            fill: var(--text-2);
            pointer-events: none;
            text-anchor: middle;
            dominant-baseline: middle;
        }

        .node-label.hub {
            font-weight: 600;
            fill: var(--text-1);
            font-size: 12px;
        }

        .bg-gradient {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background:
                radial-gradient(ellipse at 20% 80%, rgba(99, 102, 241, 0.06) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 20%, rgba(129, 140, 248, 0.04) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 50%, rgba(79, 70, 229, 0.03) 0%, transparent 60%);
            pointer-events: none;
            z-index: 0;
        }

        .link {
            stroke: var(--link-default);
            stroke-width: 1.5;
            fill: none;
            transition: opacity var(--duration-default) var(--ease-default), stroke var(--duration-default) var(--ease-default);
        }

        .link.cross-link {
            stroke-dasharray: 4, 4;
            stroke-width: 1;
            opacity: 0.5;
        }

        .link.highlighted {
            stroke: var(--link-hover);
            stroke-width: 2.5;
        }

        .node {
            cursor: pointer;
        }

        .node-circle {
            transition: opacity var(--duration-default) var(--ease-default);
        }

        .node.dimmed .node-circle {
            opacity: 0.2;
        }

        .node.dimmed .node-label {
            opacity: 0.2;
        }

        .link.dimmed {
            opacity: 0.08;
        }
    </style>
</head>
<body>
    <div class="bg-gradient"></div>

    <div id="container">
        <svg id="graph-canvas"></svg>

        <div class="header">
            <h1>Latticework of Mental Models</h1>
            <p>An interconnected knowledge graph</p>
        </div>

        <div class="legend" id="legend"></div>

        <div class="instructions">
            <kbd>Click</kbd> node to open post<br>
            <kbd>Drag</kbd> to move nodes<br>
            <kbd>Scroll</kbd> to zoom
        </div>

        <div class="tooltip" id="tooltip"></div>
    </div>

    <script>
        // Blog post data (auto-generated from RSS feed)
        const posts = ''' + posts_json + ''';

        // Domain color palette (auto-assigned)
        const colorPalette = [
            "#60A5FA", // info blue
            "#34D399", // success green
            "#FBBF24", // warning amber
            "#818CF8", // accent indigo
            "#F87171", // error rose
            "#A5B4FC", // accent light
            "#67E8F9", // cyan
            "#C084FC", // violet
        ];

        const domains = [...new Set(posts.map(p => p.domain))];
        const domainColors = { "Hub": "#6366F1" };
        domains.forEach((d, i) => {
            domainColors[d] = colorPalette[i % colorPalette.length];
        });

        // Build legend dynamically
        const legend = document.getElementById('legend');
        legend.innerHTML = `
            <div class="legend-item">
                <div class="legend-dot hub" style="background: ${domainColors.Hub};"></div>
                <span>Domain Hub</span>
            </div>
            ${domains.map(d => `
                <div class="legend-item">
                    <div class="legend-dot" style="background: ${domainColors[d]};"></div>
                    <span>${d}</span>
                </div>
            `).join('')}
        `;

        // Create nodes array
        const nodes = [
            ...domains.map(d => ({
                id: `hub-${d}`,
                label: d,
                type: 'hub',
                domain: d,
                radius: 22
            })),
            ...posts.map(p => ({
                id: p.id,
                label: p.title,
                type: 'post',
                domain: p.domain,
                link: p.link,
                pubDate: p.pubDate,
                description: p.description,
                radius: 14
            }))
        ];

        // Create links array
        const links = [
            ...posts.map(p => ({
                source: `hub-${p.domain}`,
                target: p.id,
                type: 'hub-link'
            })),
            // Cross-links (manually curated or auto-generated)
            ''' + crosslinks_js + '''
        ];

        // SVG setup
        const svg = d3.select('#graph-canvas');
        const container = document.getElementById('container');
        let width = container.clientWidth;
        let height = container.clientHeight;

        svg.attr('width', width).attr('height', height);

        const g = svg.append('g');

        const zoom = d3.zoom()
            .scaleExtent([0.3, 4])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });

        svg.call(zoom);

        const initialTransform = d3.zoomIdentity
            .translate(width / 2, height / 2)
            .scale(0.9);
        svg.call(zoom.transform, initialTransform);

        const simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(links)
                .id(d => d.id)
                .distance(d => d.type === 'hub-link' ? 120 : 180)
                .strength(d => d.type === 'hub-link' ? 0.8 : 0.2))
            .force('charge', d3.forceManyBody()
                .strength(d => d.type === 'hub' ? -600 : -300))
            .force('center', d3.forceCenter(0, 0))
            .force('collision', d3.forceCollide()
                .radius(d => d.radius + 40))
            .velocityDecay(0.4)
            .alphaDecay(0.02);

        const link = g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(links)
            .enter()
            .append('line')
            .attr('class', d => `link ${d.type === 'cross-link' ? 'cross-link' : ''}`);

        const node = g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(nodes)
            .enter()
            .append('g')
            .attr('class', 'node')
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        const defs = svg.append('defs');
        const filter = defs.append('filter')
            .attr('id', 'glow')
            .attr('x', '-50%')
            .attr('y', '-50%')
            .attr('width', '200%')
            .attr('height', '200%');

        filter.append('feGaussianBlur')
            .attr('stdDeviation', '3')
            .attr('result', 'coloredBlur');

        const feMerge = filter.append('feMerge');
        feMerge.append('feMergeNode').attr('in', 'coloredBlur');
        feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

        node.append('circle')
            .attr('class', 'node-circle')
            .attr('r', d => d.radius)
            .attr('fill', d => d.type === 'hub' ? domainColors.Hub : domainColors[d.domain])
            .attr('stroke', d => d.type === 'hub' ? domainColors.Hub : domainColors[d.domain])
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.6)
            .attr('fill-opacity', d => d.type === 'hub' ? 0.9 : 0.85)
            .style('filter', 'url(#glow)');

        node.filter(d => d.type === 'hub')
            .append('rect')
            .attr('width', 8)
            .attr('height', 8)
            .attr('x', -4)
            .attr('y', -4)
            .attr('transform', 'rotate(45)')
            .attr('fill', 'rgba(255,255,255,0.3)')
            .attr('rx', 1);

        node.append('text')
            .attr('class', d => `node-label ${d.type === 'hub' ? 'hub' : ''}`)
            .attr('dy', d => d.radius + 16)
            .text(d => d.label);

        const tooltip = document.getElementById('tooltip');
        let tooltipX = 0, tooltipY = 0;
        let tooltipVisible = false;

        function updateTooltipPosition() {
            if (tooltipVisible) {
                tooltip.style.transform = `translate(${tooltipX}px, ${tooltipY}px)`;
            }
            requestAnimationFrame(updateTooltipPosition);
        }
        requestAnimationFrame(updateTooltipPosition);

        const connectedNodesMap = new Map();
        nodes.forEach(n => {
            const connected = new Set([n.id]);
            links.forEach(l => {
                const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                if (sourceId === n.id) connected.add(targetId);
                if (targetId === n.id) connected.add(sourceId);
            });
            connectedNodesMap.set(n.id, connected);
        });

        node.on('mouseenter', function(event, d) {
            d3.select(this).select('.node-circle')
                .transition()
                .duration(150)
                .attr('r', d.radius * 1.15);

            const connectedNodeIds = connectedNodesMap.get(d.id);

            node.classed('dimmed', n => !connectedNodeIds.has(n.id));
            link.classed('dimmed', l => {
                const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                return sourceId !== d.id && targetId !== d.id;
            });
            link.classed('highlighted', l => {
                const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                return sourceId === d.id || targetId === d.id;
            });

            if (d.type === 'post') {
                const color = domainColors[d.domain];
                tooltip.innerHTML = `
                    <div class="tooltip-title">${d.label}</div>
                    <span class="tooltip-domain" style="background: ${color}22; color: ${color}; border: 1px solid ${color}44;">${d.domain}</span>
                    <div class="tooltip-description">${d.description}</div>
                    <div class="tooltip-date">📅 ${d.pubDate}</div>
                    <div class="tooltip-hint">Click to read →</div>
                `;
            } else {
                const count = posts.filter(p => p.domain === d.domain).length;
                tooltip.innerHTML = `
                    <div class="tooltip-title">${d.label}</div>
                    <div class="tooltip-description">${count} mental model${count > 1 ? 's' : ''}</div>
                `;
            }

            tooltipX = event.pageX + 15;
            tooltipY = event.pageY + 15;
            tooltipVisible = true;
            tooltip.classList.add('visible');
        });

        node.on('mousemove', function(event) {
            let x = event.pageX + 15;
            let y = event.pageY + 15;

            const tooltipRect = tooltip.getBoundingClientRect();
            if (x + tooltipRect.width > window.innerWidth - 20) {
                x = event.pageX - tooltipRect.width - 15;
            }
            if (y + tooltipRect.height > window.innerHeight - 20) {
                y = event.pageY - tooltipRect.height - 15;
            }

            tooltipX = x;
            tooltipY = y;
        });

        node.on('mouseleave', function(event, d) {
            d3.select(this).select('.node-circle')
                .transition()
                .duration(150)
                .attr('r', d.radius);

            node.classed('dimmed', false);
            link.classed('dimmed', false);
            link.classed('highlighted', false);
            tooltipVisible = false;
            tooltip.classList.remove('visible');
        });

        node.on('click', function(event, d) {
            if (d.type === 'post' && d.link) {
                window.open(d.link, '_blank');
            }
        });

        simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        simulation.on('end', () => {
            simulation.stop();
        });

        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        window.addEventListener('resize', () => {
            width = container.clientWidth;
            height = container.clientHeight;
            svg.attr('width', width).attr('height', height);
        });

        node.style('opacity', 0)
            .transition()
            .delay((d, i) => i * 50)
            .duration(500)
            .style('opacity', 1);

        link.style('opacity', 0)
            .transition()
            .delay(300)
            .duration(800)
            .style('opacity', 1);
    </script>
</body>
</html>'''

    return html_template


def main():
    parser = argparse.ArgumentParser(
        description="Generate a knowledge graph visualization from a Substack RSS feed"
    )
    parser.add_argument(
        "--rss",
        default="latticeworkofmodels.substack.com_feed.xml",
        help="Path to RSS feed XML file (default: latticeworkofmodels.substack.com_feed.xml)"
    )
    parser.add_argument(
        "--output",
        default="lattice-graph.html",
        help="Output HTML file path (default: lattice-graph.html)"
    )
    parser.add_argument(
        "--crosslinks",
        default="crosslinks.json",
        help="Path to JSON file with manual cross-links (default: crosslinks.json)"
    )
    parser.add_argument(
        "--auto-crosslinks",
        action="store_true",
        help="Generate automatic cross-links if no crosslinks.json exists"
    )

    args = parser.parse_args()

    # Check RSS file exists
    if not Path(args.rss).exists():
        print(f"Error: RSS file not found: {args.rss}")
        print("\nTo download your Substack RSS feed:")
        print("  curl -o feed.xml https://YOUR-SUBSTACK.substack.com/feed")
        return 1

    # Parse RSS feed
    print(f"📖 Parsing RSS feed: {args.rss}")
    posts = parse_rss(args.rss)
    print(f"   Found {len(posts)} posts across {len(set(p['domain'] for p in posts))} domains")

    # Load or generate cross-links
    crosslinks = load_crosslinks(args.crosslinks)
    if crosslinks:
        print(f"🔗 Loaded {len(crosslinks)} manual cross-links from {args.crosslinks}")
    elif args.auto_crosslinks:
        crosslinks = generate_auto_crosslinks(posts)
        print(f"🔗 Generated {len(crosslinks)} automatic cross-links")
    else:
        print(f"ℹ️  No cross-links file found. Use --auto-crosslinks or create {args.crosslinks}")

    # Generate HTML
    print(f"🎨 Generating visualization...")
    html_content = generate_html(posts, crosslinks)

    # Write output
    output_path = Path(args.output)
    output_path.write_text(html_content, encoding="utf-8")
    print(f"✅ Wrote {output_path}")
    print(f"\n🌐 Open in browser: file://{output_path.absolute()}")

    return 0


if __name__ == "__main__":
    exit(main())

