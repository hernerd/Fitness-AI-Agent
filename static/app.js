// -------- Elements --------
const chat = document.getElementById("chat");
const input = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

const profileModal = document.getElementById("profileModal");
const closeModal = document.getElementById("closeModal");
const editProfileBtn = document.getElementById("editProfileBtn");
const profileForm = document.getElementById("profileForm");

const fridgeBtn = document.getElementById("fridgeBtn");
const fridgeModal = document.getElementById("fridgeModal");
const closeFridgeModal = document.getElementById("closeFridgeModal");
const fridgeInput = document.getElementById("fridgeInput");
const fridgeList = document.getElementById("fridgeList");
const generateMealsBtn = document.getElementById("generateMealsBtn");

// -------- State --------
let profile = JSON.parse(localStorage.getItem("fitnessProfile") || "null");
let history = []; // {role: "user"|"assistant", content: string}
let fridgeItems = JSON.parse(localStorage.getItem("fridgeItems") || "[]");

function showModal() {
  // Prefill if profile exists
  if (profile) {
    for (const [k, v] of Object.entries(profile)) {
      if (profileForm.elements[k]) profileForm.elements[k].value = v;
    }
  }
  profileModal.style.display = "flex";
}

function hideModal() {
  profileModal.style.display = "none";
}

// Show on first visit if no profile
window.addEventListener("load", () => {
  if (!profile) showModal();
  greeting();
});

// -------- Chat UI helpers --------
function addMessage(content, role = "bot") {
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;
  wrap.innerText = content;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

function addTyping() {
  const wrap = document.createElement("div");
  wrap.className = "message bot";
  wrap.dataset.typing = "1";
  wrap.innerText = "…";
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

function removeTyping(node) {
  if (node && node.parentNode) node.parentNode.removeChild(node);
}

// -------- Events: Modal --------
editProfileBtn.addEventListener("click", showModal);
closeModal.addEventListener("click", hideModal);

profileForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(profileForm).entries());
  // Normalize a bit
  data.age = Number(data.age || 0);
  data.weight = Number(data.weight || 0); // lbs
  data.height = Number(data.height || 0); // in
  data.activity = data.activity || "";
  data.goal = (data.goal || "").toLowerCase();
  data.diet = (data.diet || "").toLowerCase();
  data.allergies = (data.allergies || "").trim();
  
  // NEW: Normalize Health Concerns
  data.health_concerns = (data.health_concerns || "").trim();

  profile = data;
  localStorage.setItem("fitnessProfile", JSON.stringify(profile));
  hideModal();
  addMessage("Profile saved! Ask for a diet/workout plan anytime, or just chat.", "bot");
});

fridgeBtn.addEventListener("click", () => {
  fridgeModal.style.display = "flex";
  renderFridge();
});

closeFridgeModal.addEventListener("click", () => {
  fridgeModal.style.display = "none";
});

// -------- Send message --------
sendBtn.addEventListener("click", onSend);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") onSend();
});

fridgeInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const value = fridgeInput.value.trim().toLowerCase();
    if (!value) return;

    if (!fridgeItems.includes(value)) {
      fridgeItems.push(value);
      localStorage.setItem("fridgeItems", JSON.stringify(fridgeItems));
      renderFridge();
    }

    fridgeInput.value = "";
  }
});

function onSend(intentHint = "") {
  const text = input.value.trim();
  if (!text && !intentHint) return;

  const userMessage = text || (
    intentHint === "variation" ? "next" :
    intentHint === "diet" ? "Please generate a personalized diet plan." :
    intentHint === "workout" ? "Please generate a personalized workout plan." :
    intentHint === "shopping" ? "Please generate a shopping list for this week's meals." : ""
  );

  // Render user bubble
  addMessage(userMessage, "user");
  history.push({ role: "user", content: userMessage });
  input.value = "";

  // Call backend
  const typing = addTyping();
  fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: userMessage,
      history,
      profile,
      intentHint
    })
  })
  .then(async (res) => {
    const json = await res.json();
    removeTyping(typing);
    const reply = json.reply || "Sorry, I had trouble replying.";
    addMessage(reply, "bot");
    history.push({ role: "assistant", content: reply });
  })
  .catch(err => {
    removeTyping(typing);
    addMessage(`Network error: ${err.message}`, "bot");
  });
}

function renderFridge() {
  fridgeList.innerHTML = "";

  fridgeItems.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "fridge-item";

    div.innerHTML = `
      <span>${item}</span>
      <button>×</button>
    `;

    div.querySelector("button").addEventListener("click", () => {
      fridgeItems.splice(index, 1);
      localStorage.setItem("fridgeItems", JSON.stringify(fridgeItems));
      renderFridge();
    });

    fridgeList.appendChild(div);
  });
}

// -------- Suggestions chips --------
document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    const intent = chip.dataset.intent || "";
    if (!profile && (intent === "diet" || intent === "workout" || intent === "shopping" || intent === "variation")) {
      addMessage("Please complete your profile first (Edit Profile).", "bot");
      showModal();
      return;
    }
    onSend(intent);
  });
});

generateMealsBtn.addEventListener("click", () => {
  if (fridgeItems.length === 0) {
    addMessage("Add some ingredients first!", "bot");
    return;
  }

  const message = `I have these ingredients: ${fridgeItems.join(", ")}. What can I make?`;

  // ✅ Use existing chat system (clean integration)
  input.value = message;

  fridgeModal.style.display = "none";

  onSend(); // uses your existing pipeline
});

// -------- Greeting --------
function greeting() {
  addMessage(
    "Hi! I’m your fitness & diet buddy. " +
    "You can ask me anything, or use the chips below to get a personalized diet/workout plan. " +
    "Use “Edit Profile” to update your details anytime.",
    "bot"
  );
}






