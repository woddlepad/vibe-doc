const form = document.getElementById("login-form");
const button = document.getElementById("login-submit");
const error = document.getElementById("login-error");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  error.hidden = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        password: document.getElementById("password").value,
      }),
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(result.detail || "Could not sign in. Try again.");
    window.location.replace("/");
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
    button.disabled = false;
  }
});
