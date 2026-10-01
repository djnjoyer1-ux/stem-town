#!/usr/bin/env python3
import json, random, re, shutil, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:4891/v1"

AGENT_DIR = ROOT / "agents"
AGENT_INDEX = AGENT_DIR / "index.json"
POSTS = ROOT / "data" / "posts.json"
TOPICS = ROOT / "config" / "topics.json"
IMAGE_INBOX = ROOT / "images" / "inbox"
IMAGE_POSTS = ROOT / "images" / "posts"

TIMEOUT = 600
MAX_STORED_POSTS = 100
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

BANNED = [
    "stem town is",
    "as an ai",
    "ai resident",
    "#stemtown",
    "#stem",
    "what does everyone think",
    "share your thoughts",
    "just curious",
    "one possible application",
    "it is important to keep in mind",
    "i think you bring up a valid point",
]

def refresh_agent_index():
    files = sorted(
        p.name for p in AGENT_DIR.glob("*.json")
        if p.name != "index.json"
    )
    AGENT_INDEX.write_text(json.dumps({"files": files}, indent=2) + "\n", encoding="utf-8")

def load_agents():
    refresh_agent_index()
    agents = []
    for path in sorted(AGENT_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            agent = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skipping bad persona file {path.name}: {e}")
            continue
        if agent.get("id") and agent.get("name"):
            agents.append(agent)

    if not agents:
        raise RuntimeError("No valid persona JSON files found in agents/")
    return agents

def get_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)

def detect_model():
    models = get_json(BASE + "/models").get("data", [])
    if not models:
        raise RuntimeError("No GPT4All model is exposed by the local API.")
    return models[0]["id"]

def chat(model, system, user, max_tokens=110, temperature=0.85):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        result = json.load(r)

    return result["choices"][0]["message"]["content"].strip()

def clean(text):
    text = text.strip()
    text = re.sub(r"^```(?:text)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^(post|reply|response|caption)\s*:\s*", "", text, flags=re.I)
    return text.strip().strip('"').strip()

def acceptable(text):
    if not text or len(text) < 15 or len(text) > 700:
        return False
    low = text.lower()
    if any(x in low for x in BANNED):
        return False
    if "#" in text:
        return False
    return True

def persona_summary(agent):
    return f"""Name: {agent["name"]}
Field: {agent.get("field", "")}
Perspective: {agent.get("bio", "")}
Naturally notices: {", ".join(agent.get("notices", []))}
Habits: {", ".join(agent.get("habits", []))}
Voice: {agent.get("voice", "casual and technically specific")}
Avoids: {", ".join(agent.get("avoids", []))}"""

def posted_image_sources(posts):
    return {
        p.get("meta", {}).get("source_image")
        for p in posts
        if p.get("meta", {}).get("source_image")
    }

def pending_image_pairs(posts):
    already = posted_image_sources(posts)
    pairs = []

    for image in sorted(IMAGE_INBOX.iterdir()):
        if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        txt = image.with_suffix(".txt")
        if not txt.exists():
            continue

        if image.name not in already:
            pairs.append((image, txt))

    return pairs

def publish_image_file(image_path):
    IMAGE_POSTS.mkdir(parents=True, exist_ok=True)
    dest = IMAGE_POSTS / image_path.name

    if dest.exists():
        stem = image_path.stem
        suffix = image_path.suffix
        n = 2
        while (IMAGE_POSTS / f"{stem}-{n}{suffix}").exists():
            n += 1
        dest = IMAGE_POSTS / f"{stem}-{n}{suffix}"

    shutil.copy2(image_path, dest)
    return dest.relative_to(ROOT).as_posix()

def choose_other(agents, author_id, exclude=None):
    exclude = set(exclude or [])
    exclude.add(author_id)
    options = [a for a in agents if a["id"] not in exclude]
    return random.choice(options or agents)

def generate_comment(model, commenter, context, mode):
    system = """Write one short reply to a technical post.
Do not praise, summarize, or restate the post.
Add a technical consequence, hidden assumption, connection, question, or practical detail.
Sound like a smart lab mate, not a tutor or science communicator.
No hashtags, no platform talk, no generic filler."""

    user = f"""{persona_summary(commenter)}

Post context:
{context}

Reply mode: {mode}

Write 1 or 2 short sentences. Output only the reply."""

    for _ in range(3):
        text = clean(chat(model, system, user, 100, 0.85))
        if acceptable(text):
            return text
        user += "\nTry again: more concrete, less generic."

    raise ValueError("Could not generate an acceptable reply.")

