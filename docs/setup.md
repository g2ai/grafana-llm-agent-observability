# Setup

Commands are PowerShell on Windows. Use a normal (not administrator) PowerShell window.

## 1. Grafana Cloud

1. Sign up at grafana.com and create a stack. **Choose the final stack name now.** Renaming a stack later broke Grafana.com sign in for me ("Invalid redirect URI") until the stack picked up the new URL.
2. In the stack: **Observability > Agent**, then **Start setup**.
3. The setup screen shows the API URL, Instance ID and OTLP endpoint. Note them.
4. Create a token you can manage and revoke: grafana.com > your org > **Security > Access Policies > New access policy**.
   - Realm: your stack only
   - Scopes: `metrics:write`, `logs:write`, `traces:write` and, under additional scopes, `sigil:write`
   - Add a token with an expiry date. It starts with `glc_` and is shown once.

The setup screen can also create a token for you, but that token did not appear in the Access Policies list, so I could not revoke it from the UI.

## 2. Anthropic API

1. Create an account at the Claude Console (separate from a Claude Pro plan; Pro does not include API access).
2. Buy prepaid credit ($5 is plenty) and leave auto reload **off**. The credit then acts as a hard spend cap.
3. Create an API key.

## 3. The .env file

`.env` is git ignored. Never commit it.

```powershell
Copy-Item .env.example .env
```

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `AGENTO11Y_ENDPOINT` | API URL from the setup screen, e.g. `https://agento11y-prod-<region>.grafana.net` |
| `AGENTO11Y_PROTOCOL` | `http` |
| `AGENTO11Y_AUTH_MODE` | `basic` |
| `AGENTO11Y_AUTH_TENANT_ID` | Instance ID |
| `AGENTO11Y_AUTH_TOKEN` | `glc_...` token |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint, ends in `/otlp` |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64 of instance_id:token>` |

Two gotchas with the OTLP header:

- The Python OTel exporter rejects a literal space in this variable. Use `Basic%20`, not `Basic `.
- Build the base64 value without a trailing newline. Safest way, which also keeps the token off the screen:

```powershell
$sec = Read-Host "Paste Grafana token" -AsSecureString
$token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("<instance_id>:$token"))
Remove-Variable token, sec
```

In my stack the OTLP username was the same number as the Agent Observability Instance ID. Check yours on the OpenTelemetry card.

## 4. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
```

In Windows PowerShell 5.1, `pip freeze > requirements.txt` writes UTF-16. Use `pip freeze | Set-Content requirements.txt -Encoding ascii`.

## 5. Check the wiring

```powershell
python src\hello.py
```

- No `WARNING` lines in the terminal.
- **Agent > Conversations** shows a `hello-...` conversation within a minute or two.
- **Explore > traces** shows a `generateText ...` span for service `sre-triage-agent`.
- **Explore > prom** shows `gen_ai_client_*` metrics.

## 6. Evaluators, rules and alert (before demo traffic)

Evaluations score only traffic that arrives after the rule exists.

1. **Agent > Evaluations > New evaluation > Create a new evaluation manually.**
2. Rule `online.quality.sre_triage`: trigger **User-visible response**, agent name `sre-triage-agent`, sample rate 100.
3. Add evaluators (**Add evaluator**). See [architecture.md](architecture.md#evaluation-setup-configured-in-the-grafana-ui) for the list.
   - In **Use existing**, click an evaluator once to attach it. Clicking a template creates your own copy.
   - Set **Pass when** on every evaluator. Without it there is no verdict and no pass rate.
4. Choose **Parallel**, so every evaluator counts toward the pass rate alert.
5. **Add alert**: pass rate below 70%, pick a contact point.
6. Create a second rule `online.safety.injection` with `template.prompt_injection_resistance`.
7. Test each judge in the **Playground** on an existing conversation before saving.

Then run `python scripts\run_scenarios.py all`. Scores appear a few minutes later.
