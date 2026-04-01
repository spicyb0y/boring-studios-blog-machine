"""
Run this once to find your Shopify blog ID for notes-from-the-studio.
Usage: SHOPIFY_TOKEN=your_token python get_blog_id.py
"""

import os
import requests

SHOPIFY_STORE = "boringstudios.myshopify.com"
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]

url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/blogs.json"
headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

response = requests.get(url, headers=headers)
blogs = response.json()["blogs"]

for blog in blogs:
    print(f"ID: {blog['id']}  |  Title: {blog['title']}  |  Handle: {blog['handle']}")
