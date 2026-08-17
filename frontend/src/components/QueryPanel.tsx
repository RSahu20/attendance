import { useState, type FormEvent } from "react";

const examples = [
  "Who was present on 2026-01-05?",
  "What was the average attendance percentage?",
  "Show the evidence supporting this answer.",
  "What was the attendance in a date that does not exist?",
];

interface Props {
  busy: boolean;
  error: string | null;
  onAsk: (question: string) => Promise<void>;
}

export function QueryPanel({ busy, error, onAsk }: Props) {
  const [question, setQuestion] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim()) await onAsk(question.trim());
  }
  return (
    <section className="panel" aria-labelledby="query-title">
      <p className="step">3 · Ask</p>
      <h2 id="query-title">Ask about attendance</h2>
      <form className="question-form" onSubmit={(event) => void submit(event)}>
        <label className="sr-only" htmlFor="question">Question</label>
        <textarea
          id="question"
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What was the average attendance percentage?"
          rows={3}
          value={question}
        />
        <button className="button" disabled={busy || !question.trim()} type="submit">
          {busy ? "Checking evidence…" : "Ask"}
        </button>
      </form>
      <div className="examples" aria-label="Example questions">
        {examples.map((example) => (
          <button key={example} onClick={() => setQuestion(example)} type="button">{example}</button>
        ))}
      </div>
      {error && <div className="message message--error" role="alert">{error}</div>}
    </section>
  );
}
