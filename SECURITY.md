# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Trace, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email the maintainer directly at [junkim100@gmail.com](mailto:junkim100@gmail.com)
3. Include a detailed description of the vulnerability
4. If possible, include steps to reproduce

You can expect:
- Acknowledgment within 48 hours
- Regular updates on the fix progress
- Credit in the release notes (unless you prefer to remain anonymous)

## Data Handling

Trace is designed with privacy as a core principle:

### Local-Only Storage
- All data (screenshots, notes, database) is stored locally in `~/Library/Application Support/Trace/`
- No cloud sync, no remote servers, no accounts
- Your data never leaves your computer except for AI processing

### AI Processing
- Screenshots and text are sent to OpenAI's API for analysis
- Data is processed and immediately discarded by OpenAI
- OpenAI does not use API data for training (per their data usage policy)
- No data is retained by any third party

### Sensitive Data
- Trace captures screenshots of your entire screen
- Use the blocklist feature to exclude sensitive apps and domains
- Screenshots are automatically deleted after hourly processing
- You can reset all data at any time from Settings

## Security Recommendations

1. **Keep Trace updated** - Security fixes are included in updates
2. **Use the blocklist** - Exclude banking apps, password managers, and sensitive websites
3. **Review your notes** - Periodically check what information is being captured
4. **Secure your Mac** - Trace's data is only as secure as your system
5. **API key safety** - Keep your OpenAI API key private; it's stored locally in your app settings

## Scope

This security policy applies to:
- The Trace macOS application
- The official Homebrew tap (junkim100/trace)
- This GitHub repository

Third-party forks or distributions are not covered by this policy.
