# Our domains cannot be quietly redirected

**BUILT, NOT PROVEN**

## Network

Websites

## Code version

—

## Check it yourself

`curl -sI https://docs.vordium.com | grep -i strict-transport-security` shows that browsers are told to use only secure connections. Our official addresses are listed on the Token (https://docs.vordium.com/token) page.

## Last run (UTC date)

Checked every day

## Verifier

`python3 verifiers/check_site_headers.py`

## Result

Every site we serve tells browsers to use only secure connections; the security headers of each site and the official domains are checked every day and pass.

## Limits

The secure-only rule does not yet cover subdomains or the browsers' preload lists, and some redirects do not yet carry it. No watch yet covers name-server records, certificates issued for our domains, or domain expiry.

Also on the docs: https://docs.vordium.com/security/ai-audit/#domains
