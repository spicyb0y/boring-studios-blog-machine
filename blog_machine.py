"""
Boring Studios — Automated SEO Blog Machine
Pulls keyword opportunities from Google Search Console,
writes a full post using Claude API in Boring Studios TOV,
and publishes it to the Shopify blog.
"""

import os
import io
import re
import base64
import json
import random
import datetime
import requests
from PIL import Image, ImageDraw, ImageFont
from anthropic import Anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ─────────────────────────────────────────────────────────────────

GSC_SITE_URL        = "sc-domain:boringstudios.com.au"
GSC_KEY_FILE        = "gsc-service-account.json"
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
MAKE_WEBHOOK_URL    = "https://hook.us2.make.com/fovbp51alv5blwlrfktd3qvsbk8m3eim"
IMGBB_API_KEY       = os.environ.get("IMGBB_API_KEY", "")
SITE_URL            = "https://boringstudios.com.au"
SHOP_URL            = "https://boringstudios.com.au/collections/all"

# Keyword targeting rules
MIN_IMPRESSIONS     = 50    # ignore keywords nobody searches
MIN_POSITION        = 4     # don't target #1-3 (already ranking)
MAX_POSITION        = 40    # don't target beyond page 4
DAYS_LOOKBACK       = 90    # GSC data window

# ── TOV System Prompt ───────────────────────────────────────────────────────

