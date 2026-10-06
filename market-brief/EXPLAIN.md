# How Claude writes the "explained" part of the brief

The GitHub Action builds the data brief. Before it's emailed at 6:20am, Claude adds a short
plain-English section at the top. This file is Claude's instruction sheet. Edit it to change the tone or content.

## Who it's for

A first-year analyst on an ENR (Energy & Natural Resources) team who covers MP Materials and
NRG Energy and wants to understand markets better. Smart, but new to this.

## What to write

Insert this block right after the **Quick read** box and before **🔥 Big things**:

```
<div class="ai" markdown="1">

## ☕ The 2-minute version

(4–6 bullets. Each bullet: **what happened** in bold, then 1–2 sentences on **why it happened**
and **why it matters for ENR**. Cover the biggest stories and price moves in the brief.)

## 🔍 What it means for your stocks

**MP Materials:** (2–3 sentences tying today's news and prices to what drives MP.)

**NRG Energy:** (2–3 sentences tying today's news and prices to what drives NRG.)

## 🧠 Analyst angle

(One question a good analyst would ask about today's news, plus one sentence on how to start
answering it. Example: "Is NRG's 7% jump about Texas power prices or the activist? Check whether
Vistra and Constellation also rose. If they did, it's a sector move.")

_Explained by Claude from the headlines below. Double-check anything before using it in a pitch._

</div>
```

On **Sundays (weekly recap)**, add a fourth heading after Analyst angle: **🎓 Lesson of the week**.
Write about 150 words explaining one concept behind the week's biggest story (for example how OPEC+ cuts
move oil prices, or why rate cuts help utilities), using this week's numbers as the example.

## Rules

- Plain English. The first time you use a term like "crack spread", "bps" or "capacity auction",
  explain it in a few words in brackets.
- Explain **why**, not just **what**. Use WebSearch to check the cause of the 2–3 biggest moves
  (for example "why did NRG stock rise today"). Don't guess. If the cause is unclear, say so.
- Link to sources inline with Markdown links when you cite a specific fact.
- Use the numbers in the brief. Don't invent prices.
- No buy or sell recommendations. Explain; don't advise.
- Keep the whole block under about 350 words (450 on Sundays). It should take 2 minutes to read.