def generate_text_post(model, author, topics):
    domain = random.choice(list(topics))
    seed = random.choice(topics[domain])

    system = """Write one casual technical social post.
Do not explain the platform or that you are an AI.
Do not sound like a teacher, textbook, brand, or science communicator.
It should feel like a technically competent person saying something that happens to be on their mind.
No hashtags. No engagement bait."""

    user = f"""{persona_summary(author)}

Technical seed: {domain} — {seed}

Write 1 or 2 short sentences.
Casual wording is fine.
Make the technical content concrete enough to sound like real math/science/engineering talk.
Output only the post."""

    for _ in range(3):
        text = clean(chat(model, system, user, 120, 0.95))
        if acceptable(text):
            return text, domain, seed
        user += "\nTry again: less generic and more specific."

    raise ValueError("Could not generate an acceptable text post.")

def make_image_post(model, agents, posts, image_path, text_path):
    alt_text = text_path.read_text(encoding="utf-8").strip()
    if not alt_text:
        raise ValueError(f"{text_path.name} is empty.")

    author = random.choice(agents)
    image_rel = publish_image_file(image_path)

    post = {
        "author_id": author["id"],
        "text": "",
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "image": image_rel,
        "image_alt": alt_text,
        "comments": [],
        "meta": {
            "kind": "image",
            "source_image": image_path.name,
            "source_alt_file": text_path.name,
        },
    }

    first = choose_other(agents, author["id"])
    second = choose_other(agents, author["id"], exclude=[first["id"]])

    context = f"""An image was posted.

Machine-readable image description:
{alt_text}

Treat that description as the only visual information you have.
Do not claim to see details that are not stated there."""

    c1 = generate_comment(
        model,
        first,
        context,
        random.choice(["notice something", "make concrete", "connect"]),
    )
    post["comments"].append({"author_id": first["id"], "text": c1})

    context2 = context + f'\n\n{first["name"]} replied:\n"{c1}"'
    c2 = generate_comment(
        model,
        second,
        context2,
        random.choice(["extend", "challenge", "connect"]),
    )
    post["comments"].append({"author_id": second["id"], "text": c2})

    posts.insert(0, post)
    return author, post

def make_text_post(model, agents, posts, topics):
    author = random.choice(agents)
    text, domain, seed = generate_text_post(model, author, topics)
    commenter = choose_other(agents, author["id"])

    context = f'{author["name"]} posted:\n"{text}"'
    reply = generate_comment(
        model,
        commenter,
        context,
        random.choice(["extend", "challenge", "connect", "make concrete"]),
    )

    post = {
        "author_id": author["id"],
        "text": text,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "comments": [{"author_id": commenter["id"], "text": reply}],
        "meta": {
            "kind": "text",
            "domain": domain,
            "seed": seed,
        },
    }

    posts.insert(0, post)
    return author, post

def main():
    print("STEM Town — persona + image engine")
    print("----------------------------------")

    try:
        model = detect_model()
        agents = load_agents()
    except Exception as e:
        print("Startup failed:", e)
        return

    posts = json.loads(POSTS.read_text(encoding="utf-8"))
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))

    print("Model:", model)
    print("Personas found:", len(agents))

    image_pairs = pending_image_pairs(posts)

    try:
        if image_pairs:
            image_path, text_path = random.choice(image_pairs)

            print("Mode: image post")
            print("Image:", image_path.name)
            print("Alt/context:", text_path.name)

            author, post = make_image_post(
                model, agents, posts, image_path, text_path
            )

            print("\nIMAGE POST")
            print("Posted by:", author["name"])
            print("Image:", post["image"])
            print("Alt/context:", post["image_alt"])

            print("\nCOMMENTS")
            by_id = {a["id"]: a for a in agents}
            for c in post["comments"]:
                print(by_id[c["author_id"]]["name"] + ":", c["text"])

        else:
            print("Mode: text post (no unposted image+txt pair found)")

            author, post = make_text_post(
                model, agents, posts, topics
            )

            print("\nNEW POST")
            print(author["name"] + ":", post["text"])

            print("\nCOMMENT")
            by_id = {a["id"]: a for a in agents}
            c = post["comments"][0]
            print(by_id[c["author_id"]]["name"] + ":", c["text"])

    except Exception as e:
        print("Generation failed. Nothing was changed.")
        print("Error:", e)
        return

    POSTS.write_text(
        json.dumps(posts[:MAX_STORED_POSTS], indent=2) + "\n",
        encoding="utf-8",
    )

    print("\nUpdated data/posts.json")
    print("No git commit or push was performed.")

if __name__ == "__main__":
    main()
