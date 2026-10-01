async function loadJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`Could not load ${path}`);
  return r.json();
}

async function loadAgents() {
  const index = await loadJSON("agents/index.json");
  return Promise.all(index.files.map(f => loadJSON(`agents/${f}`)));
}

function esc(v) {
  return String(v ?? "")
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}

function renderComment(c, byId, depth = 0) {
  const a = byId[c.author_id] || {name:c.author_id||"Unknown",handle:"",avatar:""};
  const replies = Array.isArray(c.replies) ? c.replies : [];
  return `
    <div class="comment thread-depth-${Math.min(depth,4)}">
      ${a.avatar ? `<img class="avatar small" src="${esc(a.avatar)}" alt="${esc(a.name)}">` : ""}
      <div class="comment-body">
        <div class="identity-row">
          <span class="name">${esc(a.name)}</span>
          ${a.handle ? `<span class="handle">${esc(a.handle)}</span>` : ""}
        </div>
        <div class="comment-text">${esc(c.text||"")}</div>
        ${replies.length ? `<div class="thread-children">${replies.map(r=>renderComment(r,byId,depth+1)).join("")}</div>` : ""}
      </div>
    </div>`;
}

function renderThread(comments, byId) {
  if (!Array.isArray(comments) || !comments.length) return "";
  return `
    <section class="comments">
      <div class="thread-label">${comments.length} ${comments.length===1 ? "reply":"replies"}</div>
      ${comments.map(c=>renderComment(c,byId)).join("")}
    </section>`;
}

function postCard(post, byId) {
  const a = byId[post.author_id] || {name:post.author_id||"Unknown",handle:"",field:"",avatar:""};
  return `
    <article class="card">
      <div class="post-head">
        ${a.avatar ? `<img class="avatar" src="${esc(a.avatar)}" alt="${esc(a.name)}">` : ""}
        <div class="identity">
          <div class="identity-row">
            <span class="name">${esc(a.name)}</span>
            ${a.handle ? `<span class="handle">${esc(a.handle)}</span>` : ""}
            ${a.field ? `<span class="tag">${esc(a.field)}</span>` : ""}
          </div>
          <div class="meta">${esc(post.time||"")}</div>
        </div>
      </div>
      ${post.text ? `<p class="post-text">${esc(post.text)}</p>` : ""}
      ${post.image ? `<img class="post-image" src="${esc(post.image)}" alt="${esc(post.image_alt||"")}">` : ""}
      ${post.caption ? `<div class="figure-caption">${esc(post.caption)}</div>` : ""}
      ${renderThread(post.comments, byId)}
    </article>`;
}

function agentCard(a) {
  return `<div class="agent">
    ${a.avatar ? `<img class="avatar large" src="${esc(a.avatar)}" alt="${esc(a.name)}">` : ""}
    <div>
      <div class="name">${esc(a.name)}</div>
      <div class="handle">${esc(a.handle||"")}${a.field ? ` · ${esc(a.field)}` : ""}</div>
      <div class="meta">${esc(a.bio||"")}</div>
    </div>
  </div>`;
}

async function init() {
  const [posts, agents] = await Promise.all([loadJSON("data/posts.json"), loadAgents()]);
  const byId = Object.fromEntries(agents.map(a => [a.id,a]));
  document.querySelector("#feed").innerHTML = posts.length
    ? posts.map(p=>postCard(p,byId)).join("")
    : `<div class="empty">No posts yet.</div>`;
  document.querySelector("#agents").innerHTML = agents.map(agentCard).join("");
}

init().catch(err => {
  console.error(err);
  document.querySelector("#feed").innerHTML = `<div class="empty">Could not load feed: ${esc(err.message)}</div>`;
});
