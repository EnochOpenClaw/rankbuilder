# Google Search Console Status — House of Supreme
**Date:** 2026-06-26
**Checked by:** Enoch
**Site:** houseofsupreme.co.za

---

## Current Status: NOT VERIFIED (by us)

I attempted to access Google Search Console for houseofsupreme.co.za. The result:

- Google Search Console welcome page loads: ✅
- Requires Google account sign-in: ✅ (as expected)
- No existing property data accessible without login

## What I Cannot Determine Without Access

1. **Is the management company already managing GSC?** — I cannot verify this without either:
   - Direct access to the Google account that owns the property
   - The management company confirming they have added it
   - Attempting to add the property and seeing if it's already claimed

2. **What data exists** — Search performance, indexing status, Core Web Vitals, mobile usability, etc.

3. **Whether a sitemap has been submitted**

## How to Check if Already Claimed

### Method 1: Ask the Management Company Directly
Contact whoever manages the website and ask:
- "Is houseofsupreme.co.za already added to Google Search Console?"
- "If yes, which Google account/email owns it?"
- "Can you add [your Google email] as a user with full permissions?"

### Method 2: Try to Add It Yourself (Safe)
1. Go to https://search.google.com/search-console
2. Sign in with a Google account (e.g., craigp@ctdesignz.co.za or a new one)
3. Click "Add property" → Enter `houseofsupreme.co.za`
4. If it's already claimed, you'll see: "This property is already verified by another user"
5. If NOT claimed, you'll be able to verify it immediately

**Note:** If it's already claimed, you'll need to contact the owner to get access. You cannot "take over" a claimed property.

### Method 3: Check DNS TXT Record
Sometimes GSC verification leaves a TXT record in DNS:
```bash
nslookup -type=TXT houseofsupreme.co.za
```
Look for records containing `google-site-verification=` — this indicates someone has verified the domain.

## Recommended Next Steps

1. **Pick an email** — Decide which Google account should own GSC. I recommend:
   - craigp@ctdesignz.co.za (your domain, under your control)
   - Or create a dedicated Google account for HOS: `gsc@houseofsupreme.co.za` or similar

2. **Try Method 2 above** — Safest way to know if it's claimed

3. **If already claimed:**
   - Contact the management company
   - Request they add your email as a "Full user" (not "Owner" — keep owner rights for now)
   - Once added, you can view all data and submit sitemaps

4. **If NOT claimed:**
   - Verify immediately via DNS TXT record (recommended) or HTML file upload
   - Submit sitemap: `https://houseofsupreme.co.za/sitemap_index.xml`
   - Check for indexing issues
   - Set up Core Web Vitals monitoring

## What to Do Once Inside GSC

1. **Submit sitemap** — Essential for indexing
2. **Check Coverage report** — See which pages are indexed vs excluded
3. **Review Performance** — What queries bring traffic, which pages rank
4. **Check Core Web Vitals** — Page speed issues that affect rankings
5. **Mobile Usability** — Any mobile rendering problems
6. **Set up email alerts** — Get notified of indexing issues

## Important Note

Even if the management company has GSC access, YOU should also have access. GSC data is invaluable for SEO decisions — knowing which pages rank, which queries bring traffic, and where indexing problems exist. Without it, you're flying blind.

---

## Action for Craig

**Please try Method 2 (add property yourself) and let me know the result.**

If it's already claimed, we'll contact the management company.
If it's free, we'll verify it immediately and I'll walk you through the initial setup.
