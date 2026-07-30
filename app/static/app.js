const PAGE_SIZE = 10;
let currentOffset = 0;

const sayForm = document.getElementById("say-form");
const sayInput = document.getElementById("say-input");
const sayError = document.getElementById("say-error");
const output = document.getElementById("output");
const recentList = document.getElementById("recent-list");
const messagesBody = document.getElementById("messages-body");
const prevPageBtn = document.getElementById("prev-page");
const nextPageBtn = document.getElementById("next-page");
const pageIndicator = document.getElementById("page-indicator");

function showError(text) {
  sayError.textContent = text;
  sayError.classList.remove("hidden");
}

function clearError() {
  sayError.textContent = "";
  sayError.classList.add("hidden");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function loadRecent() {
  recentList.innerHTML = "<li>Loading...</li>";
  try {
    const response = await fetch("/recent");
    if (!response.ok) throw new Error(`status ${response.status}`);
    const items = await response.json();
    if (items.length === 0) {
      recentList.innerHTML = "<li>nothing said yet</li>";
      return;
    }
    recentList.innerHTML = "";
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      recentList.appendChild(li);
    }
  } catch (err) {
    recentList.innerHTML = '<li class="error">couldn\'t load recent list</li>';
  }
}

async function loadMessages(offset) {
  messagesBody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
  try {
    const response = await fetch(`/messages?limit=${PAGE_SIZE}&offset=${offset}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const page = await response.json();
    currentOffset = page.offset;

    if (page.items.length === 0) {
      messagesBody.innerHTML = '<tr><td colspan="3">no messages yet</td></tr>';
    } else {
      messagesBody.innerHTML = "";
      for (const item of page.items) {
        const tr = document.createElement("tr");
        tr.classList.add("message-row");
        const created = new Date(item.created_at).toLocaleString();
        tr.innerHTML = `<td>${item.id}</td><td>${escapeHtml(item.say)}</td><td>${created}</td>`;
        tr.addEventListener("click", () => sayMessage(item.id));
        messagesBody.appendChild(tr);
      }
    }

    const totalPages = Math.max(1, Math.ceil(page.total / page.limit));
    const currentPage = Math.floor(page.offset / page.limit) + 1;
    pageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;
    prevPageBtn.disabled = page.offset <= 0;
    nextPageBtn.disabled = page.offset + page.limit >= page.total;
  } catch (err) {
    messagesBody.innerHTML = '<tr><td colspan="3" class="error">couldn\'t load messages</td></tr>';
  }
}

async function sayMessage(id) {
  try {
    const response = await fetch(`/messages/${id}/cowsay`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const art = await response.text();
    output.textContent = art;
    clearError();
    await loadRecent();
  } catch (err) {
    showError("couldn't say that message");
  }
}

sayForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = sayInput.value.trim();
  if (!text) {
    showError("say something first");
    return;
  }
  clearError();
  const submitButton = sayForm.querySelector("button");
  submitButton.disabled = true;
  try {
    const response = await fetch("/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ say: text }),
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const created = await response.json();
    output.textContent = created.cowsay;
    sayInput.value = "";
    await loadRecent();
    await loadMessages(0);
  } catch (err) {
    showError("failed to say that — try again");
  } finally {
    submitButton.disabled = false;
  }
});

prevPageBtn.addEventListener("click", () => {
  loadMessages(Math.max(0, currentOffset - PAGE_SIZE));
});

nextPageBtn.addEventListener("click", () => {
  loadMessages(currentOffset + PAGE_SIZE);
});

loadRecent();
loadMessages(0);
