"""
Database Setup — Creates containers and seeds sample data.
Run this once before the demo.

Usage:
    python setup_database.py
"""

import uuid
import time
import numpy as np
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceExistsError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

import config

console = Console()


# ─── STEP 1: Connect to Cosmos DB ──────────────────────────────────

def get_client() -> CosmosClient:
    """Create an authenticated Cosmos DB client."""
    return CosmosClient(config.COSMOS_ENDPOINT, config.COSMOS_KEY)


# ─── STEP 2: Create Database and Containers ────────────────────────

def create_database(client: CosmosClient):
    """Create the database if it doesn't exist."""
    console.print("\n[bold cyan]Creating database...[/]")
    db = client.create_database_if_not_exists(id=config.DATABASE_NAME)
    console.print(f"  Database [green]{config.DATABASE_NAME}[/] ready.")
    return db


def create_containers(db):
    """
    Create three containers for the demo:
    1. agent-memory  — semantic cache + conversation history (with vector policy)
    2. agent-events  — Change Feed event-driven coordination
    3. shared-state  — optimistic concurrency demo
    """
    containers = {}

    # ── Container 1: Agent Memory (with vector index) ──
    console.print("\n[bold cyan]Creating agent-memory container...[/]")
    console.print("  [dim]Vector policy: DiskANN, 1536 dimensions, cosine distance[/]")

    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": config.EMBEDDING_DIMENSIONS
            }
        ]
    }

    indexing_policy = {
        "indexingMode": "consistent",
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [{"path": "/embedding/*"}],
        "vectorIndexes": [
            {"path": "/embedding", "type": "diskANN"}
        ]
    }

    try:
        containers["memory"] = db.create_container(
            id=config.CONTAINER_MEMORY,
            partition_key=PartitionKey(path="/threadId"),
            vector_embedding_policy=vector_embedding_policy,
            indexing_policy=indexing_policy,
        )
    except CosmosResourceExistsError:
        containers["memory"] = db.get_container_client(config.CONTAINER_MEMORY)

    console.print(f"  Container [green]{config.CONTAINER_MEMORY}[/] ready (DiskANN vector index).")

    # ── Container 2: Agent Events ──
    console.print("\n[bold cyan]Creating agent-events container...[/]")
    try:
        containers["events"] = db.create_container(
            id=config.CONTAINER_EVENTS,
            partition_key=PartitionKey(path="/agentId"),
        )
    except CosmosResourceExistsError:
        containers["events"] = db.get_container_client(config.CONTAINER_EVENTS)

    console.print(f"  Container [green]{config.CONTAINER_EVENTS}[/] ready.")

    # ── Container 3: Shared State ──
    console.print("\n[bold cyan]Creating shared-state container...[/]")
    try:
        containers["state"] = db.create_container(
            id=config.CONTAINER_STATE,
            partition_key=PartitionKey(path="/stateKey"),
        )
    except CosmosResourceExistsError:
        containers["state"] = db.get_container_client(config.CONTAINER_STATE)

    console.print(f"  Container [green]{config.CONTAINER_STATE}[/] ready.")
    return containers


# ─── STEP 3: Seed Sample Data ───────────────────────────────────────

def generate_fake_embedding(text: str, dims: int = 1536) -> list[float]:
    """
    Generate a deterministic pseudo-embedding from text.
    Uses a seeded random generator so similar texts produce similar vectors.
    For the real demo, replace with OpenAI embeddings.
    """
    seed = sum(ord(c) for c in text.lower().replace(" ", ""))
    rng = np.random.RandomState(seed)
    vec = rng.randn(dims).astype(np.float32)
    vec = vec / np.linalg.norm(vec)  # L2 normalize
    return vec.tolist()


