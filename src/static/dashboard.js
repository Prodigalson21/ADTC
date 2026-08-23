/* dashboard.js -- vanilla JS, no build step, no CDN dependency. */

async function sendQuery() {
  const input = document.getElementById("query-input");
  const resultDiv = document.getElementById("query-result");
  const text = input.value.trim();
  if (!text) return;

  resultDiv.textContent = "Sending...";
  resultDiv.className = "";

  try {
    const resp = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    resultDiv.textContent = JSON.stringify(data, null, 2);
    resultDiv.className = data.success ? "success" : "error";
  } catch (err) {
    resultDiv.textContent = "Network error: " + err.message;
    resultDiv.className = "error";
  }
}

async function readScale() {
  const resultDiv = document.getElementById("scale-result");
  resultDiv.textContent = "Reading...";
  resultDiv.className = "";

  try {
    const resp = await fetch("/api/scale");
    const data = await resp.json();
    resultDiv.textContent = JSON.stringify(data, null, 2);
    resultDiv.className = data.success ? "success" : "error";
  } catch (err) {
    resultDiv.textContent = "Network error: " + err.message;
    resultDiv.className = "error";
  }
}

async function checkBarcode() {
  const resultDiv = document.getElementById("barcode-result");
  resultDiv.textContent = "Checking...";
  resultDiv.className = "";

  try {
    const resp = await fetch("/api/barcode");
    const data = await resp.json();
    resultDiv.textContent = JSON.stringify(data, null, 2);
    resultDiv.className = data.success ? "success" : "error";
  } catch (err) {
    resultDiv.textContent = "Network error: " + err.message;
    resultDiv.className = "error";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("query-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendQuery();
    });
  }
});