TOV_SYSTEM_PROMPT = """
You are the blog writer for Boring Studios, writing for "Notes from the Studio" at boringstudios.com.au/blogs/notes-from-the-studio.

VOICE AND PERSONALITY
Casual and confident. Written like a smart friend who has been through it and is sharing what actually worked. Not a guru, not a coach. Just someone a few steps ahead on the same path. Approachable, honest, and a little unfiltered.

AUDIENCE
Freelancers, studio owners, and creative entrepreneurs at beginner to intermediate level. Designers, copywriters, photographers, interior designers, and anyone building a creative business on their own. They want real talk and practical steps, not theory.

WRITING RULES

Tone:
- Conversational, like you are talking to one person
- Confident but not preachy
- Warm, occasionally self-deprecating
- Use "I" and share personal experience where it fits

Sentence style:
- Keep sentences short and punchy
- Mix short sentences with medium ones for rhythm
- No long winding paragraphs
- One idea per paragraph

Words to use:
- Plain everyday English
- "you" and "we" over "one" or "people"
- Contractions: you're, it's, don't, can't
- Direct verbs: start, do, build, write, get

Words and phrases to NEVER use:
- M-dashes, anywhere, ever. Use a full stop or comma instead.
- Jargon: leverage, synergy, optimise, utilise, scalable
- Filler openers: "In today's world...", "Have you ever wondered...", "It's no secret that..."
- Contrastive negation: never open with a wrong idea just to correct it
- Overused qualifiers: very, really, just, quite, essentially
- The word "cringe"

STRUCTURE

Headlines:
- Sentence case always: capitalise the first word only, plus proper nouns
- Written to read like a heading, not a sentence. Clear, direct, specific.
- Use the main keyword naturally in the H1
- H2/H3 subheadings break up sections and include supporting keywords naturally

Opening:
- Start with the situation or problem the reader is already in
- Make them feel seen immediately
- Skip the preamble

Body:
- Informative with actionable steps
- Use numbered lists or bullet points for steps
- Keep lists tight, one idea per line
- Bold the step name, follow with a plain text explanation. Use a full stop to separate, never a m-dash.

Closing:
- Wrap up with the main takeaway in one or two sentences
- Link to a relevant Boring Studios product where it fits naturally
- NO sign off. No name, no title, no farewell sentence. End on the last line of content.

SEO:
- One primary keyword per post, used naturally in the H1, intro, and one subheading
- Supporting keywords woven into body copy where they fit naturally
- No keyword stuffing
- Meta title: sentence case, under 60 characters
- Meta description: 1-2 sentences, includes keyword, under 120 characters, reads like a human wrote it

PRODUCT LINKS
Link to 1-2 Boring Studios products per post. Be direct. Frame it as the obvious next step.
Examples:
- "We built [product] for exactly this. Go grab it here."
- "If you want to skip the setup, [product] has it all ready to go."
- "[Product] is what I'd start with. It's all here."

PRIORITY PRODUCTS — always prefer these first. Link to one of these in every post where it fits:
- Creative Business Operating System (CBOS) — the full system for running a creative business → https://boringstudios.com.au/products/cbos-entire-system
- Studio Starter Bundle — CBOS + essentials for new studios → https://boringstudios.com.au/products/studio-starter-cbos
- CBOS Frameworks (8 x Figma frameworks) — client onboarding, proposals, contracts, invoices, offboarding, pitch, portfolio, services guide → https://boringstudios.com.au/products/cbos-frameworks-8-figma-frameworks
- Contract Framework (Figma) → https://boringstudios.com.au/products/contract
- Client Onboarding Framework (Figma) → https://boringstudios.com.au/products/client-onboarding-1
- Client Offboarding Framework (Figma) → https://boringstudios.com.au/products/client-offboarding-1
- Proposal Framework (Figma) → https://boringstudios.com.au/products/proposal-1
- Invoice Framework (Figma) → https://boringstudios.com.au/products/invoice-1
- Portfolio Framework (Figma) → https://boringstudios.com.au/products/portfolio-1
- Services Guide Framework (Figma) → https://boringstudios.com.au/products/services-guide
- Pitch Framework (Figma) → https://boringstudios.com.au/products/client-pitch

If the post topic is branding or visual identity, you may also link to these:
Only link to products from this exact list. Use the exact URLs shown:
- Boring Branding book → https://boringstudios.com.au/products/boring-branding-building-a-brand-that-is-impossible-to-ignore
- Brand Book → https://boringstudios.com.au/products/brand-book
- Brand Guidelines → https://boringstudios.com.au/products/brand-guidelines
- Brand Presentation → https://boringstudios.com.au/products/brand-presentation
- Brand Strategy template → https://boringstudios.com.au/products/brand-strategy
- Brand Voice → https://boringstudios.com.au/products/brand-voice
- Client Agreement → https://boringstudios.com.au/products/client-agreement
- Client Email Templates → https://boringstudios.com.au/products/client-email-templates
- Client Offboarding → https://boringstudios.com.au/products/client-offboarding
- Client Onboarding → https://boringstudios.com.au/products/client-onboarding
- Client Portal (Notion) → https://boringstudios.com.au/products/client-portal
- Client Proposal Template → https://boringstudios.com.au/products/proposal
- Clients & Lead Generation book → https://boringstudios.com.au/products/clients-lead-generation-the-simple-steps-to-clients-and-leads
- Content Planner (Notion) → https://boringstudios.com.au/products/content-planner
- Content Strategy → https://boringstudios.com.au/products/content-strategy
- Competitor Analysis → https://boringstudios.com.au/products/competitor-analysis
- Creative Business Operating System (CBOS) → https://boringstudios.com.au/products/cbos-entire-system
- Creator Bundle → https://boringstudios.com.au/products/freelance-creator-bundle
- Daily Planner (Notion) → https://boringstudios.com.au/products/daily-planner
- Freelance Starter Bundle → https://boringstudios.com.au/products/freelance-starter-bundle©-free-portfolio-template
- From Creative Skill to Business book → https://boringstudios.com.au/products/from-creative-skill-to-your-first-profitable-business
- Invoice → https://boringstudios.com.au/products/invoice
- Portfolio → https://boringstudios.com.au/products/portfolio
- Proposal Template → https://boringstudios.com.au/products/proposal
- Services Guide → https://boringstudios.com.au/products/services-guide-template
- Starter Bundle → https://boringstudios.com.au/products/client-starter-bundle
- Studio Pro Bundle → https://boringstudios.com.au/products/freelancer-pro-bundle
- Studio Starter Bundle → https://boringstudios.com.au/products/studio-starter-cbos
- Thinking Like a Business Owner book → https://boringstudios.com.au/products/thinking-like-a-business-owner-the-mindset-shift-required-for-success

LINK STYLING
All hyperlinks must use inline styles: <a href="URL" style="color: #0000EE; text-decoration: underline;">anchor text</a>
This applies to every link in the post including product links.

OUTPUT FORMAT
Return a JSON object with these exact keys:
{
  "title": "Post title (H1, sentence case)",
  "meta_title": "Meta title (under 60 chars, sentence case)",
  "meta_description": "Meta description (under 120 chars, includes keyword)",
  "body_html": "Full post body as HTML with proper H2/H3 tags, paragraphs, lists. No H1 in body. All links must use style='color: #0000EE; text-decoration: underline;'",
  "tags": ["tag1", "tag2", "tag3"],
  "summary": "One sentence summary of the post",
  "cover_title": "Short punchy headline for cover image. Max 5 words. No article words like 'the', 'a', 'an' unless essential. Title case.",
  "cover_subtitle": "One short punchy line for cover image. Max 8 words. A hook or teaser. Sentence case.",
  "faqs": [
    {"question": "A real question someone would type into Google", "answer": "Direct 2-3 sentence answer."},
    {"question": "Another common question about this topic", "answer": "Direct 2-3 sentence answer."},
    {"question": "A third question", "answer": "Direct 2-3 sentence answer."}
  ]
}
"""

