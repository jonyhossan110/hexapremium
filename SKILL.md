# HexaPremium — premium social-image design compiler

Make premium, clean, high-quality social-media images for ANY topic — the way a
designer would, but rendered by code. All text is typeset by the render engine
(never drawn by an image-generation model), at 2x supersample with sharpening,
so small text stays readable after LinkedIn/Instagram compression.

## When to use
The user gives a topic, idea or summary and wants a premium post image,
cover, square/portrait post, story, or YouTube thumbnail — especially when
they want every design to look different and unique.

## How it works
1. **Content brain (you, the agent):** turn the user's topic into a content
   JSON (schema below). Rules:
   - One hook line with real stakes (money, risk, result) for the top banner.
   - One clear title, one subtitle. Max ~7 cards.
   - Card facts/numbers must come from the user's input or be clearly generic
     statements — NEVER invent statistics, prices, client names or results.
   - Mix card types: stat, code, toggles, bars, checklist, quote, text.
   - Card count by format: landscape post 5–7 cards; square/portrait/story
     need 6–9 cards or the lower half stays empty (the engine auto-grows
     content up to 1.45x, but it cannot invent content).
2. **Style engine:** layout × theme × card-style × decor × font-pair are
   combined by a seed. Same seed = same design; new seed = new design.
   A history file (`history.json` next to this skill) remembers used combos
   so consecutive images never repeat a style.
3. **Render + QA:** the engine auto-shrinks content until it fits and reports
   `qa.fits`. If `fits` is false, remove a card or shorten text and re-run.

## Command
```bash
python3 scripts/hexapremium.py --content <content.json> --out <out.png> \
  [--platform linkedin-post|linkedin-square|linkedin-cover|ig-square|ig-portrait|story|yt-thumbnail] \
  [--seed N] [--layout hero|split|grid|dashboard] \
  [--theme peach|navy|mint|sunset|mono|sky] \
  [--cardstyle flat|sticker|glass] [--decor dots|grid|rings|plain] \
  [--fontpair bold|serif|mono] [--no-history]
```
Omit style flags to let the seed choose. Useful modes:
- **Batch of styles:** run 3–5 times with different seeds, show all, let the
  user pick.
- **Same content, new style:** re-run with a new seed.
- **Lock a style:** pass the axis flags explicitly.

## Content JSON schema
```json
{
  "topic": "fallback title",
  "hook_left": "FOR ONLINE BUSINESSES",
  "hook": "ONE HACK CAN COST YOU $$$,$$$",
  "hook_right": "ONE CHECK CAN SAVE IT",
  "title": "Main headline",
  "subtitle": "One supporting line",
  "bullets": ["split layout only"],
  "cta": "FIX - VERIFY - SECURE",
  "brand": {"name": "HexaCyberLab"},
  "person": {"image": "path/to/person.png", "cutout": "hsv|none"},
  "cards": [
    {"type": "stat", "value": "27", "label": "BUGS FOUND", "sub": "every one fixed + verified"},
    {"type": "code", "title": "pentest - deep-scan", "lines": [{"t": "$ nmap target.com", "c": "cmd"}, {"t": "✓ ORDER CONFIRMED", "c": "ok"}]},
    {"type": "toggles", "title": "AI Models", "sub": "latest versions", "rows": [["ChatGPT", "GPT-6"], ["Claude", "Opus 5.5"]]},
    {"type": "bars", "title": "Deep Website Scan", "rows": [["Critical", 92, "critical"], ["High", 74, "high"], ["Medium", 45, "medium"]]},
    {"type": "checklist", "title": "What you get", "items": ["Full manual test", "Proof + fix steps"]},
    {"type": "quote", "text": "\"Scanners missed it. We didn't.\"", "by": "— on a hidden IDOR"},
    {"type": "text", "title": "HIDDEN RISK FOUND", "body": "Broken access control, deep inside the app."}
  ]
}
```
Code line colours: plain, cmd, ok, bad, warn, dim, accent, white.
Person cutout `hsv` removes a teal/cyan studio background (proven method);
`none` pastes the image as-is. Bengali text is supported (Noto Sans Bengali,
proper shaping via libraqm) — titles, cards and hooks may be in Bangla.

## Brand kit
Edit `brand.json` with the user's name/logo defaults. Premium finished images
for Jony go to the PC folder `D:\HexaDesigns\` as well as chat.

## Roadmap (axes grow without code changes to layouts)
v1 axes: 4 layouts × 6 themes × 3 card styles × 4 decors × 3 font pairs = 864
combos. Adding themes/layouts multiplies the space — the design target is
1,000+ verified-distinct premium looks (blueprint: the HexaPremium idea note).
