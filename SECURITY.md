# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in CrisisWatch AI, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email: **security@crisiswatch-ai.dev**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

| Action | SLA |
|--------|-----|
| Acknowledgement | Within 48 hours |
| Triage & assessment | Within 5 business days |
| Fix or mitigation | Within 14 business days |
| Public disclosure | After fix is released |

## Scope

### In Scope
- Backend API (FastAPI) — authentication bypass, injection, SSRF
- Frontend (Next.js) — XSS, CSRF, sensitive data exposure
- ML pipeline — model poisoning, adversarial input causing dangerous outputs
- Infrastructure — Docker, database, Redis misconfigurations
- Dependencies — known CVEs in npm/pip packages

### Out of Scope
- Social engineering attacks
- Denial of service against upstream data sources
- The ML models' prediction accuracy (not a security issue)

## Security Practices

- No secrets or API keys are committed to the repository
- Environment variables are used for all configuration (`.env.example` provided)
- CORS is restricted to configured origins
- Rate limiting is applied to all API endpoints
- Input validation via Pydantic on all POST endpoints
- SQL injection prevented by SQLAlchemy ORM (parameterized queries)
- Frontend uses React's built-in XSS protections (no `dangerouslySetInnerHTML` with user input)

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest main | ✅ |
| Older commits | ❌ |

## Dependencies

We use `npm audit` and `pip-audit` (via CI) to scan for known vulnerabilities in dependencies. Critical vulnerabilities are patched within 72 hours.
