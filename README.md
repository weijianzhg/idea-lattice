# Latticework of Mental Models — Knowledge Graph

An interactive visualization of mental models as an interconnected knowledge graph.

![Graph Preview](https://img.shields.io/badge/D3.js-Interactive-blue)
![Python](https://img.shields.io/badge/Python-3.9+-green)

## Features

- **Interactive force-directed graph** — nodes naturally arrange based on connections
- **Domain hubs** — posts are grouped by category (Economics, Psychology, Mathematics, Logic)
- **Cross-links** — dotted lines show conceptual relationships across domains
- **Clickable nodes** — click any post to open it in a new tab
- **Smooth interactions** — hover highlights, drag to rearrange, scroll to zoom
- **Dark theme** — elegant design ready to embed

## Quick Start

### 1. Download your RSS feed

```bash
curl -o latticeworkofmodels.substack.com_feed.xml \
  https://latticeworkofmodels.substack.com/feed
```

### 2. Generate the visualization

```bash
python generate_graph.py
```

### 3. Open in browser

```bash
open lattice-graph.html
# or on Linux: xdg-open lattice-graph.html
```

## Usage

```
python generate_graph.py [OPTIONS]

Options:
  --rss PATH           Path to RSS feed XML (default: latticeworkofmodels.substack.com_feed.xml)
  --output PATH        Output HTML file (default: lattice-graph.html)
  --crosslinks PATH    Path to cross-links JSON (default: crosslinks.json)
  --auto-crosslinks    Auto-generate cross-links if JSON file missing
```

### Examples

```bash
# Use default settings
python generate_graph.py

# Custom RSS and output
python generate_graph.py --rss my_feed.xml --output docs/graph.html

# Auto-generate cross-links
python generate_graph.py --auto-crosslinks
```

## Customizing Cross-Links

Edit `crosslinks.json` to define connections between your posts:

```json
{
  "crosslinks": [
    {
      "source": "kelly-criterion",
      "target": "bayes-theorem",
      "reason": "Kelly uses Bayesian probability estimation"
    }
  ]
}
```

**Note:** The `source` and `target` values are "slugified" versions of your post titles:
- "Kelly criterion" → `kelly-criterion`
- "Bayes' theorem" → `bayes-theorem`
- "The Power of Incentives" → `the-power-of-incentives`

The `reason` field is optional documentation for yourself.

## Embedding in Your Website

### Option 1: Direct embed (iframe)

```html
<iframe
  src="lattice-graph.html"
  width="100%"
  height="600"
  style="border: none; border-radius: 12px;"
></iframe>
```

### Option 2: Full-page

Simply host `lattice-graph.html` as a standalone page on your site.

### Option 3: Subdirectory

```
your-website/
├── index.html
└── knowledge-graph/
    └── index.html  (rename lattice-graph.html)
```

## Requirements

- Python 3.9+ (no external dependencies!)
- Modern browser with JavaScript enabled

## File Structure

```
idea-lattice/
├── generate_graph.py                              # Generator script
├── lattice-graph.html                             # Output visualization
├── crosslinks.json                                # Manual cross-links
├── latticeworkofmodels.substack.com_feed.xml      # Your RSS feed
└── README.md
```

## Workflow: Updating After New Posts

1. **Download fresh RSS feed:**
   ```bash
   curl -o latticeworkofmodels.substack.com_feed.xml \
     https://latticeworkofmodels.substack.com/feed
   ```

2. **Add cross-links for new posts** (optional):
   Edit `crosslinks.json` to connect your new post to related concepts.

3. **Regenerate:**
   ```bash
   python generate_graph.py
   ```

4. **Deploy:**
   Upload the new `lattice-graph.html` to your website.

## How It Works

1. **RSS Parsing** — Extracts title, domain, description, date, and URL from each post
2. **Title Splitting** — Parses "Model Name - Domain" format to categorize posts
3. **Graph Construction** — Creates hub nodes (domains) + post nodes with connections
4. **D3.js Rendering** — Force-directed layout with physics simulation
5. **Interactivity** — Mouse events for hover, click, drag, and zoom

## License

MIT — Feel free to use and modify for your own knowledge graphs!

