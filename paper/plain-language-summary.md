---
type: paper-node
title: "Paper B (methods/validation) — Plain-language summary"
manuscript_section: plain-language-summary
provenance:
  ai_model: claude-sonnet-5
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing skill; playbook-write-up Step 12)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified, and not yet fit to publish.** This is written in plain language for people who are
> not researchers. It still needs two things before release: a check by someone with lived experience of doing a
> systematic review by hand, and Saul's own sign-off. This paper is a methods/validation study about the software
> tool itself (not a clinical review), so the usual "what treatment did people get" framing is adapted to "what did
> the AI tool do and how well did it do it" — the same plain-language rules still apply: short sentences, real
> numbers labelled in words, no jargon, and no recommendations.

# What we did and what we found — in plain terms

## The problem

When researchers do a systematic review, they have to read through hundreds or thousands of study titles and
abstracts to work out which ones are relevant. This takes a lot of time. Some tools now use AI to help with this by
acting as a "second screener" — a second pair of eyes checking the same studies a human already checked. But an AI
tool should never be the *only* screener. A human should always make the final call.

## What we tested

We built a tool called EvidenceEngine that uses AI as a second screener, and we tested how good it was at one part of
that job: deciding which study abstracts looked relevant to a review question. We gave the AI 327 study abstracts
from a real, published review about urinary incontinence treatments, and asked it to say which ones looked worth
reading in full.

We were careful about two things that can make an AI look better than it really is.

- **Had it seen the answers before?** AI language models are trained on huge amounts of text from the internet, so
  it is possible the AI had already read this particular published review during its training. We asked it, before
  we scored anything, whether it recognised the review. It said it recognised the topic and the dataset, but could
  not name which specific studies were included. That is a reassuring sign, but not a guarantee — so we treat our
  results as a likely *best case*, not a guaranteed everyday result.
- **Were we comparing it to a fair answer key?** We compared the AI's decisions to the original review's own
  published decisions, because that was the fairest fair answer key we had access to for this test. But that is not
  the same as comparing it to a fresh human doing the same job blind, which is the proper test we still need to run.

## What we found

Out of 78 studies that should have been kept, the AI correctly kept 69 of them and missed 9. That is a "recall" of
88 out of 100 (in the language researchers use: recall = .88).

When we looked closely at the 9 studies it missed, the picture was more reassuring than the raw number suggests.
Five of those 9 had actually been included in the original review after all — the AI mostly missed them because of
a research-design choice we had to make (we did not have the original team's exact rulebook for what counted as
relevant, so we had to write our own close approximation), not because the AI simply failed to notice a relevant
study. The other 4 studies the AI dropped were ones the original review team had also eventually excluded, once they
read the full papers.

So, in plain terms: the AI missed about 1 in 8 relevant studies in this one test, but roughly half of that "miss
rate" traces back to our own rulebook being an approximation, not to the AI itself.

## What this does and does not show

**What it shows:** an AI second screener that keeps a full paper trail of what it decided and why, checks itself for
having "seen the answers before," and is honest about where its testing rulebook was only an approximation, is
something we can build and test locally without sending any data outside the researcher's own computer.

**What it does not show:** it does not show that this AI tool is ready to be trusted on its own, or that it is as
good as, or better than, a properly trained human screener. Our test used one AI model, on one topic, checked
against one review's published answer key — not a fresh, independent human doing the same job blind, which is the
real test this tool still needs. Until that proper test is done, this should be read as "promising, but not yet
proven" — not as "this works."

## What happens next

The next step is a proper test: real people screen a real, new review by hand first, *before* seeing anything the AI
decided, and then we compare the two. That test has not happened yet. This paper reports the smaller test that came
before it, honestly, including the parts that did not go perfectly.
