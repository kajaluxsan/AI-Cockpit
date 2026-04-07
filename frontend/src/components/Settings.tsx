import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import { settingsApi } from "@/lib/api";

export default function Settings() {
  const { data } = useApi(() => settingsApi.get(), []);
  const [testEmail, setTestEmail] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);

  const sendTestEmail = async () => {
    setTestResult(null);
    try {
      const result = await settingsApi.testEmail(testEmail);
      setTestResult(result.success ? "OK — email sent" : "FAILED to send");
    } catch (e: any) {
      setTestResult(`Error: ${e.message}`);
    }
  };

  const testTwilio = async () => {
    setTestResult(null);
    try {
      const result = await settingsApi.testTwilio();
      setTestResult(JSON.stringify(result, null, 2));
    } catch (e: any) {
      setTestResult(`Error: ${e.message}`);
    }
  };

  if (!data) return <div className="text-text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-text-secondary mt-1">
          Read-only configuration overview. All values are loaded from{" "}
          <code className="font-mono text-amber-accent">.env</code>.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Application">
          <Row k="Name" v={data.app.name} />
          <Row k="Environment" v={data.app.env} />
          <Row k="Agent name" v={data.app.agent_name} />
          <Row k="Company" v={data.app.company_name} />
        </Card>

        <Card title="Active sources">
          <Row k="Email" v={data.sources.email ? "ENABLED" : "disabled"} />
          <Row k="LinkedIn" v={data.sources.linkedin ? "ENABLED" : "disabled"} />
          <Row k="External API" v={data.sources.external_api ? "ENABLED" : "disabled"} />
        </Card>

        <Card title="Matching">
          <Row k="Threshold" v={`${data.matching.threshold_percent}%`} />
          <Row k="Auto call" v={data.matching.auto_call_enabled ? "yes" : "no"} />
          <Row k="Auto follow-up" v={data.matching.auto_email_followup ? "yes" : "no"} />
          <Row k="Required fields" v={data.matching.missing_info_fields.join(", ")} />
        </Card>

        <Card title="Twilio">
          <Row k="Configured" v={data.twilio.configured ? "yes" : "no"} />
          <Row k="Phone" v={data.twilio.phone_number ?? "—"} />
        </Card>

        <Card title="ElevenLabs">
          <Row k="Configured" v={data.elevenlabs.configured ? "yes" : "no"} />
          <Row k="Model" v={data.elevenlabs.model} />
        </Card>

        <Card title="Deepgram">
          <Row k="Configured" v={data.deepgram.configured ? "yes" : "no"} />
          <Row k="Model" v={data.deepgram.model} />
          <Row k="Auto language detect" v={data.deepgram.language_detect ? "yes" : "no"} />
        </Card>

        <Card title="Anthropic / Claude">
          <Row k="Configured" v={data.anthropic.configured ? "yes" : "no"} />
          <Row k="Model" v={data.anthropic.model} />
        </Card>

        <Card title="External API">
          <Row k="Base URL" v={data.external_api.base_url || "—"} />
          <Row k="Auth type" v={data.external_api.auth_type} />
        </Card>
      </div>

      <div className="card p-6">
        <h2 className="font-display text-lg font-semibold mb-4">Connection tests</h2>
        <div className="flex flex-wrap items-center gap-3">
          <input
            className="input max-w-sm"
            placeholder="email@example.ch"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
          />
          <button className="btn-secondary" onClick={sendTestEmail} disabled={!testEmail}>
            Send test email
          </button>
          <button className="btn-secondary" onClick={testTwilio}>
            Test Twilio config
          </button>
        </div>
        {testResult && (
          <pre className="mt-4 p-3 bg-bg-elevated rounded-md text-xs whitespace-pre-wrap">
            {testResult}
          </pre>
        )}
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <h3 className="font-display font-semibold mb-3">{title}</h3>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="label-mono">{k}</span>
      <span className="font-mono text-text-primary">{v}</span>
    </div>
  );
}
