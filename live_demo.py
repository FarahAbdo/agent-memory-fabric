"""
╔══════════════════════════════════════════════════════════════╗
║  LIVE DEMO — Agent Memory Fabric                            ║
║  Azure Cosmos DB Conf 2026 | Farah Abdou                    ║
║                                                             ║
║  Run:  python live_demo.py                                  ║
╚══════════════════════════════════════════════════════════════╝

Single-file, 2-minute live demo for stage.
Shows the semantic cache in action: 3 agents, 3 queries,
1 cache hit saves an LLM call. Opens with a dashboard,
closes with cost impact.
"""

import time
import uuid
from openai import OpenAI
from azure.cosmos import CosmosClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich import box

from config import (
    COSMOS_ENDPOINT, COSMOS_KEY, DATABASE_NAME, CONTAINER_MEMORY,
    OPENAI_API_KEY, EMBEDDING_MODEL, CHAT_MODEL, SIMILARITY_THRESHOLD,
    validate_config,
)

console = Console(width=72)


# ─────────────────────────────────────────────────────────────
#  COSMOS DB QUERY — this is what the audience needs to see
# ─────────────────────────────────────────────────────────────

VECTOR_SEARCH_SQL = """
SELECT TOP 1
    c.question, c.response,
    VectorDistance(c.embedding, @v) AS similarity
FROM   c
WHERE  c.type = 'semantic-cache'
ORDER BY VectorDistance(c.embedding, @v)
"""


# ─────────────────────────────────────────────────────────────
#  AGENTS
# ─────────────────────────────────────────────────────────────

AGENTS = [
    {"name": "Support Agent",  "color": "bright_blue",
     "query": "What is the refund policy for electronics?"},
    {"name": "Returns Agent",  "color": "bright_green",
     "query": "How can I return an electronic product?"},
    {"name": "Product Agent",  "color": "bright_yellow",
     "query": "What is the warranty on laptops?"},
]


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def embed(client: OpenAI, text: str) -> list[float]:
    return client.embeddings.create(
        model=EMBEDDING_MODEL, input=text
    ).data[0].embedding


def ask_llm(client: OpenAI, question: str) -> tuple[str, int]:
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system",
             "content": "You are a concise customer-service agent."},
            {"role": "user", "content": question},
        ],
        max_tokens=120,
    )
    return r.choices[0].message.content, r.usage.total_tokens


def cache_lookup(container, vector: list[float]) -> dict | None:
    rows = list(container.query_items(
        query=VECTOR_SEARCH_SQL,
        parameters=[{"name": "@v", "value": vector}],
        enable_cross_partition_query=True,
    ))
    if rows and rows[0]["similarity"] > SIMILARITY_THRESHOLD:
        return rows[0]
    return None


def cache_store(container, q: str, resp: str, vec: list[float]):
    container.upsert_item({
        "id": str(uuid.uuid4()), "threadId": "cache",
        "type": "semantic-cache", "question": q,
        "response": resp, "embedding": vec,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hitCount": 0,
    })


# ─────────────────────────────────────────────────────────────
#  OPENING DASHBOARD
# ─────────────────────────────────────────────────────────────

def show_dashboard():
    console.print()
    console.print(Panel(
        "[bold white]AGENT MEMORY FABRIC[/]\n"
        "[dim]Azure Cosmos DB as the unified memory layer "
        "for multi-agent AI[/]",
        border_style="bright_white", padding=(1, 4),
    ))

    cards = [
        Panel(
            "[bold bright_blue]Semantic\nCaching[/]\n\n"
            "[dim]DiskANN vector search\n"
            "eliminates duplicate\n"
            "LLM calls across\n"
            "agents[/]",
            border_style="bright_blue",
            width=22, padding=(1, 2),
        ),
        Panel(
            "[bold bright_green]Change\nFeed[/]\n\n"
            "[dim]Database writes\n"
            "trigger agent\n"
            "handoffs — zero\n"
            "message queues[/]",
            border_style="bright_green",
            width=22, padding=(1, 2),
        ),
        Panel(
            "[bold bright_magenta]Optimistic\nConcurrency[/]\n\n"
            "[dim]ETag checks\n"
            "prevent state\n"
            "corruption from\n"
            "parallel writes[/]",
            border_style="bright_magenta",
            width=22, padding=(1, 2),
        ),
    ]
    console.print(Columns(cards, padding=(0, 1), align="center"))
    console.print()
    time.sleep(2)


# ─────────────────────────────────────────────────────────────
#  LIVE DEMO LOOP
# ─────────────────────────────────────────────────────────────