# Pre-built cache entries — questions agents commonly ask
SEED_CACHE_ENTRIES = [
    {
        "question": "What is the refund policy for electronics?",
        "response": "Electronics can be returned within 30 days of purchase with original receipt. Items must be in original packaging and unused condition. A 15% restocking fee applies after 14 days.",
    },
    {
        "question": "How do I track my order status?",
        "response": "You can track your order by logging into your account and navigating to Order History. You will also receive email notifications at each shipping milestone.",
    },
    {
        "question": "What payment methods are accepted?",
        "response": "We accept Visa, Mastercard, American Express, PayPal, and Apple Pay. Bank transfers are available for orders over $500.",
    },
    {
        "question": "What are the shipping options and costs?",
        "response": "Standard shipping (5-7 days) is free for orders over $50. Express shipping (2-3 days) is $9.99. Next-day delivery is $19.99 and available in select metro areas.",
    },
    {
        "question": "How do I contact customer support?",
        "response": "Customer support is available 24/7 via live chat on our website. You can also call 1-800-555-0199 or email support@example.com. Average response time is under 2 minutes.",
    },
    {
        "question": "What is the warranty coverage for laptops?",
        "response": "All laptops come with a 1-year manufacturer warranty covering hardware defects. Extended 3-year warranties are available for $149. Accidental damage protection can be added for $79/year.",
    },
    {
        "question": "Can I change my delivery address after ordering?",
        "response": "Address changes are possible within 1 hour of order placement. After that, you will need to contact support. Orders already shipped cannot have their address changed.",
    },
    {
        "question": "What is your price matching policy?",
        "response": "We match prices from authorized retailers within 14 days of purchase. Bring proof of the lower price to any store or submit it online. Marketplace sellers and flash sales are excluded.",
    },
    {
        "question": "How do I apply a discount code?",
        "response": "Enter your discount code in the Promo Code field at checkout and click Apply. Only one code can be used per order. Codes are case-sensitive and have expiration dates.",
    },
    {
        "question": "What is the process for bulk orders?",
        "response": "Bulk orders of 50+ units qualify for volume discounts of 10-25%. Contact our B2B team at business@example.com or call ext. 400. Lead time is typically 5-10 business days.",
    },
]


def seed_cache_data(container):
    """Seed the agent-memory container with pre-embedded cache entries."""
    console.print("\n[bold cyan]Seeding semantic cache data...[/]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Inserting cache entries...", total=len(SEED_CACHE_ENTRIES))

        for i, entry in enumerate(SEED_CACHE_ENTRIES):
            doc = {
                "id": str(uuid.uuid4()),
                "threadId": "cache",
                "turnIndex": i,
                "type": "semantic-cache",
                "question": entry["question"],
                "response": entry["response"],
                "embedding": generate_fake_embedding(entry["question"]),
                "timestamp": "2026-03-26T10:00:00Z",
                "hitCount": 0,
                "metadata": {"source": "seed", "tokens": len(entry["response"].split())}
            }
            container.upsert_item(doc)
            progress.update(task, advance=1)

    console.print(f"  [green]{len(SEED_CACHE_ENTRIES)} cache entries seeded.[/]")


def seed_state_document(container):
    """Seed an initial shared state document for the concurrency demo."""
    console.print("\n[bold cyan]Seeding shared state document...[/]")
    doc = {
        "id": "customer-session-001",
        "stateKey": "session",
        "customerId": "C-1042",
        "status": "active",
        "context": {
            "topic": "product inquiry",
            "sentiment": "neutral",
            "entities": ["laptop", "warranty"]
        },
        "agentNotes": {},
        "lastUpdatedBy": "system",
        "version": 1
    }
    container.upsert_item(doc)
    console.print("  [green]Shared state document ready.[/]")


# ─── MAIN ───────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold white]Agent Memory Fabric — Database Setup[/]\n"
        "[dim]Creates containers and seeds sample data for the demo.[/]",
        border_style="cyan",
        padding=(1, 2)
    ))

    if not config.validate_config():
        return

    client = get_client()
    db = create_database(client)
    containers = create_containers(db)
    seed_cache_data(containers["memory"])
    seed_state_document(containers["state"])

    # ── Summary ──
    summary = Table(title="Setup Complete", show_header=True, header_style="bold cyan")
    summary.add_column("Container", style="white")
    summary.add_column("Partition Key", style="dim")
    summary.add_column("Purpose", style="green")
    summary.add_row(config.CONTAINER_MEMORY, "/threadId", "Semantic cache + agent memory")
    summary.add_row(config.CONTAINER_EVENTS, "/agentId", "Change Feed coordination")
    summary.add_row(config.CONTAINER_STATE, "/stateKey", "Optimistic concurrency")
    console.print(summary)
    console.print("\n[bold green]Setup complete. Ready for demo.[/]\n")


if __name__ == "__main__":
    main()