# ── FAQ schema ──────────────────────────────────────────────────────────────

def build_faq_schema(faqs):
    """Build a JSON-LD FAQPage schema block and return as an HTML script tag."""
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq["answer"]
                }
            }
            for faq in faqs
        ]
    }
    return f'<script type="application/ld+json">{json.dumps(schema)}</script>'


# ── Cover image helpers ─────────────────────────────────────────────────────

def _load_font(bold=False, size=40):
    """Load Helvetica Neue from system, with fallbacks for Linux CI."""
    # macOS: HelveticaNeue.ttc — index 1 = Bold, index 0 = Regular
    ttc = "/System/Library/Fonts/HelveticaNeue.ttc"
    if os.path.exists(ttc):
        return ImageFont.truetype(ttc, size, index=1 if bold else 0)
    # Linux (GitHub Actions with fonts-liberation)
    linux_path = (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    )
    if os.path.exists(linux_path):
        return ImageFont.truetype(linux_path, size)
    return ImageFont.load_default()


def _pt_to_px(pt, dpi=150):
    """Convert Illustrator points to pixels at given DPI."""
    return round(pt * dpi / 72)


def _draw_tracked(draw, pos, text, font, fill, tracking=-30, dpi=150):
    """Draw text with Illustrator-style tracking (1/1000 em units)."""
    font_pt     = font.size * 72 / dpi          # px back to pt
    spacing_px  = (tracking / 1000) * font_pt * (dpi / 72)
    x, y = pos
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textbbox((0, 0), char, font=font)[2] + spacing_px
    return x


def _measure_tracked(draw, text, font, tracking=-30, dpi=150):
    """Measure width of tracked text."""
    font_pt    = font.size * 72 / dpi
    spacing_px = (tracking / 1000) * font_pt * (dpi / 72)
    w = 0
    for char in text:
        w += draw.textbbox((0, 0), char, font=font)[2] + spacing_px
    return w


def _wrap_tracked(draw, text, font, max_width, tracking=-30, dpi=150):
    """Word-wrap text accounting for tracking."""
    words, lines, current = text.split(), [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if _measure_tracked(draw, test, font, tracking, dpi) > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def generate_cover_image(title, tags, body_html, cover_title="", cover_subtitle=""):
    """Generate a cover image matching Boring Studios blog template. Returns PNG bytes."""
    DPI   = 150
    W, H  = 2501, 1667
    BG    = (7, 7, 7)
    WHITE = (255, 255, 255)
    pad   = 180   # generous margin (~86pt at 150dpi)

    img  = Image.new("RGB", (W, H), color=BG)
    draw = ImageDraw.Draw(img)

    # Read time + category
    plain     = re.sub(r"<[^>]+>", "", body_html)
    read_time = max(1, round(len(plain.split()) / 200))
    category  = tags[0].title() if tags else "Notes"

    # Use cover-specific copy if available, fall back to full title/summary
    headline = cover_title if cover_title else title
    subtitle = cover_subtitle if cover_subtitle else ""

    # Font sizes (Illustrator pt → pixels at 150 DPI)
    title_font = _load_font(bold=True,  size=_pt_to_px(90, DPI))   # 188px bold
    sub_font   = _load_font(bold=False, size=_pt_to_px(60, DPI))   # 125px regular
    meta_font  = _load_font(bold=False, size=_pt_to_px(30, DPI))   # 63px regular

    max_w  = W - pad * 2
    line_h = draw.textbbox((0, 0), "Ag", font=title_font)[3]
    sub_lh = draw.textbbox((0, 0), "Ag", font=sub_font)[3]

    # Headline — bold, -30 tracking
    y = pad
    for line in _wrap_tracked(draw, headline, title_font, max_w, tracking=-30, dpi=DPI):
        _draw_tracked(draw, (pad, y), line, title_font, WHITE, tracking=-30, dpi=DPI)
        y += line_h + _pt_to_px(8, DPI)   # ~110% line height

    # Divider — 2mm
    y += _pt_to_px(22, DPI)
    divider_w = round(2 * DPI / 25.4)
    draw.line([(pad, y), (W - pad, y)], fill=WHITE, width=divider_w)
    y += divider_w + _pt_to_px(28, DPI)

    # Subtitle — regular, no tracking
    if subtitle:
        for line in _wrap_tracked(draw, subtitle, sub_font, max_w, tracking=0, dpi=DPI):
            _draw_tracked(draw, (pad, y), line, sub_font, WHITE, tracking=0, dpi=DPI)
            y += sub_lh + _pt_to_px(8, DPI)

    # Meta — bottom left, -30 tracking
    meta_text = f"{category} - {read_time} minute read"
    meta_y    = H - pad - _pt_to_px(30, DPI)
    _draw_tracked(draw, (pad, meta_y), meta_text, meta_font, WHITE, tracking=-30, dpi=DPI)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(DPI, DPI))
    return buf.getvalue()


