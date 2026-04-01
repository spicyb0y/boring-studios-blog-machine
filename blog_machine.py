"""
Boring Studios — Automated SEO Blog Machine
Pulls keyword opportunities from Google Search Console,
writes a full post using Claude API in Boring Studios TOV,
and publishes it to the Shopify blog.
"""

import os
import json
import random
import datetime
import requests
from anthropic import Anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ─────────────────────────────────────────────────────────────────

GSC_SITE_URL        = "https://boringstudios.com.au"
GSC_KEY_FILE        = "gsc-service-account.json"   # path to your downloaded JSON key
SHOPIFY_STORE       = "boringstudios.myshopify.com"
SHOPIFY_TOKEN       = os.environ["SHOPIFY_TOKEN"]   # set in GitHub Actions secrets
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
SHOPIFY_BLOG_ID     = "86091120946"                 # notes-from-the-studio blog ID
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
When linking to Boring Studios products, frame as a helpful next step, never a hard sell.
Example: "If you want a head start, we built [product] for exactly this."
Only link 1-2 products per post. Choose from: https://boringstudios.com.au/collections/all

OUTPUT FORMAT
Return a JSON object with these exact keys:
{
  "title": "Post title (H1, sentence case)",
  "meta_title": "Meta title (under 60 chars, sentence case)",
  "meta_description": "Meta description (under 120 chars, includes keyword)",
  "body_html": "Full post body as HTML with proper H2/H3 tags, paragraphs, lists. No H1 in body.",
  "tags": ["tag1", "tag2", "tag3"],
  "summary": "One sentence summary of the post"
}
"""

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
- Meta title under 60 characters
- Meta description under 120 characters
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

    post_data = json.loads(content)
    print(f"\n Post written: '{post_data['title']}'")
    print(f"   Meta title ({len(post_data['meta_title'])} chars): {post_data['meta_title']}")
    print(f"   Meta desc ({len(post_data['meta_description'])} chars): {post_data['meta_description']}")
    return post_data


# ── Step 4: Publish to Shopify ─────────────────────────────────────────────

def publish_to_shopify(post_data, keyword_data):
    """Publish the post to the Boring Studios Shopify blog."""

    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/blogs/{SHOPIFY_BLOG_ID}/articles.json"

    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "article": {
            "title":          post_data["title"],
            "body_html":      post_data["body_html"],
            "summary_html":   post_data["meta_description"],
            "tags":           ", ".join(post_data.get("tags", [])),
            "published":      True,
            "metafields": [
                {
                    "key":       "title_tag",
                    "value":     post_data["meta_title"],
                    "type":      "single_line_text_field",
                    "namespace": "global"
                },
                {
                    "key":       "description_tag",
                    "value":     post_data["meta_description"],
                    "type":      "single_line_text_field",
                    "namespace": "global"
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    article = response.json()["article"]
    article_url = f"{SITE_URL}/blogs/notes-from-the-studio/{article['handle']}"

    print(f"\n Published: {article_url}")
    return article


# ── Step 5: Log the run ────────────────────────────────────────────────────

def log_run(keyword_data, post_data, article):
    """Append run details to a log file."""

    log_entry = {
        "date":        str(datetime.date.today()),
        "keyword":     keyword_data["keyword"],
        "impressions": keyword_data["impressions"],
        "position":    keyword_data["position"],
        "title":       post_data["title"],
        "url":         f"{SITE_URL}/blogs/notes-from-the-studio/{article['handle']}",
        "article_id":  article["id"]
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

    print("\n[1/5] Pulling keyword opportunities from GSC...")
    opportunities = get_keyword_opportunities()
    print(f"   Found {len(opportunities)} opportunities")

    print("\n[2/5] Selecting keyword...")
    keyword_data = select_keyword(opportunities)

    print("\n[3/5] Writing post with Claude...")
    post_data = write_post(keyword_data)

    print("\n[4/5] Publishing to Shopify...")
    article = publish_to_shopify(post_data, keyword_data)

    print("\n[5/5] Logging run...")
    log_run(keyword_data, post_data, article)

    print("\n Done. Post is live.")


if __name__ == "__main__":
    main()
