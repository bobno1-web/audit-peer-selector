# Peer Company Selector (PeerLens)

[🇰🇷 한국어](README.md) | 🇺🇸 English

**Enter just one company name, and it finds and ranks the peer companies that are financially comparable to it.**

## ▶️ Demo Video

A one-minute video beats a long explanation. See how it actually works first.

▶️ **(video link)**

## What this tool is

When an auditor analyzes a company, the same question always comes up — **"What do we compare this company against?"**

Whether a financial ratio is high or low, normal or abnormal, can only be judged **by comparing it against similar companies.** Yet choosing "similar companies" usually relies on human intuition. Being in the same industry does not make a company a valid comparison, and being similar in size does not make the business similar. When this choice wavers, the entire analysis that follows wavers with it.

This tool replaces that choice **with data.**

1. It **automatically fetches financial and business information** by company name,
2. **computes the degree of similarity** by combining industry, size, market cap, and business content,
3. **organizes peer companies in order of similarity,** and
4. shows **why each company was chosen and how trustworthy** it is.

Enter one company name, wait a moment, and the comparison-set selection is done in one place.

## Who needs it and why

**Built for these people — audit teams at accounting firms.**
A tool for when you prepare analytical procedures, review a new client's financials, or need to decide on comparison targets.

**The difficulties auditors actually face**

- Because peer companies are **chosen by human judgment,** the rationale wavers and differs from person to person.
- Even within the same industry code, companies with **extremely different sizes** or entirely different businesses get mixed in, sometimes making the comparison meaningless.

**How this tool solves it**
It combines industry, size, market cap, and business content into data and presents peer companies **in order of similarity.** It then reveals with tags in what respect each company is similar (industry, size, business content), and tells you with a confidence level whether the comparison is solid or not. Data takes the place of the chooser's intuition.

**How it's used**

- **Preparing analytical procedures** — select, from data, a comparison group to benchmark financial ratios against
- **Reviewing new engagements** — quickly grasp the peers of a company you are about to take on
- **Documenting the basis for comparison** — leave a record of why you compared against these companies

## What it looks like

Enter one company name and it comes out like this.

![Peer Company Selector — landing screen](docs/images/web_landing.png)

*Landing screen — product intro and a start button.*

![Peer Company Selector — API key entry](docs/images/web_key.png)

*API key entry — you enter your OpenDART authentication key.*

![Peer Company Selector — result screen](docs/images/web_result_ottogi.png)

*Result screen — peer companies ordered by similarity, each with similarity-basis tags and a confidence level.*

## How to run

What you need: **Python 3**, and an **OpenDART API key** (free).

```
1) (once) pip install -r requirements.txt
2) double-click start.bat           ← Windows
   ./start.sh                        ← macOS / Linux
3) the browser opens http://127.0.0.1:5000 automatically
4) on the screen, enter API key → enter company name → view results
```

> **This tool runs on your own PC.** When you double-click `start.bat`, a console window opens and, after a moment, the browser opens automatically. **Do not close this console window while using the tool — this window keeps the server alive.** When you close the window after you're done, the server shuts down.

**An API key is required.** The OpenDART authentication key is issued **for free.**

| Key | Issued at |
|---|---|
| `OPENDART_API_KEY` | https://opendart.fss.or.kr (OpenDART authentication key) |

> The key is **entered on screen,** stays briefly in this PC's memory only, and disappears when you stop the server. It is not saved to any file or record, and it runs only inside your own PC — it never goes out. (See `.env.example`, which contains only the key name.)

## What this tool cared about

Four things that got special attention while building it.

**1. It chooses with data, not human intuition.**
When people pick "similar companies" by hand, the rationale wavers and differs from person to person. This tool combines industry, size, market cap, and business content into data and picks peer companies consistently, the same way every time.

**2. It looks at four things together, not one.**
Being in the same industry doesn't make a company similar. So instead of industry alone, it weighs four things together — size, market cap, and business content too — and lifts companies that resemble the target evenly across several dimensions. It doesn't get fooled by a company that matches on one axis but is completely different on the rest.

**3. It doesn't pad the list; if there's none, it says so.**
If there's no company with a similar industry, it doesn't fill the gap with companies that are merely similar in size. It honestly shows **"No industry-similar peer company was found."** And for companies that are hard to compare, it candidly flags **low confidence.**

**4. It works for any listed company, not a specific one.**
No values tuned to a particular company are baked in. Enter just a company name and it processes any listed company the same way. Every judgment criterion was derived from data.

---
_For developer documentation, see the `docs/` folder._