def upload_cover_image(image_bytes):
    """Upload image to imgbb and return public URL. Returns None if no API key."""
    if not IMGBB_API_KEY:
        print("   No IMGBB_API_KEY set — skipping cover image")
        return None
    b64      = base64.b64encode(image_bytes).decode("utf-8")
    response = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBB_API_KEY, "image": b64})
    response.raise_for_status()
    url = response.json()["data"]["url"]
    print(f"   Cover image uploaded: {url}")
    return url


# ── Step 1: Pull keyword opportunities from GSC ─────────────────────────────

def get_keyword_opportunities():
    """Pull search queries from GSC and find the best opportunities."""

    credentials = service_account.Credentials.from_service_account_file(
        GSC_KEY_FILE,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    service = build("searchconsole", "v1", credentials=credentials)

    end_date   = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=DAYS_LOOKBACK)

    response = service.searchanalytics().query(
        siteUrl=GSC_SITE_URL,
        body={
            "startDate": str(start_date),
            "endDate":   str(end_date),
            "dimensions": ["query"],
            "rowLimit":   500,
            "dimensionFilterGroups": [{
                "filters": [{
                    "dimension": "country",
                    "operator":  "equals",
                    "expression": "aus"
                }]
            }]
        }
    ).execute()

    rows = response.get("rows", [])

    opportunities = []
    for row in rows:
        query      = row["keys"][0]
        impressions = row.get("impressions", 0)
        clicks      = row.get("clicks", 0)
        position    = row.get("position", 100)
        ctr         = row.get("ctr", 0)

        # Filter for opportunity keywords
        if (
            impressions >= MIN_IMPRESSIONS and
            MIN_POSITION <= position <= MAX_POSITION and
            len(query.split()) >= 3  # avoid single/double word queries
        ):
            # Score: high impressions + low position number = best opportunity
            score = impressions * (1 / position)
            opportunities.append({
                "keyword":     query,
                "impressions": impressions,
                "clicks":      clicks,
                "position":    round(position, 1),
                "ctr":         round(ctr * 100, 2),
                "score":       score
            })

    # Sort by score, return top 20
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    return opportunities[:20]


# ── Step 2: Pick the best keyword to write about ────────────────────────────

def select_keyword(opportunities):
    """Pick keyword from top opportunities. Adds some randomness to vary content."""
    if not opportunities:
        raise ValueError("No keyword opportunities found. Check GSC connection.")

    # Pick randomly from top 5 to add variety
    top_5 = opportunities[:5]
    selected = random.choice(top_5)
    print(f"\n Selected keyword: '{selected['keyword']}'")
    print(f"   Impressions: {selected['impressions']} | Position: {selected['position']} | CTR: {selected['ctr']}%")
    return selected


# ── Step 3: Write the post using Claude ────────────────────────────────────

