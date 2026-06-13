import re
import sys
from dataclasses import dataclass

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.threads.net"


@dataclass
class ThreadPost:
    post_id: str
    author: str
    content: str
    url: str


def search_threads(keyword: str, max_results: int = 20) -> list[ThreadPost]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-TW",
        )
        page = context.new_page()

        search_url = f"{BASE_URL}/search?q={keyword}&serp_type=default"
        page.goto(search_url, wait_until="domcontentloaded")

        try:
            page.wait_for_selector("a[href*='/post/']", timeout=15000)
        except Exception:
            print(f"  No posts found for '{keyword}'", file=sys.stderr)
            browser.close()
            return []

        # Extract post data via JS to avoid repeated Python↔browser round-trips
        raw_posts: list[dict] = page.evaluate("""
            (maxResults) => {
                const seen = new Set();
                const results = [];
                const links = document.querySelectorAll('a[href*="/post/"]');

                for (const link of links) {
                    if (results.length >= maxResults) break;

                    const href = link.getAttribute('href');
                    const match = href && href.match(/\\/@([^\\/]+)\\/post\\/([^\\/?#]+)/);
                    if (!match) continue;

                    const postId = match[2];
                    if (seen.has(postId)) continue;
                    seen.add(postId);

                    // Walk up to the article/post container for content
                    let container = link;
                    for (let i = 0; i < 8; i++) {
                        const parent = container.parentElement;
                        if (!parent) break;
                        container = parent;
                        if (container.tagName === 'ARTICLE') break;
                    }

                    results.push({
                        href: href,
                        author: match[1],
                        post_id: postId,
                        content: (container.innerText || '').trim().substring(0, 500),
                    });
                }
                return results;
            }
        """, max_results)

        browser.close()

    posts = []
    for item in raw_posts:
        posts.append(ThreadPost(
            post_id=item["post_id"],
            author=item["author"],
            content=item["content"],
            url=BASE_URL + item["href"],
        ))
    return posts