def run_demo():

    show_dashboard()

    if not validate_config():
        return

    cosmos = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    container = cosmos.get_database_client(
        DATABASE_NAME
    ).get_container_client(CONTAINER_MEMORY)
    ai = OpenAI(api_key=OPENAI_API_KEY)

    console.print(Panel(
        VECTOR_SEARCH_SQL.strip(),
        title="[bold]Cosmos DB query used for cache lookup[/]",
        border_style="dim", padding=(0, 2),
    ))
    time.sleep(2)

    # ── Metrics accumulators ──
    rows = []               # for summary table
    llm_calls = 0
    cache_hits = 0
    tokens_used = 0
    tokens_saved = 0

    for agent in AGENTS:
        name  = agent["name"]
        color = agent["color"]
        query = agent["query"]

        console.print(f"\n[bold {color}]{name}[/]")
        console.print(f'[white]"{query}"[/]\n')

        # 1 — embed the question
        vec = embed(ai, query)

        # 2 — search the cache
        t0 = time.time()
        hit = cache_lookup(container, vec)
        ms = (time.time() - t0) * 1000

        if hit:
            cache_hits += 1
            est_saved = len(hit["response"].split()) + len(query.split())
            tokens_saved += est_saved
            console.print(
                f"  [bold green]CACHE HIT[/]  "
                f"similarity [green]{hit['similarity']:.2f}[/]  "
                f"[dim]{ms:.0f} ms[/]"
            )
            console.print(f"  [dim]Matched:[/] \"{hit['question']}\"")
            answer = hit["response"]
            rows.append((name, query[:36] + "...",
                         f"[green]HIT[/]",
                         f"{hit['similarity']:.2f}",
                         f"{ms:.0f} ms", "0"))
        else:
            llm_calls += 1
            console.print(
                f"  [red]CACHE MISS[/]  [dim]{ms:.0f} ms[/]"
            )
            console.print("  [dim]Calling LLM...[/]", end=" ")
            t0 = time.time()
            answer, tok = ask_llm(ai, query)
            llm_ms = (time.time() - t0) * 1000
            tokens_used += tok
            console.print(f"[dim]{llm_ms:.0f} ms  {tok} tokens[/]")
            cache_store(container, query, answer, vec)
            console.print("  [dim]Stored in cache.[/]")
            rows.append((name, query[:36] + "...",
                         f"[red]MISS[/]",
                         "—",
                         f"{llm_ms:.0f} ms", str(tok)))

        console.print(f"\n  [white]{answer[:160]}[/]")
        time.sleep(1.5)

    # ── RESULTS TABLE ──
    console.print(f"\n{'━' * 72}\n")
    tbl = Table(
        title="Results",
        box=box.HEAVY_HEAD,
        header_style="bold",
        show_lines=False,
    )
    tbl.add_column("Agent")
    tbl.add_column("Query")
    tbl.add_column("Cache", justify="center")
    tbl.add_column("Sim.", justify="center")
    tbl.add_column("Latency", justify="right")
    tbl.add_column("Tokens", justify="right")
    for r in rows:
        tbl.add_row(*r)
    console.print(tbl)

    # ── COST IMPACT PANEL ──
    cost_tok = 0.015           # $ per 1K tokens (gpt-4o-mini approx)
    saved_usd = (tokens_saved / 1000) * cost_tok
    daily_queries = 10_000
    monthly_factor = daily_queries * 30 * (cache_hits / len(AGENTS))
    monthly_usd = (monthly_factor * (tokens_saved / cache_hits if cache_hits else 1) / 1000) * cost_tok

    impact = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    impact.add_column(style="dim", min_width=28)
    impact.add_column(style="bold white", justify="right")
    impact.add_row("LLM calls made",      str(llm_calls))
    impact.add_row("LLM calls avoided",   f"[bold green]{cache_hits}[/]")
    impact.add_row("Tokens consumed",      f"{tokens_used:,}")
    impact.add_row("Tokens saved",         f"[green]~{tokens_saved:,}[/]")
    impact.add_row("Cost saved (this run)",f"[green]~${saved_usd:.4f}[/]")
    impact.add_row("", "")
    impact.add_row(
        "Projected monthly saving",
        f"[bold bright_green]~${monthly_usd:,.0f}[/]"
    )
    impact.add_row(
        "[dim](at 10K queries/day)[/]", ""
    )
    console.print(Panel(impact, title="[bold]Cost Impact[/]",
                        border_style="green", padding=(1, 2)))

    # ── CLOSING ──
    console.print(Panel(
        "[bold white]One database. Three capabilities.[/]\n\n"
        "[bright_blue]Semantic Cache[/]  →  "
        "[bright_green]Change Feed[/]  →  "
        "[bright_magenta]ETag Concurrency[/]\n\n"
        "[dim]No Redis. No Pinecone. No RabbitMQ.\n"
        "Just Azure Cosmos DB.[/]",
        border_style="bright_white", padding=(1, 4),
    ))


if __name__ == "__main__":
    console.clear()
    run_demo()
