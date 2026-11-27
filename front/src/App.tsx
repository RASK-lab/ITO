import { useState } from "react";

function App() {
  const [result, setResult] = useState("");

  async function checkBackend() {
    try {
      const response = await fetch("/api/health");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setResult(JSON.stringify(data, null, 2));

    } catch (error) {
      setResult(String(error));
    }
  }

  return (
    <main>
      <h1>ITO Development Environment</h1>

      <button onClick={checkBackend}>
        Check Backend
      </button>

      <pre>{result}</pre>
    </main>
  );
}

export default App;