def write_post(keyword_data):
    """Use Claude to write a full post in Boring Studios TOV."""

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    keyword = keyword_data["keyword"]

    prompt = f"""Write a complete, publish-ready blog post for Boring Studios targeting the keyword: "{keyword}"

The post should be 1,500 to 2,000 words. Make it genuinely useful and specific.

Remember:
- Primary keyword "{keyword}" must appear in the H1, intro paragraph, and one H2 subheading
- Link to 1-2 relevant Boring Studios products naturally
- End on the last line of content. No sign off, no farewell.
- Return valid JSON in the exact format specified.

The post must pass this checklist before you return it:
- No m-dashes anywhere
- No jargon (leverage, synergy, optimise, utilise, scalable)
- No filler openers
- Headings are sentence case
- Lists use full stops to separate bold label from explanation
- Meta title is STRICTLY under 60 characters — count every character before returning
- Meta description is STRICTLY under 120 characters
- At least one CBOS or Figma framework product is linked unless the post is purely about visual branding
"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=TOV_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.content[0].text

    # Extract JSON from response
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    # Attempt parse with one retry on failure
    try:
        post_data = json.loads(content)
    except json.JSONDecodeError:
        print("   JSON parse failed, retrying...")
        retry = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8192,
            system=TOV_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": content},
                {"role": "user", "content": "The JSON you returned was malformed. Return only the corrected valid JSON object, no markdown fences."}
            ]
        )
        content = retry.content[0].text.strip()
        post_data = json.loads(content)
    # Hard enforce character limits
    if len(post_data["meta_title"]) > 60:
        post_data["meta_title"] = post_data["meta_title"][:57] + "..."
    if len(post_data["meta_description"]) > 120:
        post_data["meta_description"] = post_data["meta_description"][:117] + "..."

    # Inject FAQ schema into body
    if post_data.get("faqs"):
        post_data["body_html"] += build_faq_schema(post_data["faqs"])

    print(f"\n Post written: '{post_data['title']}'")
    print(f"   Meta title ({len(post_data['meta_title'])} chars): {post_data['meta_title']}")
    print(f"   Meta desc ({len(post_data['meta_description'])} chars): {post_data['meta_description']}")
    return post_data


# ── Step 4: Send to Make webhook ───────────────────────────────────────────

def publish_via_make(post_data, keyword_data, cover_image_url=None):
    """Send post data to Make webhook which publishes to Shopify."""

    payload = {
        "title":            post_data["title"],
        "body_html":        post_data["body_html"],
        "meta_title":       post_data["meta_title"],
        "meta_description": post_data["meta_description"],
        "tags":             ", ".join(post_data.get("tags", [])),
        "keyword":          keyword_data["keyword"],
        "published":        True
    }
    if cover_image_url:
        payload["cover_image_url"] = cover_image_url

    response = requests.post(MAKE_WEBHOOK_URL, json=payload)
    response.raise_for_status()

    print(f"\n Sent to Make webhook successfully")
    return payload


# ── Step 5: Log the run ────────────────────────────────────────────────────

def log_run(keyword_data, post_data, article):
    """Append run details to a log file."""

    log_entry = {
        "date":        str(datetime.date.today()),
        "keyword":     keyword_data["keyword"],
        "impressions": keyword_data["impressions"],
        "position":    keyword_data["position"],
        "title":       post_data["title"]
    }

    log_file = "publish_log.json"
    logs = []

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            logs = json.load(f)

    logs.append(log_entry)

    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

    print(f"\n Logged to {log_file}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Boring Studios Blog Machine")
    print("=" * 40)

    print("\n[1/6] Pulling keyword opportunities from GSC...")
    opportunities = get_keyword_opportunities()
    print(f"   Found {len(opportunities)} opportunities")

    print("\n[2/6] Selecting keyword...")
    keyword_data = select_keyword(opportunities)

    print("\n[3/6] Writing post with Claude...")
    post_data = write_post(keyword_data)

    print("\n[4/6] Generating cover image...")
    image_bytes = generate_cover_image(post_data["title"], post_data.get("tags", []), post_data["body_html"], post_data.get("cover_title", ""), post_data.get("cover_subtitle", ""))
    cover_image_url = upload_cover_image(image_bytes)

    print("\n[5/6] Sending to Make...")
    article = publish_via_make(post_data, keyword_data, cover_image_url)

    print("\n[6/6] Logging run...")
    log_run(keyword_data, post_data, article)

    print("\n Done. Post is live.")


if __name__ == "__main__":
    main()
