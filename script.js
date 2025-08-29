// helpers
function showSection(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(id);
  if (target) target.classList.add('active');
  document.querySelectorAll('.sidebar ul li').forEach(li => li.classList.remove('active'));
  if (window.event && window.event.target && window.event.target.tagName === 'LI') {
    window.event.target.classList.add('active');
  }
}
function toggleCard(id) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.style.maxHeight) el.style.maxHeight = null;
  else el.style.maxHeight = el.scrollHeight + "px";
}

let lastStructured = { mcqs: [], true_false: [] };
let lastRaw = "";

// generate
document.getElementById("generateBtn").addEventListener("click", async () => {
  const pdfFile = document.getElementById("pdfInput").files[0];
  const status = document.getElementById("status");
  if (!pdfFile) { alert("Please upload a PDF first."); return; }

  const formData = new FormData();
  formData.append("pdf", pdfFile);

  status.innerText = "Generating questions...";

  try {
    const res = await fetch("http://127.0.0.1:5000/generate-questions", { method: "POST", body: formData });
    const data = await res.json();

    if (data.error) {
      status.innerText = "Error: " + data.error;
      console.error("Backend error:", data);
      return;
    }

    console.log("Backend response:", data);

    // If backend returned raw and empty arrays, show raw in console and UI notice
    if (Array.isArray(data.mcqs) && data.mcqs.length === 0 &&
        Array.isArray(data.true_false) && data.true_false.length === 0) {
      lastStructured = { mcqs: [], true_false: [] };
      lastRaw = data.raw || "";
      status.innerText = "No parsed questions — check console (raw AI output).";
      console.warn("Raw AI output (check formatting):", lastRaw);
      // show the raw output in MCQ section so you can see what model returned
      const mcqList = document.getElementById("mcqList");
      mcqList.innerHTML = "";
      const li = document.createElement("li");
      li.className = "question-card";
      li.style.whiteSpace = "pre-wrap";
      li.textContent = data.raw || "No raw provided";
      mcqList.appendChild(li);
      toggleCard('mcqList');
      return;
    }

    // Normal rendering when parsed
    lastStructured = { mcqs: data.mcqs || [], true_false: data.true_false || [] };
    lastRaw = "";

    const mcqList = document.getElementById("mcqList");
    const tfList = document.getElementById("tfList");
    mcqList.innerHTML = "";
    tfList.innerHTML = "";

    let qNum = 1;
    (lastStructured.mcqs || []).forEach(q => {
      const li = document.createElement("li");
      li.className = "question-card";
      li.style.whiteSpace = "pre-line";
      li.innerText = `Q${qNum}: ${q.question}\nA. ${q.options?.[0] || ""}\nB. ${q.options?.[1] || ""}\nC. ${q.options?.[2] || ""}\nD. ${q.options?.[3] || ""}\nAnswer: ${q.answer || ""}`;
      mcqList.appendChild(li);
      qNum++;
    });

    let tNum = 1;
    (lastStructured.true_false || []).forEach(q => {
      const li = document.createElement("li");
      li.className = "question-card";
      li.style.whiteSpace = "pre-line";
      li.innerText = `T${tNum}: ${q.question}\nAnswer: ${q.answer}`;
      tfList.appendChild(li);
      tNum++;
    });

    // expand both lists
    document.getElementById("mcqList").style.maxHeight = document.getElementById("mcqList").scrollHeight + "px";
    document.getElementById("tfList").style.maxHeight = document.getElementById("tfList").scrollHeight + "px";

    status.innerText = "Questions generated successfully!";

  } catch (err) {
    console.error(err);
    document.getElementById("status").innerText = "❌ Error generating questions. Check console logs.";
  }
});

// export (keeps your existing export)
document.getElementById("exportBtn").addEventListener("click", () => {
  if ((lastStructured.mcqs.length || lastStructured.true_false.length)) {
    const rows = [["Type", "Question", "Option A", "Option B", "Option C", "Option D", "Answer"]];
    lastStructured.mcqs.forEach(q => rows.push(["MCQ", q.question || "", q.options?.[0]||"", q.options?.[1]||"", q.options?.[2]||"", q.options?.[3]||"", q.answer||""]));
    lastStructured.true_false.forEach(q => rows.push(["True/False", q.question || "", "", "", "", "", q.answer || ""]));
    const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], {type: "text/csv"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "quiz_questions.csv"; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    return;
  }
  if (lastRaw) {
    const blob = new Blob([lastRaw], {type: "text/plain"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "ai_raw_output.txt"; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    return;
  }
  alert("No questions to export. Please generate first.");
});